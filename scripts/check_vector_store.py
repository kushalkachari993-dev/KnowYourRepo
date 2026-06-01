import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import settings
from app.ingestion.embedder import get_embedder
from app.vectordb.factory import get_vector_store


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the configured vector store.")
    parser.add_argument("--query", help="Optional test query to run against the vector store.")
    parser.add_argument("--top-k", type=int, default=3, help="Number of search results for --query.")
    parser.add_argument("--list-collections", action="store_true", help="List collections when using Zilliz/Milvus.")
    parser.add_argument("--probe-insert", action="store_true", help="Insert one tiny probe row into the active vector store.")
    args = parser.parse_args()

    print(f"Vector backend: {settings.VECTOR_DB_BACKEND}")
    print(f"Collection: {settings.COLLECTION_NAME}")
    print(f"Embedding provider: {settings.EMBEDDING_PROVIDER}")
    print(f"Embedding model: {settings.EMBEDDING_MODEL}")
    print(f"Embedding dimension: {settings.EMBEDDING_DIMENSION}")

    store = get_vector_store()

    if args.list_collections and hasattr(store, "client"):
        list_collections = getattr(store.client, "list_collections", None)
        if callable(list_collections):
            print(f"Available collections: {list_collections()}")

    if args.probe_insert:
        probe_id = "debug_probe_row"
        probe_text = "debug probe document for vector store verification"
        probe_embedding = [0.0] * settings.EMBEDDING_DIMENSION
        probe_embedding[0] = 1.0
        store.add_documents(
            ids=[probe_id],
            documents=[probe_text],
            embeddings=[probe_embedding],
            metadatas=[
                {
                    "filename": "debug_probe.txt",
                    "source_type": "debug",
                    "source_path": "debug_probe",
                    "document_id": "debug_probe",
                    "chunk_index": 0,
                }
            ],
        )
        print("Inserted probe row.")

    info = store.get_collection_info()

    print(f"Stored rows/chunks: {info['count']}")
    print(f"Store metadata: {info['metadata']}")

    if args.query:
        embedder = get_embedder()
        query_embedding = embedder.embed(args.query)
        results = store.similarity_search(query_embedding, top_k=args.top_k)

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        print(f"\nSearch results for: {args.query}")
        if not documents:
            print("No matches returned.")
            return

        for index, (document, metadata, distance) in enumerate(zip(documents, metadatas, distances), start=1):
            filename = metadata.get("filename", "unknown")
            source_type = metadata.get("source_type", "unknown")
            source_path = metadata.get("source_path", "")
            preview = document.replace("\n", " ")[:160]
            print(f"{index}. {filename} | {source_type} | distance={distance:.4f}")
            if source_path:
                print(f"   source_path: {source_path}")
            print(f"   preview: {preview}")


if __name__ == "__main__":
    main()
