# from app.retrieval.search import get_searcher
# from app.retrieval.aggregator import get_aggregator

# searcher = get_searcher()

# # Test different queries
# queries = [
#     "machine learning",
#     "python programming",
#     "deep learning neural networks",
#     "variance analysis"
# ]

# for query in queries:
#     print(f"\n{'='*60}")
#     print(f"Query: '{query}'")
#     print('='*60)
    
#     results = searcher.search(query, top_k=3)
    
#     if results:
#         for result in results:
#             print(f"\nRank {result['rank']} - Similarity: {result['similarity']:.3f}")
#             print(f"  File: {result['metadata']['filename']}")
#             print(f"  Text: {result['text'][:100]}...")
#     else:
#         print("No results found")

# print("\n" + "="*60)
# print("AGGREGATED VIEW")
# print("="*60)

# results = searcher.search("machine learning", top_k=10)
# aggregator = get_aggregator()
# aggregated = aggregator.aggregate_by_document(results)

# for doc in aggregated:
#     print(f"\n📄 {doc['filename']}")
#     print(f"   Relevance: {doc['relevance_score']:.3f}")
#     print(f"   Matches: {doc['num_matching_chunks']}")

import shutil
from pathlib import Path
from app.config.settings import settings
from app.ingestion.ingest import get_pipeline

# 1. Delete the entire ChromaDB directory
# force_reset_v2.py
import shutil
from pathlib import Path
from app.config.settings import settings

# 1. Delete the entire ChromaDB directory
chroma_dir = Path(settings.CHROMA_PERSIST_DIR)
if chroma_dir.exists():
    print(f"🗑️  Deleting old ChromaDB at {chroma_dir}")
    shutil.rmtree(chroma_dir)
    print("✓ Deleted")

# Wait for imports to use new code
print("\n📊 Importing fresh modules...")
from app.ingestion.ingest import get_pipeline

# 2. Create fresh pipeline
print("Creating fresh ChromaDB with cosine similarity...")
pipeline = get_pipeline()
status = pipeline.get_status()
print(f"✓ Collection: {status['collection_name']}")
print(f"✓ Chunks: {status['total_chunks']}")
print(f"✓ Metadata: {status['metadata']}")

# 3. Ingest documents
print("\n📂 Ingesting documents...")
results = pipeline.ingest_directory("data/raw/")

print(f"\n✅ Done! Ingested {len(results)} files:")
for filename, count in results.items():
    print(f"  • {filename}: {count} chunks")

final_status = pipeline.get_status()
print(f"\n📊 Final count: {final_status['total_chunks']} chunks")

# 4. Test search immediately
print("\n🔍 Testing search...")
from app.retrieval.search import get_searcher

searcher = get_searcher()
results = searcher.search("machine learning", top_k=3)

if results:
    print(f"✓ Search works! Found {len(results)} results")
    for r in results:
        print(f"  - {r['metadata']['filename']}: similarity {r['similarity']:.3f}")
else:
    print("✗ No results found")