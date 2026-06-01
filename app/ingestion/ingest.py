from typing import List, Dict, Any, Optional
from pathlib import Path
import logging
import uuid
import tempfile

from app.ingestion.loader import get_loader
from app.ingestion.chunker import get_chunker
from app.ingestion.embedder import get_embedder
from app.sources.connectors import get_source_connector
from app.vectordb.factory import get_vector_store
from app.config.settings import settings

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format=settings.LOG_FORMAT
)

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """
    End-to-end document ingestion pipeline.
    
    Pipeline stages:
    1. Load documents (PDF, TXT, DOCX, MD)
    2. Chunk text into manageable pieces
    3. Generate embeddings using Ollama
    4. Store in ChromaDB with metadata
    """

    def __init__(
        self,
        chroma_persist_dir: str = None,
        collection_name: str = None,
        use_semantic_chunking: bool = False,
    ):
        """
        Args:
            chroma_persist_dir: Where ChromaDB stores data
            collection_name: ChromaDB collection name
            use_semantic_chunking: Use paragraph-aware chunking
        """
        self.loader = get_loader()
        self.chunker = get_chunker(semantic=use_semantic_chunking)
        self.embedder = get_embedder()
        
        self.vector_store = get_vector_store()
        
        logger.info("✓ Ingestion pipeline initialized")

    def ingest_file(self, file_path: str, extra_metadata: Optional[Dict[str, Any]] = None) -> int:
        """
        Ingest a single document file.
        
        Args:
            file_path: Path to document
            
        Returns:
            Number of chunks ingested
        """
        logger.info(f"Starting ingestion for: {file_path}")
        
        # 1. Load document
        document = self.loader.load(file_path)
        if extra_metadata:
            document["metadata"].update(extra_metadata)
        document["metadata"].setdefault("source_type", "local")
        document["metadata"].setdefault("source_url", "")
        document["metadata"].setdefault("source_root", "")
        document["metadata"].setdefault("source_path", str(file_path))
        document["metadata"].setdefault("document_id", self._document_id(document["metadata"], file_path))
        
        # 2. Chunk document
        chunks = self.chunker.chunk_document(document)
        
        if not chunks:
            logger.warning(f"No chunks created from {file_path}")
            return 0
        
        # 3. Generate embeddings
        chunk_texts = [chunk["text"] for chunk in chunks]
        embeddings = self.embedder.embed_batch(chunk_texts)
        
        # 4. Prepare data for ChromaDB
        ids = [self._generate_chunk_id(file_path, i) for i in range(len(chunks))]
        metadatas = [chunk["metadata"] for chunk in chunks]
        
        # 5. Store in vector database
        self.vector_store.add_documents(
            ids=ids,
            documents=chunk_texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        
        logger.info(f"✓ Ingested {len(chunks)} chunks from {Path(file_path).name}")
        
        return len(chunks)

    def ingest_directory(self, directory_path: str) -> Dict[str, int]:
        """
        Ingest all supported documents from a directory.
        
        Args:
            directory_path: Path to directory containing documents
            
        Returns:
            Dictionary mapping filename -> number of chunks ingested
        """
        logger.info(f"Starting batch ingestion from: {directory_path}")
        
        dir_path = Path(directory_path)
        
        if not dir_path.exists() or not dir_path.is_dir():
            raise ValueError(f"Invalid directory: {directory_path}")
        
        results = {}
        total_chunks = 0
        
        # Get all supported files
        supported_files = [
            f for f in dir_path.iterdir()
            if f.is_file() and f.suffix.lower() in settings.SUPPORTED_FILE_TYPES
        ]
        
        logger.info(f"Found {len(supported_files)} supported documents")
        
        for file_path in supported_files:
            try:
                num_chunks = self.ingest_file(
                    str(file_path),
                    extra_metadata={
                        "source_type": "local",
                        "source_path": str(file_path),
                        "document_id": f"local:{file_path.resolve()}",
                    },
                )
                results[file_path.name] = num_chunks
                total_chunks += num_chunks
            except Exception as e:
                logger.error(f"Failed to ingest {file_path.name}: {e}")
                results[file_path.name] = 0
        
        logger.info(f"✓ Batch ingestion complete: {total_chunks} total chunks from {len(results)} files")
        
        return results

    def ingest_documents(self, documents: Dict[str, Dict[str, Any]]) -> int:
        """
        Ingest pre-loaded documents (from DocumentLoader.load_directory()).
        
        Args:
            documents: Dictionary mapping filename -> document data
            
        Returns:
            Total number of chunks ingested
        """
        logger.info(f"Ingesting {len(documents)} pre-loaded documents")
        
        total_chunks = 0
        
        for filename, doc_data in documents.items():
            try:
                # Chunk document
                chunks = self.chunker.chunk_document(doc_data)
                
                if not chunks:
                    continue
                
                # Generate embeddings
                chunk_texts = [chunk["text"] for chunk in chunks]
                embeddings = self.embedder.embed_batch(chunk_texts)
                
                # Prepare for ChromaDB
                ids = [self._generate_chunk_id(filename, i) for i in range(len(chunks))]
                metadatas = [chunk["metadata"] for chunk in chunks]
                
                # Store
                self.vector_store.add_documents(
                    ids=ids,
                    documents=chunk_texts,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )
                
                total_chunks += len(chunks)
                logger.info(f"✓ Ingested {len(chunks)} chunks from {filename}")
                
            except Exception as e:
                logger.error(f"Failed to ingest {filename}: {e}")
        
        logger.info(f"✓ Total ingestion: {total_chunks} chunks")
        
        return total_chunks

    def ingest_source_url(self, source_url: str) -> Dict[str, int]:
        """
        Ingest supported documents from a public source URL.

        Demo sources:
        - Public GitHub repository URL
        - Public Google Drive file URL
        """
        connector = get_source_connector()
        results = {}

        with tempfile.TemporaryDirectory(prefix="document_source_") as temp_dir:
            source_documents = connector.fetch(source_url, Path(temp_dir))

            if not source_documents:
                return results

            for source_document in source_documents:
                try:
                    num_chunks = self.ingest_file(
                        str(source_document.path),
                        extra_metadata=source_document.metadata,
                    )
                    display_name = source_document.metadata.get("source_path", source_document.path.name)
                    results[display_name] = num_chunks
                except Exception as e:
                    logger.error("Failed to ingest %s: %s", source_document.path.name, e)
                    results[source_document.path.name] = 0

        return results

    def _generate_chunk_id(self, source: str, chunk_index: int) -> str:
        """
        Generate unique ID for a chunk.
        
        Format: {source_name}_{chunk_index}_{uuid}
        """
        source_name = Path(source).stem  # filename without extension
        unique_id = str(uuid.uuid4())[:8]  # Short UUID
        
        return f"{source_name}_chunk{chunk_index}_{unique_id}"

    def _document_id(self, metadata: Dict[str, Any], file_path: str) -> str:
        source_url = metadata.get("source_url")
        if source_url:
            return source_url

        return f"local:{Path(file_path).resolve()}"

    def get_status(self) -> Dict[str, Any]:
        """
        Get current status of the vector database.
        
        Returns:
            Dictionary with collection info and document count
        """
        info = self.vector_store.get_collection_info()
        
        return {
            "collection_name": info["name"],
            "total_chunks": info["count"],
            "metadata": info["metadata"],
        }

    def reset_database(self) -> None:
        """
        Delete all data from the vector database.
        
        WARNING: This is irreversible!
        """
        logger.warning("Resetting vector database - all data will be deleted!")
        self.vector_store.delete_all()
        logger.info("✓ Database reset complete")


# ============================================================
# Convenience Functions
# ============================================================

def ingest_file(file_path: str) -> int:
    """
    Quick function to ingest a single file.
    
    Args:
        file_path: Path to document
        
    Returns:
        Number of chunks ingested
    """
    pipeline = IngestionPipeline()
    return pipeline.ingest_file(file_path)


def ingest_directory(directory_path: str) -> Dict[str, int]:
    """
    Quick function to ingest a directory.
    
    Args:
        directory_path: Path to directory
        
    Returns:
        Dictionary mapping filename -> chunk count
    """
    pipeline = IngestionPipeline()
    return pipeline.ingest_directory(directory_path)


def get_pipeline() -> IngestionPipeline:
    """Returns a configured ingestion pipeline instance."""
    return IngestionPipeline()
