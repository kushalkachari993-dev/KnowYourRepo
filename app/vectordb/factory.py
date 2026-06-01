from app.config.settings import settings
from app.vectordb.chroma_client import ChromaClient
from app.vectordb.zilliz_client import ZillizClient


def get_vector_store():
    backend = settings.VECTOR_DB_BACKEND.lower()

    if backend == "chroma":
        return ChromaClient(
            persist_directory=str(settings.CHROMA_PERSIST_DIR),
            collection_name=settings.COLLECTION_NAME,
        )

    if backend == "zilliz":
        return ZillizClient(
            uri=settings.ZILLIZ_URI,
            token=settings.ZILLIZ_TOKEN,
            collection_name=settings.COLLECTION_NAME,
            dimension=settings.EMBEDDING_DIMENSION,
        )

    raise ValueError(
        f"Unsupported VECTOR_DB_BACKEND='{settings.VECTOR_DB_BACKEND}'. "
        "Available backends: chroma, zilliz."
    )
