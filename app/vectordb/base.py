from typing import Any, Dict, List, Optional, Protocol


class VectorStore(Protocol):
    """Interface every vector database backend must implement."""

    def add_documents(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        ...

    def similarity_search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        ...

    def delete_all(self) -> None:
        ...

    def delete_where(self, where: Dict[str, Any]) -> None:
        ...

    def get_collection_info(self) -> Dict[str, Any]:
        ...

    def count_documents(self, where: Optional[Dict[str, Any]] = None, active_or_legacy: bool = False) -> int:
        ...
