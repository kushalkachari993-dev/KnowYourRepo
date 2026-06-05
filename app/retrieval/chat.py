from typing import Any, Dict, List
import logging
import json
import re

import requests

from app.config.settings import settings

logger = logging.getLogger(__name__)


class BaseDocumentChat:
    """Common retrieved-context prompt builder."""

    def answer(self, question: str, chunks: List[Dict], max_context_chars: int = 4000) -> str:
        return self.grounded_answer(question, chunks, max_context_chars)["answer"]

    def grounded_answer(self, question: str, chunks: List[Dict], max_context_chars: int = 4000) -> Dict[str, Any]:
        context = self._build_context(chunks, max_context_chars)
        if not context:
            return {
                "answer": "I could not find enough retrieved context to answer this.",
                "citations": [],
                "confidence": "low",
                "groundedness": {
                    "status": "insufficient_evidence",
                    "grounded": False,
                    "unsupported_claims": ["No retrieved context was available."],
                    "needs_correction": False,
                },
                "corrected": False,
            }

        answer_prompt = self._build_grounded_answer_prompt(question, context)
        raw_answer = self._complete(answer_prompt)
        answer_payload = self._parse_json_object(raw_answer)
        answer_text = str(answer_payload.get("answer") or raw_answer).strip()
        citations = self._normalize_citations(answer_payload.get("citations", []))
        confidence = self._normalize_confidence(answer_payload.get("confidence", "medium"))

        check = self._groundedness_check(question, answer_text, context)
        corrected = False
        if check.get("needs_correction"):
            correction_prompt = self._build_correction_prompt(question, answer_text, context, check)
            corrected_raw = self._complete(correction_prompt)
            corrected_payload = self._parse_json_object(corrected_raw)
            answer_text = str(corrected_payload.get("answer") or corrected_raw).strip()
            citations = self._normalize_citations(corrected_payload.get("citations", citations))
            confidence = self._normalize_confidence(corrected_payload.get("confidence", "low"))
            check = self._groundedness_check(question, answer_text, context)
            corrected = True

        if check.get("needs_correction"):
            answer_text = "I found related documents, but I do not have enough grounded evidence to answer that confidently."
            citations = []
            confidence = "low"
            check = {
                "status": "insufficient_evidence",
                "grounded": False,
                "unsupported_claims": check.get("unsupported_claims", []),
                "needs_correction": False,
            }

        return {
            "answer": answer_text,
            "citations": citations,
            "confidence": confidence,
            "groundedness": check,
            "corrected": corrected,
        }

    def healthcheck(self) -> None:
        raise NotImplementedError

    def _complete(self, prompt: str) -> str:
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

    def _build_grounded_answer_prompt(self, question: str, context: str) -> str:
        return (
            "You are a grounded document assistant. Complete the user's request using only the document excerpts.\n"
            "Return only valid JSON with this schema:\n"
            "{\n"
            '  "answer": "answer, summary, or explanation grounded in the excerpts",\n'
            '  "citations": [{"filename": "...", "chunk_index": 0, "quote": "short exact supporting quote"}],\n'
            '  "confidence": "high|medium|low"\n'
            "}\n"
            "Rules:\n"
            "- Do not use outside knowledge.\n"
            "- Treat summarization, explanation, comparison, and extraction requests as valid document tasks.\n"
            "- If the user asks for a summary, summarize all useful information present in the excerpts.\n"
            "- Match the requested level of detail. For a long or detailed summary, use multiple paragraphs or bullets if the excerpts support it.\n"
            "- Do not refuse only because the request is not phrased as a question.\n"
            "- Every factual claim must be supported by the excerpts and the citations list should include the strongest supporting chunks.\n"
            "- If the excerpts are limited, give the best grounded answer from them and clearly say that it is based only on the retrieved excerpts.\n"
            "- If the excerpts do not contain relevant information, say so in the answer and use low confidence.\n"
            "- Keep quotes short.\n\n"
            f"Document excerpts:\n{context}\n\n"
            f"User request: {question}\n"
        )

    def _build_check_prompt(self, question: str, answer: str, context: str) -> str:
        return (
            "Check whether the response is supported by the document excerpts and satisfies the user's document task.\n"
            "Return only valid JSON with this schema:\n"
            "{\n"
            '  "grounded": true,\n'
            '  "unsupported_claims": [],\n'
            '  "needs_correction": false,\n'
            '  "status": "grounded|partially_grounded|insufficient_evidence"\n'
            "}\n"
            "Mark unsupported any claim that is not directly supported by the excerpts.\n\n"
            f"Document excerpts:\n{context}\n\n"
            f"User request: {question}\n\n"
            f"Response to check:\n{answer}\n"
        )

    def _build_correction_prompt(self, question: str, answer: str, context: str, check: Dict[str, Any]) -> str:
        unsupported = "; ".join(str(item) for item in check.get("unsupported_claims", [])) or "unsupported claims"
        return (
            "Rewrite the response so it uses only claims supported by the document excerpts and still completes the user's request.\n"
            "Remove unsupported claims. Return only valid JSON with this schema:\n"
            "{\n"
            '  "answer": "corrected grounded answer, summary, or explanation",\n'
            '  "citations": [{"filename": "...", "chunk_index": 0, "quote": "short exact supporting quote"}],\n'
            '  "confidence": "high|medium|low"\n'
            "}\n\n"
            f"Unsupported claims to remove: {unsupported}\n\n"
            f"Document excerpts:\n{context}\n\n"
            f"User request: {question}\n\n"
            f"Original response:\n{answer}\n"
        )

    def _groundedness_check(self, question: str, answer: str, context: str) -> Dict[str, Any]:
        raw_check = self._complete(self._build_check_prompt(question, answer, context))
        payload = self._parse_json_object(raw_check)
        grounded = bool(payload.get("grounded", False))
        unsupported = payload.get("unsupported_claims", [])
        if not isinstance(unsupported, list):
            unsupported = [str(unsupported)]

        status = payload.get("status")
        if status not in {"grounded", "partially_grounded", "insufficient_evidence"}:
            status = "grounded" if grounded and not unsupported else "partially_grounded"

        needs_correction = bool(payload.get("needs_correction", bool(unsupported) or not grounded))
        return {
            "status": status,
            "grounded": grounded and not unsupported,
            "unsupported_claims": [str(item) for item in unsupported],
            "needs_correction": needs_correction,
        }

    def _parse_json_object(self, text: str) -> Dict[str, Any]:
        text = (text or "").strip()
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, flags=re.DOTALL)
            if not match:
                return {}
            try:
                parsed = json.loads(match.group(0))
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}

    def _normalize_citations(self, citations: Any) -> List[Dict[str, Any]]:
        normalized = []
        if not isinstance(citations, list):
            return normalized

        for citation in citations[:6]:
            if not isinstance(citation, dict):
                continue
            normalized.append(
                {
                    "filename": str(citation.get("filename", "unknown")),
                    "chunk_index": citation.get("chunk_index", ""),
                    "quote": str(citation.get("quote", ""))[:280],
                }
            )
        return normalized

    def _normalize_confidence(self, confidence: Any) -> str:
        confidence = str(confidence).lower()
        return confidence if confidence in {"high", "medium", "low"} else "medium"

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

        return self._complete(prompt)

    def _complete(self, prompt: str) -> str:
        if not prompt:
            return ""

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

        return self._complete(prompt)

    def _complete(self, prompt: str) -> str:
        if not prompt:
            return ""

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
