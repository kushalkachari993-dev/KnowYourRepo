import tempfile
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.auth.supabase_auth import get_auth_client
from app.config.settings import settings
from app.ingestion.ingest import get_pipeline
from app.retrieval.aggregator import get_aggregator
from app.retrieval.chat import get_document_chat
from app.retrieval.search import get_searcher
from app.sources.connectors import get_source_connector


FRONTEND_DIST = settings.PROJECT_ROOT / "frontend" / "dist"
JOB_ROOT = settings.PROCESSED_DATA_DIR / "jobs"
JOBS: Dict[str, Dict[str, Any]] = {}
JOB_LOCK = threading.Lock()

app = FastAPI(title="KnowYourRepo API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SignInRequest(BaseModel):
    email: str
    password: str


class SourceEstimateRequest(BaseModel):
    source_url: str


class IngestSourceRequest(BaseModel):
    source_url: str
    session_id: str = Field(default_factory=lambda: f"session:{uuid4().hex}")


class SearchRequest(BaseModel):
    query: str
    session_id: str
    top_k: int = 5
    similarity_threshold: float = 0.3


class ChatRequest(BaseModel):
    question: str
    chunks: List[Dict[str, Any]] = Field(default_factory=list)


class CleanupRequest(BaseModel):
    secret: Optional[str] = None


def pipeline():
    return get_pipeline()


def searcher():
    return get_searcher()


def aggregator():
    return get_aggregator()


def chat():
    return get_document_chat()


def bearer_token(authorization: Optional[str]) -> str:
    if not authorization:
        return ""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return token.strip()


def auth_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    token = bearer_token(authorization)
    if not token:
        return {}
    try:
        return get_auth_client().get_user(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid auth token: {exc}") from exc


def identity(session_id: str, user: Dict[str, Any]) -> Dict[str, str | bool]:
    if user:
        return {
            "user_id": user.get("id", ""),
            "session_id": session_id,
            "signed_in": True,
        }
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required for anonymous requests.")
    return {
        "user_id": f"anon:{session_id}",
        "session_id": session_id,
        "signed_in": False,
    }


def owner_filter(user_id: str = "", session_id: str = "") -> Dict[str, Any]:
    owner_clauses = []
    if user_id:
        owner_clauses.append({"user_id": user_id})
    if session_id:
        owner_clauses.append({"session_id": session_id})

    if not owner_clauses:
        return {}
    if len(owner_clauses) == 1:
        return owner_clauses[0]
    return {"$or": owner_clauses}


def public_source_url(doc: Dict[str, Any]) -> str:
    metadata = doc.get("metadata", {})
    return metadata.get("source_url", "")


def create_job(kind: str, ident: Dict[str, str | bool], label: str) -> Dict[str, Any]:
    job_id = f"job:{uuid4().hex}"
    now = int(time.time())
    job = {
        "job_id": job_id,
        "kind": kind,
        "label": label,
        "status": "queued",
        "progress": 0,
        "message": "Queued",
        "user_id": ident["user_id"],
        "session_id": ident["session_id"],
        "signed_in": ident["signed_in"],
        "created_at": now,
        "updated_at": now,
        "expires_at": now + int(settings.SESSION_TTL_SECONDS),
        "files_indexed": 0,
        "chunks_indexed": 0,
        "chunks_by_file": {},
        "error": "",
    }
    with JOB_LOCK:
        JOBS[job_id] = job
    return job.copy()


def update_job(job_id: str, **changes: Any) -> Dict[str, Any]:
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise KeyError(job_id)
        job.update(changes)
        job["updated_at"] = int(time.time())
        return job.copy()


def get_job(job_id: str) -> Dict[str, Any]:
    with JOB_LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        return job.copy()


def authorize_job(job: Dict[str, Any], session_id: Optional[str], user: Dict[str, Any]) -> None:
    if user and job.get("user_id") == user.get("id"):
        return
    if session_id and job.get("session_id") == session_id:
        return
    raise HTTPException(status_code=403, detail="You do not have access to this job.")


def run_source_ingestion_job(job_id: str, source_url: str, user_id: str, session_id: str) -> None:
    try:
        update_job(job_id, status="running", progress=10, message="Fetching source files")
        results = pipeline().ingest_source_url(source_url, user_id=user_id, session_id=session_id)
        chunks_indexed = sum(results.values())
        update_job(
            job_id,
            status="completed",
            progress=100,
            message=f"Indexed {len(results)} files",
            files_indexed=len(results),
            chunks_indexed=chunks_indexed,
            chunks_by_file=results,
        )
    except Exception as exc:
        update_job(job_id, status="failed", progress=100, message="Ingestion failed", error=str(exc))


def run_upload_ingestion_job(
    job_id: str,
    saved_files: List[Dict[str, str]],
    user_id: str,
    session_id: str,
    source_id: str,
    job_dir: str,
) -> None:
    chunks_by_file = {}
    try:
        update_job(job_id, status="running", progress=5, message="Indexing uploaded files")
        total_files = max(len(saved_files), 1)
        for index, saved_file in enumerate(saved_files, start=1):
            filename = saved_file["filename"]
            update_job(
                job_id,
                progress=max(5, int((index - 1) / total_files * 90)),
                message=f"Indexing {filename}",
            )
            chunks_by_file[filename] = pipeline().ingest_file(
                saved_file["path"],
                extra_metadata={
                    "source_type": "upload",
                    "source_path": filename,
                    "document_id": f"upload:{filename}:{uuid4().hex[:8]}",
                },
                user_id=user_id,
                source_id=source_id,
                session_id=session_id,
            )

        update_job(
            job_id,
            status="completed",
            progress=100,
            message=f"Indexed {len(chunks_by_file)} uploaded files",
            files_indexed=len(chunks_by_file),
            chunks_indexed=sum(chunks_by_file.values()),
            chunks_by_file=chunks_by_file,
        )
    except Exception as exc:
        update_job(job_id, status="failed", progress=100, message="Upload ingestion failed", error=str(exc))
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {"ok": True, "time": int(time.time())}


@app.get("/api/config")
def config() -> Dict[str, Any]:
    return {
        "vector_backend": settings.VECTOR_DB_BACKEND,
        "collection_name": settings.COLLECTION_NAME,
        "embedding_provider": settings.EMBEDDING_PROVIDER,
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_dimension": settings.EMBEDDING_DIMENSION,
        "chat_provider": settings.CHAT_PROVIDER,
        "chat_model": settings.CHAT_MODEL,
        "anonymous_repo_limit_mb": settings.ANONYMOUS_REPO_LIMIT_MB,
        "session_ttl_seconds": settings.SESSION_TTL_SECONDS,
        "supabase_configured": bool(settings.SUPABASE_URL and settings.SUPABASE_ANON_KEY),
    }


@app.get("/api/status")
def status(
    session_id: Optional[str] = Query(default=None),
    user: Dict[str, Any] = Depends(auth_user),
) -> Dict[str, Any]:
    user_id = user.get("id", "") if user else ""
    if not user_id and session_id:
        user_id = f"anon:{session_id}"

    filters = owner_filter(user_id=user_id, session_id=session_id or "")
    store_status = pipeline().get_status(where=filters, active_or_legacy=True) if filters else pipeline().get_status()
    if not filters:
        store_status["total_chunks"] = 0

    return {
        "total_chunks": store_status["total_chunks"],
        "collection_name": store_status["collection_name"],
        "metadata": store_status["metadata"],
        "user": user,
    }


@app.post("/api/auth/sign-in")
def sign_in(payload: SignInRequest) -> Dict[str, Any]:
    session = get_auth_client().sign_in(payload.email.strip(), payload.password)
    return {
        "user": session.user,
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
    }


@app.post("/api/auth/sign-up")
def sign_up(payload: SignInRequest) -> Dict[str, Any]:
    result = get_auth_client().sign_up(payload.email.strip(), payload.password)
    return {
        "user": result.user,
        "confirmation_required": result.confirmation_required,
        "session": {
            "user": result.session.user,
            "access_token": result.session.access_token,
            "refresh_token": result.session.refresh_token,
        }
        if result.session
        else None,
    }


@app.post("/api/auth/sign-out")
def sign_out(authorization: Optional[str] = Header(default=None)) -> Dict[str, bool]:
    token = bearer_token(authorization)
    if token:
        get_auth_client().sign_out(token)
    return {"ok": True}


@app.post("/api/sources/estimate")
def estimate_source(payload: SourceEstimateRequest) -> Dict[str, Any]:
    size_mb = get_source_connector().estimate_size_mb(payload.source_url.strip())
    limit_mb = settings.ANONYMOUS_REPO_LIMIT_MB
    return {
        "size_mb": size_mb,
        "anonymous_limit_mb": limit_mb,
        "requires_auth": bool(size_mb is not None and size_mb > limit_mb),
    }


@app.post("/api/ingest/source")
def ingest_source(
    payload: IngestSourceRequest,
    background_tasks: BackgroundTasks,
    user: Dict[str, Any] = Depends(auth_user),
) -> Dict[str, Any]:
    source_url = payload.source_url.strip()
    if not source_url:
        raise HTTPException(status_code=400, detail="source_url is required.")

    connector = get_source_connector()
    requires_auth, size_mb = connector.requires_auth_for_anonymous(
        source_url,
        settings.ANONYMOUS_REPO_LIMIT_MB,
    )
    if requires_auth and not user:
        raise HTTPException(
            status_code=401,
            detail=(
                f"This GitHub repository is about {size_mb:.1f} MB. "
                f"Sign in to index repositories over {settings.ANONYMOUS_REPO_LIMIT_MB} MB."
            ),
        )

    ident = identity(payload.session_id, user)
    job = create_job("source", ident, source_url)
    background_tasks.add_task(
        run_source_ingestion_job,
        job["job_id"],
        source_url,
        ident["user_id"],
        ident["session_id"],
    )
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "message": job["message"],
        "signed_in": ident["signed_in"],
        "expires_in_seconds": settings.SESSION_TTL_SECONDS,
    }


@app.post("/api/ingest/upload")
async def ingest_upload(
    background_tasks: BackgroundTasks,
    session_id: str = Form(...),
    files: List[UploadFile] = File(...),
    user: Dict[str, Any] = Depends(auth_user),
) -> Dict[str, Any]:
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required.")

    ident = identity(session_id, user)
    source_id = f"upload_batch:{ident['user_id']}:{uuid4().hex[:12]}"
    job = create_job("upload", ident, f"{len(files)} uploaded files")
    job_dir = JOB_ROOT / job["job_id"].replace(":", "_")
    job_dir.mkdir(parents=True, exist_ok=True)
    saved_files = []

    for upload in files:
        filename = Path(upload.filename or f"upload_{uuid4().hex}").name
        destination = job_dir / filename
        destination.write_bytes(await upload.read())
        saved_files.append({"filename": filename, "path": str(destination)})

    background_tasks.add_task(
        run_upload_ingestion_job,
        job["job_id"],
        saved_files,
        ident["user_id"],
        ident["session_id"],
        source_id,
        str(job_dir),
    )

    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "message": job["message"],
        "signed_in": ident["signed_in"],
        "expires_in_seconds": settings.SESSION_TTL_SECONDS,
    }


@app.get("/api/jobs/{job_id}")
def job_status(
    job_id: str,
    session_id: Optional[str] = Query(default=None),
    user: Dict[str, Any] = Depends(auth_user),
) -> Dict[str, Any]:
    job = get_job(job_id)
    authorize_job(job, session_id, user)
    return job


@app.post("/api/search")
def search_documents(
    payload: SearchRequest,
    user: Dict[str, Any] = Depends(auth_user),
) -> Dict[str, Any]:
    ident = identity(payload.session_id, user)
    raw_results = searcher().search(
        payload.query,
        top_k=max(payload.top_k * 3, payload.top_k),
        user_id=ident["user_id"],
        session_id=ident["session_id"],
    )
    filtered = [result for result in raw_results if result["similarity"] >= payload.similarity_threshold]
    docs = aggregator().aggregate_by_document(filtered, max_chunks_per_doc=3)
    return {
        "documents": docs,
        "chunks": [chunk for doc in docs for chunk in doc["chunks"]],
        "count": len(docs),
    }


@app.post("/api/chat")
def chat_documents(payload: ChatRequest) -> Dict[str, Any]:
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="question is required.")
    if not payload.chunks:
        raise HTTPException(status_code=400, detail="Run a search first so chat has document context.")

    chat_client = chat()
    chat_client.healthcheck()
    return {"answer": chat_client.answer(payload.question, payload.chunks)}


@app.post("/api/cleanup-expired-vectors")
def cleanup_expired_vectors(
    request: Request,
    payload: CleanupRequest = CleanupRequest(),
    cleanup_secret: Optional[str] = Header(default=None, alias="X-Cleanup-Secret"),
) -> Dict[str, Any]:
    configured_secret = getattr(settings, "CLEANUP_SECRET", "")
    provided_secret = cleanup_secret or payload.secret
    if configured_secret and provided_secret != configured_secret:
        raise HTTPException(status_code=403, detail="Invalid cleanup secret.")

    store = pipeline()
    before = store.get_status()["total_chunks"]
    store.cleanup_expired()
    after = store.get_status()["total_chunks"]
    return {
        "ok": True,
        "before": before,
        "after": after,
        "deleted": max(before - after, 0),
        "path": str(request.url.path),
    }


if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{full_path:path}")
def serve_frontend(full_path: str):
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found.")

    target = FRONTEND_DIST / full_path
    if target.exists() and target.is_file():
        return FileResponse(target)

    index_file = FRONTEND_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)

    return {
        "message": "React frontend has not been built yet.",
        "build_command": "cd frontend && npm install && npm run build",
    }
