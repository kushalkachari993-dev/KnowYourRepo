from typing import List, Dict, Any
from collections import defaultdict
import logging

from app.config.settings import settings

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format=settings.LOG_FORMAT
)

logger = logging.getLogger(__name__)


class ResultAggregator:
    """
    Aggregates and ranks search results by document.
    
    Takes raw chunk-level results and groups them by source document,
    computing document-level relevance scores.
    """

    def __init__(self):
        logger.info("ResultAggregator initialized")

    def aggregate_by_document(
        self,
        results: List[Dict[str, Any]],
        max_chunks_per_doc: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Group search results by source document.
        
        Args:
            results: List of chunk-level search results
            max_chunks_per_doc: Max chunks to include per document
            
        Returns:
            List of document-level results, each containing:
                - 'filename': Source document name
                - 'relevance_score': Aggregated relevance
                - 'chunks': Top matching chunks from this document
                - 'metadata': Document metadata
        """
        if not results:
            return []
        
        # Group chunks by stable document identity. Filenames are not enough
        # once the same repo/folder can contain duplicate names.
        doc_groups = defaultdict(list)
        
        for result in results:
            document_key = result['metadata'].get('document_id') or result['metadata'].get('source_url') or result['metadata'].get('filename', 'unknown')
            doc_groups[document_key].append(result)
        
        # Aggregate and rank documents
        aggregated = []
        
        for document_key, chunks in doc_groups.items():
            # Sort chunks by similarity (highest first)
            chunks = sorted(chunks, key=lambda x: x['similarity'], reverse=True)
            
            # Take top N chunks
            top_chunks = chunks[:max_chunks_per_doc]
            
            # Calculate document-level relevance score
            # Use average of top chunks' similarities
            relevance_score = sum(c['similarity'] for c in top_chunks) / len(top_chunks)
            
            # Extract document metadata (from first chunk)
            doc_metadata = self._extract_document_metadata(chunks[0]['metadata'])
            filename = doc_metadata.get('filename', document_key)
            
            aggregated.append({
                'filename': filename,
                'document_id': document_key,
                'relevance_score': relevance_score,
                'num_matching_chunks': len(chunks),
                'chunks': top_chunks,
                'metadata': doc_metadata,
            })
        
        # Sort documents by relevance
        aggregated = sorted(aggregated, key=lambda x: x['relevance_score'], reverse=True)
        
        logger.info(f"✓ Aggregated {len(results)} chunks into {len(aggregated)} documents")
        
        return aggregated

    def _extract_document_metadata(self, chunk_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract document-level metadata from chunk metadata.
        
        Removes chunk-specific fields like chunk_index.
        """
        doc_metadata = chunk_metadata.copy()
        
        # Remove chunk-specific fields
        chunk_fields = ['chunk_index', 'chunk_length']
        for field in chunk_fields:
            doc_metadata.pop(field, None)
        
        return doc_metadata

    def format_for_display(
        self,
        aggregated_results: List[Dict[str, Any]],
        include_chunk_text: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Format aggregated results for UI display.
        
        Args:
            aggregated_results: Output from aggregate_by_document()
            include_chunk_text: Whether to include full chunk text
            
        Returns:
            Formatted results suitable for display
        """
        formatted = []
        
        for doc in aggregated_results:
            formatted_doc = {
                'filename': doc['filename'],
                'relevance_score': round(doc['relevance_score'], 3),
                'num_matches': doc['num_matching_chunks'],
                'file_type': doc['metadata'].get('file_type', 'unknown'),
            }
            
            if include_chunk_text:
                formatted_doc['excerpts'] = []
                
                for chunk in doc['chunks']:
                    excerpt = {
                        'text': self._create_excerpt(chunk['text']),
                        'similarity': round(chunk['similarity'], 3),
                        'chunk_index': chunk['metadata'].get('chunk_index', 0),
                    }
                    formatted_doc['excerpts'].append(excerpt)
            
            formatted.append(formatted_doc)
        
        return formatted

    def _create_excerpt(self, text: str, max_length: int = 200) -> str:
        """
        Create a display excerpt from full chunk text.
        
        Truncates long text and adds ellipsis.
        """
        if len(text) <= max_length:
            return text
        
        return text[:max_length].strip() + "..."


# ============================================================
# Convenience Functions
# ============================================================

def aggregate_results(
    results: List[Dict[str, Any]],
    max_chunks_per_doc: int = 3,
) -> List[Dict[str, Any]]:
    """
    Quick function to aggregate search results.
    
    Args:
        results: Raw chunk-level search results
        max_chunks_per_doc: Max chunks to show per document
        
    Returns:
        Document-level aggregated results
    """
    aggregator = ResultAggregator()
    return aggregator.aggregate_by_document(results, max_chunks_per_doc)


def get_aggregator() -> ResultAggregator:
    """Returns a ResultAggregator instance."""
    return ResultAggregator()
