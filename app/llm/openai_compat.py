"""Cliente para endpoints compatíveis com a API de chat da OpenAI (Gemini, Groq, Ollama).

O mesmo código atende os três; só mudam base_url, modelo e chave (ver app/core/config.py).
"""
from __future__ import annotations

import json
import logging
from typing import Any

import openai

from app.core.config import LLM_TIMEOUT_SECONDS, LLMSettings
from app.llm.base import LLMError, LLMResponse, Message, ToolCall

log = logging.getLogger(__name__)


def _simplify_schema(schema: Any) -> Any:
    """Precaução de compatibilidade: tipos em lista viram o primeiro tipo e remove `additionalProperties`.

    Não verificado na documentação do Gemini se esses recursos são aceitos no endpoint
    compatível; a validação real dos argumentos continua no registry, com o schema completo.
    """
    if isinstance(schema, dict):
        out = {}
        for key, value in schema.items():
            if key == "additionalProperties":
                continue
            if key == "type" and isinstance(value, list):
                out[key] = next((t for t in value if t != "null"), "string")
                continue
            out[key] = _simplify_schema(value)
        return out
    if isinstance(schema, list):
        return [_simplify_schema(v) for v in schema]
    return schema


def to_openai_tools(tools: list[dict]) -> list[dict]:
    return [{"type": "function",
             "function": {"name": t["name"], "description": t["description"],
                          "parameters": _simplify_schema(t["parameters"])}} for t in tools]


def _parse_arguments(raw: str | None) -> dict:
    if not raw or not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMError("bad_response", "Argumentos de ferramenta não são JSON válido") from exc
    if not isinstance(value, dict):
        raise LLMError("bad_response", "Argumentos de ferramenta não são um objeto")
    return value


def map_exception(exc: Exception) -> LLMError:
    """Traduz exceções do SDK para LLMError com categoria (sem expor chave ou corpo da resposta)."""
    if isinstance(exc, LLMError):
        return exc
    if isinstance(exc, openai.APITimeoutError):
        return LLMError("timeout", "Tempo esgotado ao consultar o LLM")
    if isinstance(exc, openai.APIConnectionError):
        return LLMError("network", "Falha de rede ao consultar o LLM")
    if isinstance(exc, openai.RateLimitError):
        return LLMError("rate_limit", "Limite de uso do provedor atingido (429)")
    if isinstance(exc, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return LLMError("auth", "Chave de API recusada pelo provedor (verifique LLM_API_KEY)")
    if isinstance(exc, openai.APIStatusError):
        category = "server" if exc.status_code >= 500 else "bad_response"
        return LLMError(category, f"Provedor respondeu com erro HTTP {exc.status_code}")
    return LLMError("bad_response", "Resposta inesperada do provedor")


class OpenAICompatClient:
    def __init__(self, settings: LLMSettings, *, client: Any | None = None,
                 timeout: float = LLM_TIMEOUT_SECONDS) -> None:
        if client is None:
            if not settings.api_key:
                raise LLMError("config", "LLM_API_KEY não definida")
            if not settings.model or not settings.base_url:
                raise LLMError("config", "Modelo ou endereço do provedor não definidos")
            client = openai.OpenAI(api_key=settings.api_key, base_url=settings.base_url,
                                   timeout=timeout, max_retries=1)
        self._client = client
        self._model = settings.model

    def chat(self, messages: list[Message], tools: list[dict]) -> LLMResponse:
        kwargs: dict[str, Any] = {"model": self._model, "messages": messages, "temperature": 0.3}
        if tools:
            kwargs["tools"] = to_openai_tools(tools)
            kwargs["tool_choice"] = "auto"
        try:
            resp = self._client.chat.completions.create(**kwargs)
            return self._convert(resp)
        except Exception as exc:  # noqa: BLE001 - tudo vira LLMError categorizado
            err = map_exception(exc)
            log.warning("Falha no LLM (%s)", err.category)
            raise err from exc

    @staticmethod
    def _convert(resp: Any) -> LLMResponse:
        choices = getattr(resp, "choices", None)
        if not choices:
            raise LLMError("bad_response", "Resposta do provedor sem conteúdo")
        msg = choices[0].message
        calls = [ToolCall(id=tc.id or f"call_{i}", name=tc.function.name,
                          arguments=_parse_arguments(tc.function.arguments))
                 for i, tc in enumerate(getattr(msg, "tool_calls", None) or [])]
        return LLMResponse(text=(msg.content or None), tool_calls=calls)
