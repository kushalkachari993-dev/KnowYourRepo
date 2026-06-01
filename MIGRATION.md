Migration Toward The Demo Goal
==============================

Goal
----

Build a deployable demo where users connect document sources, index them, search semantically, open the original source, and chat with retrieved document context.

The app should avoid storing original files unless the user explicitly uploads them. For linked sources, it stores:

- chunk text
- embedding vectors
- document metadata
- source references such as Drive/GitHub URLs

Current State
-------------

The app now supports:

- public GitHub repository ingestion
- public Google Drive file ingestion
- public Google Drive folder ingestion through `gdown`
- upload-based ingestion
- local `data/raw` ingestion
- retrieved-document chat with a local Ollama chat model
- a vector store interface so Chroma can later be swapped out

Available vector backends:

```text
VECTOR_DB_BACKEND=chroma
VECTOR_DB_BACKEND=zilliz
```

Cloud Migration Path
--------------------

Recommended demo stack:

```text
App hosting: Hugging Face Spaces or Render
Source files: stay in Google Drive / GitHub
Metadata: vector DB metadata first, Supabase later if auth is added
Vector DB: Zilliz Cloud or Qdrant Cloud
Embeddings: local sentence-transformers on the app server, or Ollama on a VPS
Chat: local small model on VPS, or API-based model for hosted demos
```

Zilliz Setup
------------

Install dependencies:

```powershell
pip install -r requirements.txt
```

Create a free Zilliz Cloud cluster, then set:

Expected environment variables:

```text
VECTOR_DB_BACKEND=zilliz
ZILLIZ_URI=<your-zilliz-endpoint>
ZILLIZ_TOKEN=<your-zilliz-token>
COLLECTION_NAME=vectorEMBD
EMBEDDING_PROVIDER=huggingface
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIMENSION=384
CHAT_PROVIDER=groq
CHAT_MODEL=llama-3.1-8b-instant
GROQ_API_KEY=<your-groq-api-key>
```

These can be placed in `.env` at the project root. The app loads `.env` automatically through `python-dotenv`.

The Zilliz backend stores:

- vector
- chunk text
- filename
- source_url
- source_type
- document_id
- other scalar metadata

Keep secrets and OAuth tokens outside Zilliz.

Next Code Step
--------------

Add user identity and source ownership metadata:

```text
user_id
source_id
tenant_id
```

Then filter search results by user/source so one user's indexed chunks cannot appear for another user.

Production Notes
----------------

For a public demo, public Drive/GitHub links are enough.

For real users, use OAuth:

- Google Drive API for private Drive access
- GitHub OAuth or GitHub App installation for private repos
- Supabase Auth for app users

For original files:

- Keep linked source files in Drive/GitHub.
- Store only source references in vector metadata.
- Use Supabase Storage only for manual uploads that need persistence.
