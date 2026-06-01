from typing import List, Union
import logging

import requests

from app.config.settings import settings

logger = logging.getLogger(__name__)


class OllamaEmbedder:
    """Wrapper for Ollama's local embedding API."""

    def __init__(self, base_url: str = None, model: str = None):
        self.base_url = base_url or settings.OLLAMA_BASE_URL
        self.model = model or settings.EMBEDDING_MODEL
        self.embed_endpoint = f"{self.base_url}/api/embeddings"

        logger.info("Initialized OllamaEmbedder with model: %s", self.model)
        self._check_ollama_connection()

    def _check_ollama_connection(self) -> None:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise ConnectionError(
                f"Ollama server not reachable at {self.base_url}. "
                f"Make sure Ollama is running. Error: {exc}"
            ) from exc

    def embed_single(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise ValueError("Cannot embed empty text")

        response = requests.post(
            self.embed_endpoint,
            json={"model": self.model, "prompt": text},
            timeout=30,
        )
        response.raise_for_status()

        embedding = response.json().get("embedding")
        if not embedding:
            raise RuntimeError("No embedding returned from Ollama")

        return embedding

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        embeddings = []
        for index, text in enumerate(texts):
            try:
                embeddings.append(self.embed_single(text))
            except Exception as exc:
                logger.error("Failed to embed text %s: %s", index, exc)
                embeddings.append([0.0] * settings.EMBEDDING_DIMENSION)

        return embeddings

    def embed(self, text: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
        if isinstance(text, str):
            return self.embed_single(text)
        if isinstance(text, list):
            return self.embed_batch(text)
        raise TypeError("Input must be str or List[str]")

    def get_embedding_dimension(self) -> int:
        return settings.EMBEDDING_DIMENSION


class HuggingFaceEmbedder:
    """Local sentence-transformers embedder for deployable Python hosting."""

    def __init__(self, model: str = None):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Hugging Face embeddings require sentence-transformers. "
                "Install requirements.txt again."
            ) from exc

        self.model_name = model or settings.EMBEDDING_MODEL
        self.model = SentenceTransformer(self.model_name)
        logger.info("Initialized HuggingFaceEmbedder with model: %s", self.model_name)

        actual_dimension = self.model.get_sentence_embedding_dimension()
        if actual_dimension != settings.EMBEDDING_DIMENSION:
            raise ValueError(
                f"EMBEDDING_DIMENSION={settings.EMBEDDING_DIMENSION} does not match "
                f"{self.model_name} output dimension {actual_dimension}."
            )

    def embed_single(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise ValueError("Cannot embed empty text")

        return self.model.encode(text, normalize_embeddings=True).tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        clean_texts = [text if text and text.strip() else " " for text in texts]
        return self.model.encode(clean_texts, normalize_embeddings=True).tolist()

    def embed(self, text: Union[str, List[str]]) -> Union[List[float], List[List[float]]]:
        if isinstance(text, str):
            return self.embed_single(text)
        if isinstance(text, list):
            return self.embed_batch(text)
        raise TypeError("Input must be str or List[str]")

    def get_embedding_dimension(self) -> int:
        return settings.EMBEDDING_DIMENSION


_embedder_instance = None


def get_embedder():
    """Return a singleton embedder for the configured provider."""
    global _embedder_instance

    if _embedder_instance is not None:
        return _embedder_instance

    provider = settings.EMBEDDING_PROVIDER.lower()
    if provider == "ollama":
        _embedder_instance = OllamaEmbedder()
    elif provider in {"huggingface", "sentence-transformers", "sentence_transformers"}:
        _embedder_instance = HuggingFaceEmbedder()
    else:
        raise ValueError(
            f"Unsupported EMBEDDING_PROVIDER='{settings.EMBEDDING_PROVIDER}'. "
            "Use 'ollama' or 'huggingface'."
        )

    return _embedder_instance
