---
title: KnowYourRepo
sdk: docker
app_port: 7860
---

Document Search System
======================

React + FastAPI demo app for indexing document sources, searching them semantically, opening the original source file, and chatting with the retrieved document context.

Supported demo sources:

- Public GitHub repository URLs, such as `https://github.com/owner/repo`
- Public Google Drive file and folder links
- Manual uploads through the web UI
- Local demo files in `data/raw`

Current Google Drive note: public folder ingestion uses `gdown`, which is good for demos. Private folders or per-user permissions should use the Google Drive API with OAuth.

Setup
-----

Install dependencies:

```powershell
pip install -r requirements.txt
```

Run Ollama and pull the models you want to use:

```powershell
ollama pull bge-m3
ollama pull llama3.2:3b
```

Optional environment overrides:

```env
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=bge-m3:567m
EMBEDDING_DIMENSION=1024
CHAT_MODEL=llama3.2:3b
VECTOR_DB_BACKEND=chroma
```

For Zilliz Cloud, put this in `.env`:

```env
VECTOR_DB_BACKEND=zilliz
ZILLIZ_URI=your-zilliz-endpoint
ZILLIZ_TOKEN=your-zilliz-token
COLLECTION_NAME=vectorEMBD
SUPABASE_URL=your-supabase-project-url
SUPABASE_ANON_KEY=your-supabase-anon-key
ANONYMOUS_REPO_LIMIT_MB=100
EMBEDDING_PROVIDER=huggingface
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIMENSION=384
CHAT_PROVIDER=groq
CHAT_MODEL=llama-3.1-8b-instant
GROQ_API_KEY=your-groq-api-key
```

`.env` is ignored by git because it contains secrets.

Start the app:

```powershell
uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8010
```

Run the React frontend during local development:

```powershell
cd frontend
npm install
npm run dev
```

Build React for FastAPI to serve:

```powershell
cd frontend
npm run build
```

Scheduled Vector Cleanup
------------------------

Expired vectors are ignored during search, and the deployed cleanup endpoint physically deletes expired rows:

```text
POST /api/cleanup-expired-vectors
```

GitHub Actions calls the Hugging Face Space cleanup endpoint every 15 minutes from:

```text
.github/workflows/cleanup-expired-vectors.yml
```

For protected cleanup, set the same secret in both places:

- Hugging Face Space secret: `CLEANUP_SECRET`
- GitHub repository secret: `CLEANUP_SECRET`


Verify Vector Storage
---------------------

Check which vector store is active and how many chunks are stored:

```powershell
python scripts/check_vector_store.py
```

Run a quick search against the active vector store:

```powershell
python scripts/check_vector_store.py --query "machine learning"
```

How It Works
------------

1. A user provides a source link or uploads files.
2. The app extracts supported documents.
3. Text is chunked and embedded with Ollama.
4. Chunks and metadata are stored in ChromaDB.
5. Search returns relevant chunks grouped by original document.
6. The UI shows excerpts and an `Open source` or `Download file` action.
7. The chat panel answers follow-up questions using the most recent retrieved chunks.

User Isolation
--------------

Supabase Auth is used for sign in/sign up. Every ingested chunk is tagged with:

```text
user_id
source_id
document_id
```

Search filters by `user_id`, so each signed-in user only retrieves their own indexed chunks.

Anonymous users can index GitHub repositories up to `ANONYMOUS_REPO_LIMIT_MB`. Larger repositories require sign-in. Anonymous indexing uses a temporary browser-session user ID, so it is intended for short-lived exploration rather than persistent workspaces.

Migration
---------

This project is being moved toward a deployable source-connected demo. See `MIGRATION.md` for the current architecture, cloud backend plan, and the next vector database migration step.
