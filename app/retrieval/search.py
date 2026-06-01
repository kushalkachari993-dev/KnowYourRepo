from typing import List, Dict, Any, Optional
import logging

from app.ingestion.embedder import get_embedder
from app.vectordb.factory import get_vector_store
from app.config.settings import settings

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format=settings.LOG_FORMAT
)

logger = logging.getLogger(__name__)


class DocumentSearcher:
    """
    Semantic search over document collection.
    
    Workflow:
    1. Convert query text to embedding
    2. Search vector database for similar chunks
    3. Return ranked results with metadata
    """

    def __init__(
        self,
        chroma_persist_dir: str = None,
        collection_name: str = None,
    ):
        """
        Args:
            chroma_persist_dir: Where ChromaDB stores data
            collection_name: ChromaDB collection name
        """
        self.embedder = get_embedder()
        
        self.vector_store = get_vector_store()
        
        logger.info("✓ DocumentSearcher initialized")

    def search(
        self,
        query: str,
        top_k: int = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for documents similar to the query.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            filter_metadata: Optional metadata filters (e.g., {"file_type": ".pdf"})
            
        Returns:
            List of search results, each containing:
                - 'text': Chunk text
                - 'metadata': Chunk metadata
                - 'similarity': Similarity score (lower distance = higher similarity)
                - 'rank': Result rank (1-indexed)
        """
        if not query or not query.strip():
            logger.warning("Empty query provided")
            return []
        
        top_k = top_k or settings.DEFAULT_TOP_K
        
        logger.info(f"Searching for: '{query[:50]}...' (top_k={top_k})")
        
        # 1. Generate query embedding
        try:
            query_embedding = self.embedder.embed(query)
        except Exception as e:
            logger.error(f"Failed to generate query embedding: {e}")
            raise RuntimeError(f"Query embedding failed: {e}")
        
        # 2. Search vector database
        try:
            raw_results = self.vector_store.similarity_search(
                query_embedding=query_embedding,
                top_k=top_k,
                where=filter_metadata,
            )
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            raise RuntimeError(f"Search failed: {e}")
        
        # 3. Format results
        results = self._format_results(raw_results)
        
        logger.info(f"✓ Found {len(results)} results")
        
        return results

    def _format_results(self, raw_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Convert ChromaDB results to standardized format.
        
        ChromaDB returns:
            {
                'ids': [[...]],
                'documents': [[...]],
                'metadatas': [[...]],
                'distances': [[...]]
            }
        """
        if not raw_results or not raw_results.get('documents'):
            return []
        
        # ChromaDB returns nested lists (batch query support)
        # We only send one query, so take first element
        documents = raw_results['documents'][0]
        metadatas = raw_results['metadatas'][0]
        distances = raw_results['distances'][0]
        
        results = []
        
        for rank, (doc, metadata, distance) in enumerate(zip(documents, metadatas, distances), start=1):
            # Convert cosine distance to similarity
            # Cosine distance: 0 (identical) to 2 (opposite)
            # Cosine similarity: 1 - distance (ranges 0 to 1)
            similarity = 1.0 - distance
            
            result = {
                'text': doc,
                'metadata': metadata,
                'distance': distance,
                'similarity': similarity,
                'rank': rank,
            }
            
            results.append(result)
        
        return results

    def search_with_threshold(
        self,
        query: str,
        top_k: int = None,
        similarity_threshold: float = None,
    ) -> List[Dict[str, Any]]:
        """
        Search and filter by minimum similarity threshold.
        
        Args:
            query: Search query
            top_k: Max results to return
            similarity_threshold: Minimum similarity score (0-1)
            
        Returns:
            Filtered search results
        """
        threshold = similarity_threshold or settings.SIMILARITY_THRESHOLD
        
        results = self.search(query, top_k)
        
        # Filter by threshold
        filtered_results = [
            r for r in results
            if r['similarity'] >= threshold
        ]
        
        logger.info(
            f"Filtered {len(results)} -> {len(filtered_results)} results "
            f"(threshold={threshold})"
        )
        
        return filtered_results

    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the indexed documents.
        
        Returns:
            Dictionary with collection metadata
        """
        return self.vector_store.get_collection_info()


# ============================================================
# Convenience Function
# ============================================================

def search_documents(
    query: str,
    top_k: int = None,
) -> List[Dict[str, Any]]:
    """
    Quick search function.
    
    Args:
        query: Search query
        top_k: Number of results
        
    Returns:
        Search results
    """
    searcher = DocumentSearcher()
    return searcher.search(query, top_k)


def get_searcher() -> DocumentSearcher:
    """Returns a configured DocumentSearcher instance."""
    return DocumentSearcher()
