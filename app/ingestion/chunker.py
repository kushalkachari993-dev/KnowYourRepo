from typing import List, Dict, Any
import logging
import re

from app.config.settings import settings

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format=settings.LOG_FORMAT
)

logger = logging.getLogger(__name__)


class TextChunker:
    """
    Smart text chunking with overlap.
    
    Splits documents into manageable chunks for embedding while:
    - Preserving sentence boundaries
    - Adding overlap between chunks for context continuity
    - Maintaining metadata for each chunk
    """

    def __init__(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None,
    ):
        """
        Args:
            chunk_size: Target characters per chunk (default: from settings)
            chunk_overlap: Overlap between consecutive chunks (default: from settings)
        """
        self.chunk_size = chunk_size or settings.CHUNK_SIZE
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
        
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        
        logger.info(
            f"TextChunker initialized: chunk_size={self.chunk_size}, "
            f"overlap={self.chunk_overlap}"
        )

    def chunk_text(
        self,
        text: str,
        metadata: Dict[str, Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        Split text into overlapping chunks.
        
        Args:
            text: Input text to chunk
            metadata: Optional metadata to attach to each chunk
            
        Returns:
            List of chunk dictionaries, each containing:
                - 'text': Chunk text
                - 'metadata': Chunk metadata (includes chunk_index)
        """
        if not text or not text.strip():
            logger.warning("Empty text provided to chunker")
            return []
        
        # Split into sentences for better boundary detection
        sentences = self._split_into_sentences(text)
        
        chunks = []
        current_chunk = []
        current_length = 0
        chunk_index = 0
        
        for sentence in sentences:
            sentence_length = len(sentence)
            
            # If adding this sentence exceeds chunk_size, finalize current chunk
            if current_length + sentence_length > self.chunk_size and current_chunk:
                # Create chunk
                chunk_text = " ".join(current_chunk)
                chunks.append(self._create_chunk(chunk_text, chunk_index, metadata))
                chunk_index += 1
                
                # Start new chunk with overlap
                overlap_text = chunk_text[-self.chunk_overlap:] if len(chunk_text) > self.chunk_overlap else chunk_text
                current_chunk = [overlap_text]
                current_length = len(overlap_text)
            
            # Add sentence to current chunk
            current_chunk.append(sentence)
            current_length += sentence_length + 1  # +1 for space
        
        # Add final chunk
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append(self._create_chunk(chunk_text, chunk_index, metadata))
        
        logger.info(f"✓ Created {len(chunks)} chunks from {len(text)} characters")
        
        return chunks

    def _split_into_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences using regex.
        
        Handles common sentence boundaries like:
        - Period followed by space and capital letter
        - Question marks and exclamation marks
        - Preserves abbreviations like "Dr." and "U.S."
        """
        # Simple sentence splitting pattern
        # Matches: . ! ? followed by space and capital letter
        sentence_pattern = r'(?<=[.!?])\s+(?=[A-Z])'
        
        sentences = re.split(sentence_pattern, text)
        
        # Clean up sentences
        sentences = [s.strip() for s in sentences if s.strip()]
        
        return sentences

    def _create_chunk(
        self,
        text: str,
        chunk_index: int,
        base_metadata: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Create a chunk dictionary with metadata.
        
        Args:
            text: Chunk text
            chunk_index: Index of this chunk in the document
            base_metadata: Base metadata from the document
            
        Returns:
            Dictionary with 'text' and 'metadata' keys
        """
        metadata = base_metadata.copy() if base_metadata else {}
        
        # Add chunk-specific metadata
        metadata.update({
            "chunk_index": chunk_index,
            "chunk_length": len(text),
        })
        
        return {
            "text": text,
            "metadata": metadata,
        }

    def chunk_document(
        self,
        document: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Chunk a loaded document (output from DocumentLoader).
        
        Args:
            document: Dictionary with 'text' and 'metadata' keys
            
        Returns:
            List of chunks with metadata
        """
        text = document.get("text", "")
        metadata = document.get("metadata", {})
        
        return self.chunk_text(text, metadata)

    def chunk_documents(
        self,
        documents: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Chunk multiple documents.
        
        Args:
            documents: Dictionary mapping filename -> document data
            
        Returns:
            Flattened list of all chunks from all documents
        """
        all_chunks = []
        
        for filename, doc_data in documents.items():
            logger.info(f"Chunking document: {filename}")
            chunks = self.chunk_document(doc_data)
            all_chunks.extend(chunks)
        
        logger.info(f"✓ Total chunks created: {len(all_chunks)}")
        
        return all_chunks


# ============================================================
# Advanced Chunking Strategies (Optional)
# ============================================================

class SemanticChunker(TextChunker):
    """
    Advanced chunker that tries to preserve semantic boundaries.
    
    Uses paragraph breaks and section headers as primary split points.
    Falls back to sentence-based chunking when needed.
    """
    
    def chunk_text(
        self,
        text: str,
        metadata: Dict[str, Any] = None,
    ) -> List[Dict[str, Any]]:
        """Override to use paragraph-aware chunking."""
        
        if not text or not text.strip():
            return []
        
        # Split by paragraphs (double newline)
        paragraphs = re.split(r'\n\s*\n', text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
        
        chunks = []
        current_chunk = []
        current_length = 0
        chunk_index = 0
        
        for para in paragraphs:
            para_length = len(para)
            
            # If paragraph itself is too large, split it
            if para_length > self.chunk_size:
                # Finalize current chunk first
                if current_chunk:
                    chunk_text = "\n\n".join(current_chunk)
                    chunks.append(self._create_chunk(chunk_text, chunk_index, metadata))
                    chunk_index += 1
                    current_chunk = []
                    current_length = 0
                
                # Split large paragraph using parent method
                para_chunks = super().chunk_text(para, metadata)
                for pc in para_chunks:
                    pc['metadata']['chunk_index'] = chunk_index
                    chunks.append(pc)
                    chunk_index += 1
                
                continue
            
            # Check if adding this paragraph exceeds limit
            if current_length + para_length > self.chunk_size and current_chunk:
                chunk_text = "\n\n".join(current_chunk)
                chunks.append(self._create_chunk(chunk_text, chunk_index, metadata))
                chunk_index += 1
                current_chunk = []
                current_length = 0
            
            current_chunk.append(para)
            current_length += para_length
        
        # Add final chunk
        if current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            chunks.append(self._create_chunk(chunk_text, chunk_index, metadata))
        
        logger.info(f"✓ Semantic chunking: {len(chunks)} chunks created")
        
        return chunks


# ============================================================
# Global Chunker Instance
# ============================================================
_chunker_instance = None


def get_chunker(semantic: bool = False) -> TextChunker:
    """
    Returns a chunker instance.
    
    Args:
        semantic: If True, returns SemanticChunker (paragraph-aware)
                  If False, returns standard TextChunker
    """
    global _chunker_instance
    
    if _chunker_instance is None:
        if semantic:
            _chunker_instance = SemanticChunker()
        else:
            _chunker_instance = TextChunker()
    
    return _chunker_instance