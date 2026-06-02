import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config.settings import settings
from app.ingestion.ingest import get_pipeline
from app.retrieval.aggregator import get_aggregator
from app.retrieval.chat import get_document_chat
from app.retrieval.search import get_searcher


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an end-to-end smoke test.")
    parser.add_argument("--source-url", required=True, help="Public Drive/GitHub source URL to index.")
    parser.add_argument("--query", default="machine learning", help="Query to test retrieval.")
    parser.add_argument("--user-id", default="e2e_test_user_codex", help="Synthetic user ID for isolation testing.")
    parser.add_argument("--source-id", default="e2e_test_source_codex", help="Synthetic source ID for metadata.")
    args = parser.parse_args()

    print("CONFIG")
    print(f"vector={settings.VECTOR_DB_BACKEND} collection={settings.COLLECTION_NAME}")
    print(f"embedding={settings.EMBEDDING_PROVIDER} model={settings.EMBEDDING_MODEL} dim={settings.EMBEDDING_DIMENSION}")
    print(f"chat={settings.CHAT_PROVIDER} model={settings.CHAT_MODEL}")
    print(f"supabase_configured={bool(settings.SUPABASE_URL)} {bool(settings.SUPABASE_ANON_KEY)}")

    pipeline = get_pipeline()
    print(f"status_before={pipeline.get_status()}")

    print("\nINGEST")
    results = pipeline.ingest_source_url(args.source_url, user_id=args.user_id, source_id=args.source_id)
    print(f"files_indexed={len(results)}")
    print(f"chunk_counts={results}")
    print(f"total_indexed_this_run={sum(results.values())}")
    print(f"status_after={pipeline.get_status()}")

    print("\nSEARCH")
    searcher = get_searcher()
    search_results = searcher.search(args.query, top_k=5, user_id=args.user_id)
    print(f"search_count={len(search_results)}")
    for result in search_results[:3]:
        metadata = result.get("metadata", {})
        preview = result.get("text", "").replace("\n", " ")[:180]
        print(
            "hit="
            f"{result.get('rank')} file={metadata.get('filename')} "
            f"user_id={metadata.get('user_id')} similarity={result.get('similarity')}"
        )
        print(f"preview={preview}")

    wrong_user_results = searcher.search(args.query, top_k=5, user_id="e2e_wrong_user_codex")
    print(f"wrong_user_search_count={len(wrong_user_results)}")

    print("\nCHAT")
    aggregated = get_aggregator().aggregate_by_document(search_results, max_chunks_per_doc=3)
    chunks = [chunk for doc in aggregated for chunk in doc["chunks"]]
    answer = get_document_chat().answer(
        "Summarize the most relevant retrieved context in two sentences.",
        chunks,
        max_context_chars=2500,
    )
    print(f"chat_answer={answer[:500].replace(chr(10), ' ')}")


if __name__ == "__main__":
    main()
