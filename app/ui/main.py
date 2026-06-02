import html
import sys
import time
from pathlib import Path
from textwrap import dedent
from uuid import uuid4

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import settings
from app.auth.supabase_auth import get_auth_client
from app.ingestion.ingest import get_pipeline
from app.retrieval.aggregator import get_aggregator
from app.retrieval.chat import get_document_chat
from app.retrieval.search import get_searcher
from app.sources.connectors import get_source_connector


st.set_page_config(
    page_title="SourceLink AI",
    page_icon="SL",
    layout="wide",
    initial_sidebar_state="collapsed",
)


def inject_styles() -> None:
    st.html(
        dedent(
            """
        <style>
        :root {
            --ink: #101828;
            --muted: #667085;
            --line: #e6e9ef;
            --soft: #f7f8fb;
            --violet: #7047eb;
            --pink: #d946ef;
            --cyan: #06b6d4;
            --green: #10b981;
        }

        .stApp {
            background: #f8fafc;
            color: var(--ink);
        }

        .block-container {
            max-width: 1180px;
            padding-top: 1.1rem;
            padding-bottom: 3rem;
        }

        section[data-testid="stSidebar"] {
            background: #ffffff;
            border-right: 1px solid var(--line);
        }

        h1, h2, h3, p {
            letter-spacing: 0;
        }

        div[data-testid="stButton"] > button,
        div[data-testid="stDownloadButton"] > button,
        a[data-testid="stLinkButton"] {
            border-radius: 10px;
            min-height: 42px;
            font-weight: 700;
            border: 1px solid #ded7ff;
            box-shadow: none;
            background: #ffffff;
            color: #111827 !important;
        }

        div[data-testid="stButton"] > button[kind="primary"] {
            background: linear-gradient(135deg, var(--violet), var(--pink));
            border: 0;
            color: #ffffff !important;
        }

        div[data-testid="stButton"] > button[kind="primary"] *,
        div[data-testid="stButton"] > button[kind="secondary"] *,
        div[data-testid="stDownloadButton"] > button *,
        a[data-testid="stLinkButton"] * {
            color: inherit !important;
        }

        div[data-testid="stButton"] > button[kind="secondary"] {
            background: #ffffff !important;
            color: #111827 !important;
            border: 1px solid #ded7ff !important;
        }

        section[data-testid="stSidebar"] div[data-testid="stButton"] > button {
            background: #ffffff !important;
            color: #111827 !important;
            border: 1px solid #e6e9ef !important;
        }

        div[data-testid="stFileUploader"] button {
            background: #ffffff !important;
            color: #111827 !important;
            border: 1px solid #ded7ff !important;
        }

        div[data-testid="stFileUploader"] button * {
            color: #111827 !important;
        }

        div[data-testid="stTextInput"] input {
            border-radius: 12px;
            min-height: 48px;
            border-color: var(--line);
            background: #ffffff;
            color: #111827;
        }

        div[data-testid="stTextInput"] input::placeholder {
            color: #8b95a7;
        }

        div[data-testid="stFileUploader"] section {
            border-radius: 16px;
            border: 1.5px dashed #d8ddec;
            background: #fbfcff;
            min-height: 108px;
        }

        div[data-testid="stExpander"] {
            border: 1px solid var(--line);
            border-radius: 16px;
            overflow: hidden;
            background: #ffffff;
            box-shadow: 0 14px 40px rgba(16, 24, 40, 0.05);
        }

        .app-shell {
            width: 100%;
        }

        .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin: 0 auto 4.8rem auto;
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
            font-weight: 800;
            color: #111827;
            font-size: 1.05rem;
        }

        .brand-mark {
            width: 42px;
            height: 42px;
            display: grid;
            place-items: center;
            border-radius: 14px;
            color: #ffffff;
            font-weight: 900;
            background: linear-gradient(135deg, #6d5dfc, #e250d5);
            box-shadow: 0 14px 30px rgba(112, 71, 235, 0.24);
        }

        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 9px;
            padding: 8px 16px;
            border-radius: 999px;
            border: 1px solid var(--line);
            background: rgba(255, 255, 255, 0.82);
            color: #6b7280;
            font-size: 0.86rem;
            font-weight: 700;
        }

        .dot {
            width: 9px;
            height: 9px;
            border-radius: 999px;
            background: linear-gradient(135deg, var(--violet), var(--cyan));
        }

        .hero {
            text-align: center;
            margin: 0 auto 2.8rem auto;
        }

        .hero h1 {
            max-width: 860px;
            margin: 1.7rem auto 1.2rem auto;
            font-size: clamp(3.2rem, 6vw, 5.7rem);
            line-height: 0.98;
            font-weight: 900;
            color: #111827;
        }

        .hero-gradient {
            display: block;
            background: linear-gradient(135deg, #6545f5 0%, #b34df0 48%, #e250d5 100%);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
        }

        .hero p {
            max-width: 760px;
            margin: 0 auto;
            font-size: 1.18rem;
            line-height: 1.55;
            color: var(--muted);
        }

        .feature-grid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 18px;
            max-width: 840px;
            margin: 2.8rem auto 3.2rem auto;
        }

        .feature-card {
            background: #ffffff;
            border: 1px solid var(--line);
            border-radius: 16px;
            padding: 24px;
            min-height: 130px;
            box-shadow: 0 20px 44px rgba(16, 24, 40, 0.06);
        }

        .feature-icon {
            color: var(--violet);
            font-size: 1.55rem;
            line-height: 1;
            margin-bottom: 20px;
        }

        .feature-title {
            color: #1f2937;
            font-weight: 800;
            margin-bottom: 4px;
        }

        .feature-copy {
            color: var(--muted);
            font-size: 0.92rem;
        }

        .panel {
            background: #ffffff;
            border: 1px solid var(--line);
            border-radius: 18px;
            padding: 28px;
            box-shadow: 0 24px 60px rgba(16, 24, 40, 0.07);
            margin-bottom: 24px;
        }

        .panel-title {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 18px;
            margin-bottom: 18px;
        }

        .panel-title h2 {
            font-size: 1.25rem;
            margin: 0;
            color: #111827;
        }

        .panel-title p {
            margin: 4px 0 0 0;
            color: var(--muted);
        }

        .metric-row {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 14px;
            margin: 10px 0 26px 0;
        }

        .mini-metric {
            border: 1px solid var(--line);
            border-radius: 14px;
            padding: 15px 16px;
            background: #fbfcff;
        }

        .mini-metric strong {
            display: block;
            font-size: 1.25rem;
            color: #111827;
        }

        .mini-metric span {
            color: var(--muted);
            font-size: 0.84rem;
        }

        .section-kicker {
            color: var(--violet);
            font-weight: 800;
            margin-bottom: 8px;
            font-size: 0.82rem;
            text-transform: uppercase;
        }

        .excerpt-box {
            border: 1px solid #e9ecf3;
            border-radius: 14px;
            padding: 16px;
            background: #fbfcff;
            margin: 12px 0;
        }

        .excerpt-meta {
            color: var(--muted);
            font-size: 0.84rem;
            font-weight: 700;
            margin-bottom: 8px;
        }

        .excerpt-text {
            color: #1f2937;
            line-height: 1.55;
        }

        @media (max-width: 780px) {
            .topbar {
                margin-bottom: 2.8rem;
            }
            .hero h1 {
                font-size: 3rem;
            }
            .feature-grid,
            .metric-row {
                grid-template-columns: 1fr;
            }
            .panel {
                padding: 20px;
            }
        }
        </style>
        """
        ),
    )


def initialize_state() -> None:
    if "pipeline" not in st.session_state:
        st.session_state.pipeline = get_pipeline()
        st.session_state.searcher = get_searcher()
        st.session_state.aggregator = get_aggregator()
        st.session_state.chat = get_document_chat()
        st.session_state.last_chunks = []
        st.session_state.last_documents = []
    if "auth_session" not in st.session_state:
        st.session_state.auth_session = None
    if "anon_user_id" not in st.session_state:
        st.session_state.anon_user_id = f"anon:{uuid4().hex}"


def current_user() -> dict:
    session = st.session_state.get("auth_session")
    if not session:
        return {}
    return session.user


def current_user_id() -> str:
    return current_user().get("id", "") or st.session_state.get("anon_user_id", "")


def is_signed_in() -> bool:
    return bool(st.session_state.get("auth_session"))


def anonymous_repo_limit_mb() -> int:
    return int(getattr(settings, "ANONYMOUS_REPO_LIMIT_MB", 100))


def render_auth_form(location: str = "main") -> None:
    if not settings.SUPABASE_URL or not settings.SUPABASE_ANON_KEY:
        st.info("Supabase Auth is not configured yet.")
        return

    auth_mode = st.radio(
        "Account",
        ["Sign in", "Sign up"],
        horizontal=True,
        label_visibility="collapsed",
        key=f"{location}_auth_mode",
    )
    email = st.text_input("Email", key=f"{location}_auth_email")
    password = st.text_input("Password", type="password", key=f"{location}_auth_password")

    if st.button(auth_mode, type="primary", use_container_width=True, key=f"{location}_auth_button"):
        if not email.strip() or not password:
            st.warning("Enter both email and password.")
        else:
            try:
                auth_client = get_auth_client()
                if auth_mode == "Sign up":
                    result = auth_client.sign_up(email.strip(), password)
                    if result.session:
                        st.session_state.auth_session = result.session
                        st.success("Account created. You are signed in.")
                        st.rerun()
                    else:
                        st.success("Account created. Check your email if Supabase requires confirmation, then sign in.")
                        return
                else:
                    session = auth_client.sign_in(email.strip(), password)
                    st.session_state.auth_session = session
                    st.success("Signed in.")
                    st.rerun()
            except Exception as exc:
                st.error(f"Authentication error: {exc}")


def ingest_uploaded_files(uploaded_files) -> None:
    with st.spinner("Indexing uploaded files..."):
        progress_bar = st.progress(0)
        total_chunks = 0
        user_id = current_user_id()
        source_id = f"upload_batch:{user_id}:{uuid4().hex[:12]}"

        for index, uploaded_file in enumerate(uploaded_files):
            temp_path = settings.RAW_DATA_DIR / uploaded_file.name
            with open(temp_path, "wb") as file:
                file.write(uploaded_file.getbuffer())

            try:
                num_chunks = st.session_state.pipeline.ingest_file(
                    str(temp_path),
                    extra_metadata={
                        "source_type": "upload",
                        "source_path": str(temp_path),
                        "document_id": f"upload:{uploaded_file.name}",
                    },
                    user_id=user_id,
                    source_id=source_id,
                )
                total_chunks += num_chunks
                st.success(f"{uploaded_file.name}: {num_chunks} chunks")
            except Exception as exc:
                st.error(f"{uploaded_file.name}: {exc}")

            progress_bar.progress((index + 1) / len(uploaded_files))

        st.success(f"Indexed {total_chunks} chunks from {len(uploaded_files)} uploaded files.")
        time.sleep(1)
        st.rerun()


def render_document_actions(doc) -> None:
    source_url = doc["metadata"].get("source_url")
    local_file = settings.RAW_DATA_DIR / doc["filename"]

    if source_url:
        st.link_button("Open source", source_url, use_container_width=True)
    elif local_file.exists():
        with open(local_file, "rb") as file:
            st.download_button(
                label="Download file",
                data=file.read(),
                file_name=doc["filename"],
                mime="application/octet-stream",
                use_container_width=True,
            )
    else:
        st.caption("Original file is not available locally.")


def render_results(aggregated_results) -> None:
    for doc in aggregated_results:
        safe_filename = html.escape(doc["filename"])
        with st.expander(
            f"{doc['filename']}  |  relevance {doc['relevance_score']:.3f}",
            expanded=True,
        ):
            meta_col, size_col, match_col, action_col = st.columns(4)
            with meta_col:
                st.caption(f"Source: {doc['metadata'].get('source_type', 'local')}")
            with size_col:
                st.caption(f"Type: {doc['metadata'].get('file_type', 'unknown')}")
            with match_col:
                st.caption(f"Matches: {doc['num_matching_chunks']}")
            with action_col:
                render_document_actions(doc)

            st.markdown(f"**Relevant excerpts from {safe_filename}**")
            for index, chunk in enumerate(doc["chunks"], start=1):
                text = html.escape(chunk["text"])
                similarity = chunk["similarity"]
                chunk_index = chunk["metadata"].get("chunk_index", 0)
                st.html(
                    dedent(
                        f"""
                    <div class="excerpt-box">
                        <div class="excerpt-meta">Excerpt {index} - similarity {similarity:.3f} - chunk #{chunk_index}</div>
                        <div class="excerpt-text">{text}</div>
                    </div>
                    """
                    ),
                )


def render_sidebar() -> None:
    with st.sidebar:
        st.header("Controls")
        user = current_user()
        if user:
            st.caption(f"Signed in as {user.get('email', user.get('id', 'user'))}")
            if st.button("Sign out", use_container_width=True):
                try:
                    auth_client = get_auth_client()
                    auth_client.sign_out(st.session_state.auth_session.access_token)
                except Exception:
                    pass
                st.session_state.auth_session = None
                st.session_state.last_chunks = []
                st.session_state.last_documents = []
                st.rerun()
        else:
            st.caption("Anonymous session")
            st.caption(f"Repos up to {anonymous_repo_limit_mb()} MB can be indexed without sign-in.")
            with st.expander("Sign in for larger repos"):
                render_auth_form("sidebar")

        status = st.session_state.pipeline.get_status()
        st.metric("Indexed chunks", status["total_chunks"])
        st.caption(f"Vector DB: {settings.VECTOR_DB_BACKEND}")

        st.divider()

        st.subheader("Local demo data")
        if st.button("Index data/raw", use_container_width=True):
            with st.spinner("Indexing local demo directory..."):
                try:
                    user_id = current_user_id()
                    source_id = f"local_demo:{user_id}"
                    results = st.session_state.pipeline.ingest_directory(
                        str(settings.RAW_DATA_DIR),
                        user_id=user_id,
                        source_id=source_id,
                    )
                    st.success(f"Indexed {len(results)} files.")
                    time.sleep(1)
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

        st.divider()

        st.subheader("Danger zone")
        if st.button("Clear vector index", use_container_width=True):
            if st.session_state.get("confirm_reset", False):
                st.session_state.pipeline.reset_database()
                st.session_state.confirm_reset = False
                st.session_state.pipeline = get_pipeline()
                st.session_state.searcher = get_searcher()
                st.session_state.aggregator = get_aggregator()
                st.session_state.last_chunks = []
                st.session_state.last_documents = []
                st.success("Vector index cleared.")
                time.sleep(1)
                st.rerun()
            else:
                st.session_state.confirm_reset = True
                st.warning("Click again to confirm deletion.")


def render_hero(status_count: int) -> None:
    st.html(
        dedent(
            f"""
        <div class="app-shell">
            <div class="topbar">
                <div class="brand">
                    <div class="brand-mark">SL</div>
                    <div>SourceLink AI</div>
                </div>
                <div class="status-pill"><span class="dot"></span>{status_count} indexed chunks</div>
            </div>

            <section class="hero">
                <div class="status-pill"><span class="dot"></span>Your documents, now an AI assistant</div>
                <h1>
                    Connect your sources.
                    <span class="hero-gradient">Chat with every document.</span>
                </h1>
                <p>
                    Paste a Drive folder, connect a public repository, or upload files.
                    SourceLink indexes the knowledge and answers only from retrieved document context.
                </p>
            </section>

            <div class="feature-grid">
                <div class="feature-card">
                    <div class="feature-icon">01</div>
                    <div class="feature-title">Connect Sources</div>
                    <div class="feature-copy">Google Drive folders, public GitHub repos, and uploads.</div>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">02</div>
                    <div class="feature-title">Index Knowledge</div>
                    <div class="feature-copy">Chunks, embeddings, and source links stay searchable.</div>
                </div>
                <div class="feature-card">
                    <div class="feature-icon">03</div>
                    <div class="feature-title">Ask Questions</div>
                    <div class="feature-copy">Chat with the retrieved files and open originals instantly.</div>
                </div>
            </div>
        </div>
        """
        ),
    )


inject_styles()
initialize_state()
render_sidebar()

status = st.session_state.pipeline.get_status()
render_hero(status["total_chunks"])

if is_signed_in():
    st.success(f"Signed in as {current_user().get('email', current_user_id())}")
else:
    st.info(
        f"Anonymous mode: GitHub repositories up to {anonymous_repo_limit_mb()} MB can be indexed without sign-in. "
        "Sign in for larger repositories and a more stable workspace."
    )

st.html(
    dedent(
        """
    <div class="panel">
        <div class="panel-title">
            <div>
                <div class="section-kicker">Index workspace</div>
                <h2>Add documents to your assistant</h2>
                <p>Use a public source link or upload files directly for this demo.</p>
            </div>
        </div>
    </div>
    """
    ),
)

source_col, upload_col = st.columns([1, 1], gap="large")

with source_col:
    st.markdown("#### Source link")
    st.caption(f"Indexing target: {settings.VECTOR_DB_BACKEND} / {settings.COLLECTION_NAME}")
    source_url = st.text_input(
        "Public GitHub repository or Google Drive link",
        placeholder="https://drive.google.com/drive/folders/...",
        help="Supports public GitHub repositories and public Google Drive file/folder links.",
        label_visibility="collapsed",
    )
    if st.button("Index source link", type="primary", use_container_width=True):
        if not source_url.strip():
            st.warning("Paste a public source link first.")
        else:
            with st.spinner("Fetching and indexing source files..."):
                try:
                    clean_source_url = source_url.strip()
                    source_connector = get_source_connector()
                    repo_limit_mb = anonymous_repo_limit_mb()
                    requires_auth, size_mb = source_connector.requires_auth_for_anonymous(
                        clean_source_url,
                        repo_limit_mb,
                    )
                    if requires_auth and not is_signed_in():
                        st.warning(
                            f"This GitHub repository is about {size_mb:.1f} MB. "
                            f"Sign in to index repositories over {repo_limit_mb} MB."
                        )
                    else:
                        user_id = current_user_id()
                        results = st.session_state.pipeline.ingest_source_url(clean_source_url, user_id=user_id)
                        if results:
                            st.success(f"Indexed {len(results)} files.")
                            for filename, count in results.items():
                                st.write(f"{filename}: {count} chunks")
                        else:
                            st.warning("No supported files found in that source.")
                        time.sleep(1)
                        st.rerun()
                except Exception as exc:
                    st.error(str(exc))

with upload_col:
    st.markdown("#### Upload files")
    st.caption(f"Indexing target: {settings.VECTOR_DB_BACKEND} / {settings.COLLECTION_NAME}")
    uploaded_files = st.file_uploader(
        "Upload PDF, TXT, DOCX, or Markdown",
        type=["pdf", "txt", "docx", "md"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
    if st.button("Index uploaded files", use_container_width=True):
        if uploaded_files:
            ingest_uploaded_files(uploaded_files)
        else:
            st.warning("Upload at least one file first.")

st.html(
    dedent(
        f"""
    <div class="metric-row">
        <div class="mini-metric"><strong>{status["total_chunks"]}</strong><span>Indexed chunks</span></div>
        <div class="mini-metric"><strong>{html.escape(settings.VECTOR_DB_BACKEND)}</strong><span>Vector backend</span></div>
        <div class="mini-metric"><strong>{html.escape(settings.EMBEDDING_PROVIDER)}</strong><span>Embedding provider</span></div>
        <div class="mini-metric"><strong>{html.escape(settings.CHAT_PROVIDER)}</strong><span>Chat provider</span></div>
    </div>
    """
    ),
)

st.html(
    dedent(
        """
    <div class="panel">
        <div class="panel-title">
            <div>
                <div class="section-kicker">Semantic search</div>
                <h2>Find the most relevant files</h2>
                <p>Search across all indexed chunks, then open the source or ask follow-up questions.</p>
            </div>
        </div>
    </div>
    """
    ),
)

query = st.text_input(
    "Search documents",
    placeholder="Ask about a topic, policy, chapter, API, or concept...",
    label_visibility="collapsed",
)

search_col, top_k_col, threshold_col = st.columns([2, 1, 1])
with search_col:
    search_requested = st.button("Search documents", type="primary", use_container_width=True)
with top_k_col:
    top_k = st.slider("Results", min_value=1, max_value=20, value=5)
with threshold_col:
    similarity_threshold = st.slider("Min similarity", 0.0, 1.0, 0.3, 0.01)

if search_requested and query.strip():
    with st.spinner("Searching indexed documents..."):
        try:
            results = st.session_state.searcher.search(query, top_k=top_k * 3, user_id=current_user_id())
            results = [result for result in results if result["similarity"] >= similarity_threshold]

            if not results:
                st.session_state.last_chunks = []
                st.session_state.last_documents = []
                st.warning("No results found. Try a broader query or lower the similarity threshold.")
            else:
                aggregated = st.session_state.aggregator.aggregate_by_document(results, max_chunks_per_doc=3)
                st.session_state.last_chunks = [chunk for doc in aggregated for chunk in doc["chunks"]]
                st.session_state.last_documents = aggregated
                st.success(f"Found {len(aggregated)} relevant documents.")
                render_results(aggregated)
        except Exception as exc:
            st.error(f"Search error: {exc}")
elif st.session_state.last_documents:
    render_results(st.session_state.last_documents)

st.html(
    dedent(
        """
    <div class="panel">
        <div class="panel-title">
            <div>
                <div class="section-kicker">Document chat</div>
                <h2>Ask the retrieved context</h2>
                <p>The answer is grounded in the files returned by your most recent search.</p>
            </div>
        </div>
    </div>
    """
    ),
)

chat_question = st.text_input(
    "Ask a follow-up",
    placeholder="What should I know from the returned documents?",
    label_visibility="collapsed",
)

if st.button("Ask retrieved context", use_container_width=True):
    if not chat_question.strip():
        st.warning("Enter a follow-up question first.")
    elif not st.session_state.last_chunks:
        st.warning("Run a search first so the chat has document context.")
    else:
        with st.spinner("Asking the chat model..."):
            try:
                st.session_state.chat.healthcheck()
                answer = st.session_state.chat.answer(chat_question, st.session_state.last_chunks)
                st.success(answer)
            except Exception as exc:
                st.error(f"Chat model error: {exc}")
                if settings.CHAT_PROVIDER.lower() == "groq":
                    st.info("Make sure GROQ_API_KEY is set in .env and CHAT_MODEL is available in your Groq account.")
                else:
                    st.info(f"Make sure Ollama is running and the chat model is installed: ollama pull {settings.CHAT_MODEL}")

st.caption(
    f"Embeddings: {settings.EMBEDDING_PROVIDER} {settings.EMBEDDING_MODEL} - "
    f"Chat: {settings.CHAT_PROVIDER} {settings.CHAT_MODEL} - "
    f"Vector DB: {settings.VECTOR_DB_BACKEND}"
)
