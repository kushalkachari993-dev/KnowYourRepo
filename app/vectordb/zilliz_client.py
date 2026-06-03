from typing import Any, Dict, List, Optional

from app.config.settings import settings


class ZillizClient:
    """
    Zilliz Cloud / Milvus vector store backend.

    Uses pymilvus.MilvusClient. The collection uses quick setup with a string
    primary key, a vector field, and dynamic metadata fields.
    """

    def __init__(
        self,
        uri: str = None,
        token: str = None,
        collection_name: str = None,
        dimension: int = None,
    ):
        try:
            from pymilvus import DataType, MilvusClient
        except ImportError as exc:
            raise RuntimeError("Zilliz backend requires pymilvus. Install requirements.txt again.") from exc

        self.data_type = DataType
        self.uri = uri or settings.ZILLIZ_URI
        self.token = token or settings.ZILLIZ_TOKEN
        self.collection_name = collection_name or settings.COLLECTION_NAME
        self.dimension = dimension or settings.EMBEDDING_DIMENSION
        self.vector_field = "vector"
        self.text_field = "text"

        if not self.uri or not self.token:
            raise ValueError("ZILLIZ_URI and ZILLIZ_TOKEN are required when VECTOR_DB_BACKEND=zilliz.")

        self.client = MilvusClient(uri=self.uri, token=self.token)

        if not self.client.has_collection(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                dimension=self.dimension,
                primary_field_name="id",
                id_type=self.data_type.VARCHAR,
                vector_field_name=self.vector_field,
                metric_type="COSINE",
                auto_id=False,
                max_length=512,
            )
        self._load_collection()

    def add_documents(
        self,
        ids: List[str],
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        if not (len(ids) == len(documents) == len(embeddings) == len(metadatas)):
            raise ValueError("ids, documents, embeddings, and metadatas must be same length")

        rows = []
        for doc_id, document, embedding, metadata in zip(ids, documents, embeddings, metadatas):
            row = {
                "id": doc_id,
                self.vector_field: embedding,
                self.text_field: document,
            }
            row.update(self._sanitize_metadata(metadata))
            rows.append(row)

        result = self.client.upsert(collection_name=self.collection_name, data=rows)
        self._flush_collection()
        self._load_collection()
        return result

    def similarity_search(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        filter_expression = self._where_to_filter(where)
        search_kwargs = {
            "collection_name": self.collection_name,
            "data": [query_embedding],
            "limit": top_k,
            "output_fields": ["*"],
        }

        if filter_expression:
            search_kwargs["filter"] = filter_expression

        raw_results = self.client.search(**search_kwargs)

        documents = []
        metadatas = []
        distances = []

        for hit in raw_results[0] if raw_results else []:
            entity = hit.get("entity", {})
            documents.append(entity.get(self.text_field, ""))
            metadatas.append(self._extract_metadata(entity))
            distances.append(1.0 - float(hit.get("distance", 0.0)))

        return {
            "documents": [documents],
            "metadatas": [metadatas],
            "distances": [distances],
        }

    def delete_all(self) -> None:
        if self.client.has_collection(self.collection_name):
            self.client.drop_collection(self.collection_name)

        self.client.create_collection(
            collection_name=self.collection_name,
            dimension=self.dimension,
            primary_field_name="id",
            id_type=self.data_type.VARCHAR,
            vector_field_name=self.vector_field,
            metric_type="COSINE",
            auto_id=False,
            max_length=512,
        )
        self._load_collection()

    def delete_where(self, where: Dict[str, Any]) -> None:
        filter_expression = self._where_to_filter(where)
        if not filter_expression:
            raise ValueError("delete_where requires a metadata filter")

        self.client.delete(collection_name=self.collection_name, filter=filter_expression)
        self._flush_collection()
        self._load_collection()

    def get_collection_info(self) -> Dict[str, Any]:
        count = 0
        if self.client.has_collection(self.collection_name):
            stats = self.client.get_collection_stats(self.collection_name)
            count = int(stats.get("row_count", 0))

        return {
            "name": self.collection_name,
            "count": count,
            "metadata": {
                "backend": "zilliz",
                "dimension": self.dimension,
                "metric": "COSINE",
            },
        }

    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = {}
        for key, value in metadata.items():
            if value is None:
                continue
            if isinstance(value, (str, int, float, bool)):
                sanitized[key] = value
            else:
                sanitized[key] = str(value)
        return sanitized

    def _extract_metadata(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        ignored_fields = {"id", self.vector_field, self.text_field}
        return {key: value for key, value in entity.items() if key not in ignored_fields}

    def _where_to_filter(self, where: Optional[Dict[str, Any]]) -> str:
        if not where:
            return ""

        if "$and" in where:
            parts = [self._where_to_filter(part) for part in where["$and"]]
            return " and ".join(f"({part})" for part in parts if part)

        if "$or" in where:
            parts = [self._where_to_filter(part) for part in where["$or"]]
            return " or ".join(f"({part})" for part in parts if part)

        filters = []
        for key, value in where.items():
            if key.startswith("$"):
                continue
            if isinstance(value, str):
                escaped = value.replace("\\", "\\\\").replace('"', '\\"')
                filters.append(f'{key} == "{escaped}"')
            elif isinstance(value, bool):
                filters.append(f"{key} == {str(value).lower()}")
            elif isinstance(value, (int, float)):
                filters.append(f"{key} == {value}")
            elif isinstance(value, dict):
                for operator, operand in value.items():
                    if operator == "$gt":
                        filters.append(f"{key} > {operand}")
                    elif operator == "$gte":
                        filters.append(f"{key} >= {operand}")
                    elif operator == "$lt":
                        filters.append(f"{key} < {operand}")
                    elif operator == "$lte":
                        filters.append(f"{key} <= {operand}")

        return " and ".join(filters)

    def _flush_collection(self) -> None:
        flush = getattr(self.client, "flush", None)
        if callable(flush):
            flush(collection_name=self.collection_name)

    def _load_collection(self) -> None:
        load_collection = getattr(self.client, "load_collection", None)
        if callable(load_collection):
            load_collection(collection_name=self.collection_name)
