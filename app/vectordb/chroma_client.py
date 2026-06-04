from typing import List, Dict, Any, Optional
import os

import chromadb
from chromadb.config import Settings


class ChromaClient:
    """
    Centralized ChromaDB client abstraction.

    Responsibilities:
    - Initialize persistent ChromaDB
    - Create / load collections
    - Add document chunks with embeddings
    - Perform similarity search

    This class is the SINGLE point of interaction with ChromaDB.
    """

    def __init__(
        self,
        persist_directory: str,
        collection_name: str = "documents",
        embedding_function=None,
    ):
        """
        Args:
            persist_directory: Path where ChromaDB will persist data
            collection_name: Name of the Chroma collection
            embedding_function: Optional embedding function (NOT required if
                                embeddings are precomputed)
        """

        self.persist_directory = persist_directory
        self.collection_name = collection_name

        os.makedirs(self.persist_directory, exist_ok=True)

        self.client = chromadb.PersistentClient(
        path=self.persist_directory,
        settings=Settings(anonymized_telemetry=False),
        )

        

        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=embedding_function,
            metadata={
                "description": "Semantic document retrieval collection",
                "hnsw:space": "cosine"  # Use cosine similarity (0-1 scale)
            },
        )

    # ------------------------------------------------------------------
    # Ingestion API
    # ------------------------------------------------------------------

    def add_documents(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        """
        Add document chunks to the vector store.

        Args:
            ids: Unique IDs for each chunk
            documents: Chunk text
            embeddings: Precomputed embedding vectors
            metadatas: Metadata per chunk (doc name, page, chunk index, etc.)
        """

        if not (len(ids) == len(documents) == len(embeddings) == len(metadatas)):
            raise ValueError("ids, documents, embeddings, and metadatas must be same length")

        self.collection.add(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    # ------------------------------------------------------------------
    # Retrieval API
    # ------------------------------------------------------------------

    def similarity_search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Perform similarity search using a query embedding.

        Args:
            query_embedding: Embedded query vector
            top_k: Number of nearest neighbors
            where: Optional metadata filter

        Returns:
            Raw ChromaDB query result
        """

        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        return result

    # ------------------------------------------------------------------
    # Utility / Maintenance
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Return number of stored embeddings."""
        return self.collection.count()

    def count_documents(self, where: Optional[Dict[str, Any]] = None, active_or_legacy: bool = False) -> int:
        """Return number of stored embeddings matching a metadata filter."""
        if not where:
            return self.collection.count()

        result = self.collection.get(where=where, include=["metadatas"] if active_or_legacy else [])
        if not active_or_legacy:
            return len(result.get("ids", []))

        import time

        now = int(time.time())
        count = 0
        for metadata in result.get("metadatas", []):
            expires_at = metadata.get("expires_at") if metadata else None
            if expires_at is None:
                count += 1
                continue
            try:
                count += int(expires_at) > now
            except (TypeError, ValueError):
                count += 1
        return count

    def delete_all(self) -> None:
        """Delete all data in the collection."""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={
                "description": "Semantic document retrieval collection",
                "hnsw:space": "cosine"
            },
        )

    def delete_where(self, where: Dict[str, Any]) -> None:
        """Delete documents matching a metadata filter."""
        if not where:
            raise ValueError("delete_where requires a metadata filter")

        self.collection.delete(where=where)

    def get_collection_info(self) -> Dict[str, Any]:
        """Return basic collection metadata."""
        return {
            "name": self.collection.name,
            "count": self.collection.count(),
            "metadata": self.collection.metadata,
        }
