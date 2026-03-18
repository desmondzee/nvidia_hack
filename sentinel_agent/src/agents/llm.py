"""LLM provider abstraction — NVIDIA NIM, Google Gemini, or local Ollama."""

import json
import os
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

load_dotenv()


class _OllamaWithGoogleFallback(BaseChatModel):
    """Ollama LLM that falls back to Google when Ollama fails.

    Applies fallbacks at the structured-output level so both models produce
    compatible output when with_structured_output is used.
    """

    ollama_llm: BaseChatModel
    google_llm: BaseChatModel

    @property
    def _llm_type(self) -> str:
        return "ollama_with_google_fallback"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return self.ollama_llm._generate(messages, stop, run_manager, **kwargs)

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return await self.ollama_llm._agenerate(messages, stop, run_manager, **kwargs)

    def with_structured_output(
        self, schema: type | dict[str, Any], **kwargs: Any
    ) -> Runnable:
        """Return structured output runnable with fallback at this level."""
        ollama_structured = self.ollama_llm.with_structured_output(schema, **kwargs)
        google_structured = self.google_llm.with_structured_output(schema, **kwargs)
        return ollama_structured.with_fallbacks([google_structured])


def _ollama_model_detected(model: str, base_url: str) -> tuple[bool, str]:
    """Check if Ollama is running and has the requested model.

    Returns:
        (detected, resolved_name): detected=True if model exists, resolved_name is the
        exact name to use (e.g. "llama3.2:3b" when user asked for "llama3.2").
    """
    try:
        req = Request(f"{base_url.rstrip('/')}/api/tags", method="GET")
        with urlopen(req, timeout=2) as resp:
            data = resp.read().decode()
        tags = json.loads(data)
        for m in tags.get("models", []):
            name = m.get("name", "")
            if name == model or name.startswith(f"{model}:"):
                return True, name
        return False, model
    except (URLError, OSError, ValueError, KeyError):
        return False, model


def get_llm(provider: str = "nvidia") -> BaseChatModel:
    """Get an LLM instance for negotiation reasoning.

    Args:
        provider: "nvidia" for NVIDIA NIM, "google" for Gemini, "ollama" for local
            (if Ollama not detected or fails, uses Google when GOOGLE_API_KEY is set).
    """
    if provider == "nvidia":
        from langchain_nvidia_ai_endpoints import ChatNVIDIA

        return ChatNVIDIA(
            model="nvidia/llama-3.3-nemotron-super-49b-v1",
            api_key=os.getenv("NVIDIA_API_KEY"),
            temperature=0.2,
        )

    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model="gemini-3-flash-preview",
            api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0.2,
        )

    if provider == "ollama":
        model = os.getenv("OLLAMA_MODEL", "llama3.2")
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        google_api_key = os.getenv("GOOGLE_API_KEY")
        detected, resolved_model = _ollama_model_detected(model, base_url)

        if not detected:
            if google_api_key:
                from langchain_google_genai import ChatGoogleGenerativeAI

                return ChatGoogleGenerativeAI(
                    model="gemini-3-flash-preview",
                    api_key=google_api_key,
                    temperature=0.2,
                )
            raise ValueError(
                f"Ollama model '{model}' not found. Either run `ollama pull {model}` "
                "or set GOOGLE_API_KEY in .env to fall back to Gemini."
            )

        from langchain_ollama import ChatOllama

        ollama_llm = ChatOllama(
            model=resolved_model,
            base_url=base_url,
            temperature=0.2,
        )
        if google_api_key:
            from langchain_google_genai import ChatGoogleGenerativeAI

            google_llm = ChatGoogleGenerativeAI(
                model="gemini-3-flash-preview",
                api_key=google_api_key,
                temperature=0.2,
            )
            return _OllamaWithGoogleFallback(
                ollama_llm=ollama_llm,
                google_llm=google_llm,
            )
        return ollama_llm

    raise ValueError(
        f"Unknown provider '{provider}'. Choose 'nvidia', 'google', or 'ollama'."
    )
