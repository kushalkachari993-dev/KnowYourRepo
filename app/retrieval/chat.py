from typing import Dict, List
import logging

import requests

from app.config.settings import settings

logger = logging.getLogger(__name__)


class BaseDocumentChat:
    """Common retrieved-context prompt builder."""

    def answer(self, question: str, chunks: List[Dict], max_context_chars: int = 4000) -> str:
        raise NotImplementedError

    def healthcheck(self) -> None:
        raise NotImplementedError

    def _build_prompt(self, question: str, chunks: List[Dict], max_context_chars: int) -> str:
        context = self._build_context(chunks, max_context_chars)
        if not context:
            return ""

        return (
            "Answer the user's question using only the document excerpts below. "
            "If the excerpts do not contain the answer, say that the indexed documents do not show it.\n\n"
            f"Document excerpts:\n{context}\n\n"
            f"Question: {question}\n"
            "Answer:"
        )

    def _build_context(self, chunks: List[Dict], max_context_chars: int) -> str:
        parts = []
        used_chars = 0

        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            filename = metadata.get("filename", "unknown")
            chunk_index = metadata.get("chunk_index", 0)
            text = chunk.get("text", "")
            part = f"[{filename} chunk {chunk_index}]\n{text}"

            if used_chars + len(part) > max_context_chars:
                break

            parts.append(part)
            used_chars += len(part)

        return "\n\n".join(parts)


class OllamaDocumentChat(BaseDocumentChat):
    """Answer questions with a local Ollama chat model."""

    def __init__(self, base_url: str = None, model: str = None):
        self.base_url = base_url or settings.OLLAMA_BASE_URL
        self.model = model or settings.CHAT_MODEL
        self.generate_endpoint = f"{self.base_url}/api/generate"

    def answer(self, question: str, chunks: List[Dict], max_context_chars: int = 4000) -> str:
        prompt = self._build_prompt(question, chunks, max_context_chars)
        if not prompt:
            return "I could not find enough retrieved context to answer this."

        response = requests.post(
            self.generate_endpoint,
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=90,
        )
        response.raise_for_status()
        return response.json().get("response", "").strip() or "The model returned an empty answer."

    def healthcheck(self) -> None:
        response = requests.get(f"{self.base_url}/api/tags", timeout=5)
        response.raise_for_status()

        models = response.json().get("models", [])
        model_names = {model.get("name") for model in models}
        if self.model not in model_names:
            available = ", ".join(sorted(name for name in model_names if name)) or "none"
            raise RuntimeError(
                f"Chat model '{self.model}' is not installed in Ollama. "
                f"Available models: {available}. Run: ollama pull {self.model}"
            )


class GroqDocumentChat(BaseDocumentChat):
    """Answer questions with Groq's OpenAI-compatible chat completions API."""

    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        self.api_key = api_key or settings.GROQ_API_KEY
        self.base_url = (base_url or settings.GROQ_BASE_URL).rstrip("/")
        self.model = model or settings.CHAT_MODEL
        self.chat_endpoint = f"{self.base_url}/chat/completions"

        if not self.api_key:
            raise ValueError("GROQ_API_KEY is required when CHAT_PROVIDER=groq.")

    def answer(self, question: str, chunks: List[Dict], max_context_chars: int = 4000) -> str:
        prompt = self._build_prompt(question, chunks, max_context_chars)
        if not prompt:
            return "I could not find enough retrieved context to answer this."

        response = requests.post(
            self.chat_endpoint,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You answer questions using only the retrieved document context.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "stream": False,
            },
            timeout=90,
        )
        response.raise_for_status()
        choices = response.json().get("choices", [])
        if not choices:
            return "The chat model returned no answer."

        return choices[0].get("message", {}).get("content", "").strip() or "The chat model returned an empty answer."

    def healthcheck(self) -> None:
        response = requests.get(
            f"{self.base_url}/models",
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=10,
        )
        response.raise_for_status()

        models = response.json().get("data", [])
        model_ids = {model.get("id") for model in models}
        if self.model not in model_ids:
            sample = ", ".join(sorted(model for model in model_ids if model)[:10]) or "none"
            raise RuntimeError(
                f"Groq model '{self.model}' was not found for this API key. "
                f"Available examples: {sample}"
            )


def get_document_chat() -> BaseDocumentChat:
    provider = settings.CHAT_PROVIDER.lower()

    if provider == "ollama":
        return OllamaDocumentChat()
    if provider == "groq":
        return GroqDocumentChat()

    raise ValueError(f"Unsupported CHAT_PROVIDER='{settings.CHAT_PROVIDER}'. Use 'ollama' or 'groq'.")
