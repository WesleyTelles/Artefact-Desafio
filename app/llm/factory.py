"""Cria o cliente de LLM a partir da configuração (env/.env)."""
from __future__ import annotations

from dataclasses import replace

from app.core.config import LLMSettings, load_llm_settings
from app.llm.base import LLMClient, LLMError
from app.llm.mock import MockLLM
from app.llm.openai_compat import OpenAICompatClient

PROVIDERS = ("gemini", "groq", "ollama", "mock")


def create_client(settings: LLMSettings | None = None) -> LLMClient:
    settings = settings or load_llm_settings()
    if settings.provider == "mock":
        return MockLLM()
    if settings.provider not in PROVIDERS:
        raise LLMError("config", f"LLM_PROVIDER inválido: '{settings.provider}'. Use {', '.join(PROVIDERS)}.")
    if settings.provider == "ollama" and not settings.api_key:
        # Ollama local não valida a chave, mas o SDK exige algum valor.
        settings = replace(settings, api_key="ollama")
    return OpenAICompatClient(settings)
