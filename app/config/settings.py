import os
from pathlib import Path
from dataclasses import dataclass

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass
class Settings:
    """
    Centralized configuration for the document search system.
    
    All paths, model names, and system parameters are defined here.
    Can be overridden via environment variables.
    """
    
    # ============================================================
    # Project Paths
    # ============================================================
    PROJECT_ROOT: Path = PROJECT_ROOT
    DATA_DIR: Path = PROJECT_ROOT / "data"
    RAW_DATA_DIR: Path = DATA_DIR / "raw"
    PROCESSED_DATA_DIR: Path = DATA_DIR / "processed"
    CHROMA_PERSIST_DIR: Path = DATA_DIR / "chroma"
    
    # ============================================================
    # Embedding / Chat Configuration
    # ============================================================
    EMBEDDING_PROVIDER: str = "ollama"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    EMBEDDING_MODEL: str = "bge-m3:567m"
    EMBEDDING_DIMENSION: int = 1024  # bge-m3 outputs 1024-dim vectors
    CHAT_PROVIDER: str = "ollama"
    CHAT_MODEL: str = "llama3.2:3b"
    GROQ_API_KEY: str = ""
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    
    # ============================================================
    # Vector Database Configuration
    # ============================================================
    VECTOR_DB_BACKEND: str = "chroma"
    COLLECTION_NAME: str = "documents"
    ZILLIZ_URI: str = ""
    ZILLIZ_TOKEN: str = ""
    
    # ============================================================
    # Document Processing
    # ============================================================
    CHUNK_SIZE: int = 500  # Characters per chunk
    CHUNK_OVERLAP: int = 50  # Overlap between chunks
    
    SUPPORTED_FILE_TYPES: tuple = (".pdf", ".txt", ".docx", ".md")
    
    # ============================================================
    # Retrieval Configuration
    # ============================================================
    DEFAULT_TOP_K: int = 5  # Number of chunks to retrieve
    SIMILARITY_THRESHOLD: float = 0.7  # Minimum similarity score (0-1)
    
    # ============================================================
    # Streamlit UI
    # ============================================================
    APP_TITLE: str = "📚 Document Search System"
    APP_ICON: str = "📄"
    MAX_UPLOAD_SIZE_MB: int = 200
    
    # ============================================================
    # Logging
    # ============================================================
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    def __post_init__(self):
        """Create necessary directories on initialization."""
        self.RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.CHROMA_PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def from_env(cls) -> "Settings":
        """
        Load settings with environment variable overrides.
        
        Example .env file:
            OLLAMA_BASE_URL=http://localhost:11434
            EMBEDDING_PROVIDER=huggingface
            EMBEDDING_MODEL=bge-m3:567m
            EMBEDDING_DIMENSION=1024
            CHAT_PROVIDER=groq
            CHAT_MODEL=llama3.2:3b
            VECTOR_DB_BACKEND=chroma
            CHUNK_SIZE=1000
            DEFAULT_TOP_K=10
        """
        return cls(
            EMBEDDING_PROVIDER=os.getenv("EMBEDDING_PROVIDER", cls.EMBEDDING_PROVIDER),
            OLLAMA_BASE_URL=os.getenv("OLLAMA_BASE_URL", cls.OLLAMA_BASE_URL),
            EMBEDDING_MODEL=os.getenv("EMBEDDING_MODEL", cls.EMBEDDING_MODEL),
            EMBEDDING_DIMENSION=int(os.getenv("EMBEDDING_DIMENSION", cls.EMBEDDING_DIMENSION)),
            CHAT_PROVIDER=os.getenv("CHAT_PROVIDER", cls.CHAT_PROVIDER),
            CHAT_MODEL=os.getenv("CHAT_MODEL", cls.CHAT_MODEL),
            GROQ_API_KEY=os.getenv("GROQ_API_KEY", cls.GROQ_API_KEY),
            GROQ_BASE_URL=os.getenv("GROQ_BASE_URL", cls.GROQ_BASE_URL),
            CHUNK_SIZE=int(os.getenv("CHUNK_SIZE", cls.CHUNK_SIZE)),
            CHUNK_OVERLAP=int(os.getenv("CHUNK_OVERLAP", cls.CHUNK_OVERLAP)),
            DEFAULT_TOP_K=int(os.getenv("DEFAULT_TOP_K", cls.DEFAULT_TOP_K)),
            VECTOR_DB_BACKEND=os.getenv("VECTOR_DB_BACKEND", cls.VECTOR_DB_BACKEND),
            COLLECTION_NAME=os.getenv("COLLECTION_NAME", cls.COLLECTION_NAME),
            ZILLIZ_URI=os.getenv("ZILLIZ_URI", cls.ZILLIZ_URI),
            ZILLIZ_TOKEN=os.getenv("ZILLIZ_TOKEN", cls.ZILLIZ_TOKEN),
        )


# ============================================================
# Global Settings Instance
# ============================================================
settings = Settings.from_env()


# ============================================================
# Convenience function for other modules
# ============================================================
def get_settings() -> Settings:
    """Returns the global settings instance."""
    return settings
