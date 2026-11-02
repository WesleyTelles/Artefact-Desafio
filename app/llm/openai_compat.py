"""Cliente para endpoints compatíveis com a API de chat da OpenAI (Gemini, Groq, Ollama).

O mesmo código atende os três; só mudam base_url, modelo e chave (ver app/core/config.py).
"""
from __future__ import annotations

import json
import logging
import random
import time
from typing import Any, Callable

import openai

from app.core.config import (LLM_BACKOFF_BASE_SECONDS, LLM_BACKOFF_MAX_SECONDS, LLM_RETRY_AFTER_CAP_SECONDS,
                             LLM_TIMEOUT_SECONDS, LLMSettings)
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


def _parse_arguments(raw: str | None) -> tuple[dict, str | None]:
    """Devolve (argumentos, erro). Argumentos inválidos NÃO levantam: o orquestrador pede correção ao modelo."""
    if not raw or not raw.strip():
        return {}, None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}, "malformed_json"
    if not isinstance(value, dict):
        return {}, "not_object"
    return value, None


def _status_error(status: int) -> LLMError:
    if status in (401, 403):
        return LLMError("auth", f"Chave de API recusada pelo provedor (HTTP {status})",
                        hint="verifique LLM_API_KEY e as permissões da chave")
    if status == 404:
        return LLMError("not_found", "Modelo ou endereço não encontrado no provedor (HTTP 404)",
                        hint="verifique LLM_MODEL/LLM_BASE_URL")
    if status == 408:
        return LLMError("timeout", "Provedor encerrou por tempo esgotado (HTTP 408)")
    if status == 429:
        return LLMError("rate_limit", "Limite de uso do provedor atingido (HTTP 429)")
    if status >= 500:
        return LLMError("server_error", f"Provedor indisponível (HTTP {status})")
    return LLMError("bad_request", f"Provedor recusou a requisição (HTTP {status})",
                    hint="verifique LLM_MODEL e o formato da requisição")


def map_exception(exc: Exception) -> LLMError:
    """Traduz exceções do SDK para LLMError com categoria (sem expor chave ou corpo da resposta)."""
    if isinstance(exc, LLMError):
        return exc
    if isinstance(exc, openai.APITimeoutError):
        return LLMError("timeout", "Tempo esgotado ao consultar o LLM")
    if isinstance(exc, openai.APIConnectionError):
        return LLMError("connection", "Falha de conexão ao consultar o LLM",
                        hint="verifique a rede e LLM_BASE_URL")
    if isinstance(exc, openai.APIStatusError):
        return _status_error(int(getattr(exc, "status_code", 0) or 0))
    return LLMError("bad_response", "Resposta inesperada do provedor")


def _retry_after(exc: BaseException) -> float | None:
    """Segundos do cabeçalho Retry-After (formato numérico); datas HTTP são ignoradas."""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    try:
        value = float(headers.get("retry-after")) if headers is not None else None
    except (TypeError, ValueError):
        return None
    return value if value is not None and value >= 0 else None


def _extract_usage(resp: Any) -> dict | None:
    usage = getattr(resp, "usage", None)
    if usage is None:
        return None
    out = {k: getattr(usage, k, None) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
    return out if any(isinstance(v, int) for v in out.values()) else None


class OpenAICompatClient:
    """Cliente com retry próprio (o do SDK fica desligado): só falhas transitórias são repetidas."""

    def __init__(self, settings: LLMSettings, *, client: Any | None = None,
                 timeout: float = LLM_TIMEOUT_SECONDS, max_attempts: int | None = None,
                 backoff_base: float = LLM_BACKOFF_BASE_SECONDS, backoff_max: float = LLM_BACKOFF_MAX_SECONDS,
                 retry_after_cap: float = LLM_RETRY_AFTER_CAP_SECONDS,
                 sleep: Callable[[float], None] = time.sleep,
                 jitter: Callable[[], float] = random.random) -> None:
        if client is None:
            if not settings.api_key:
                raise LLMError("config", "LLM_API_KEY não definida")
            if not settings.model or not settings.base_url:
                raise LLMError("config", "Modelo ou endereço do provedor não definidos")
            client = openai.OpenAI(api_key=settings.api_key, base_url=settings.base_url,
                                   timeout=timeout, max_retries=0)
        self._client = client
        self._model = settings.model
        self._max_attempts = max(1, max_attempts if max_attempts is not None else settings.max_attempts)
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._retry_after_cap = retry_after_cap
        self._sleep = sleep
        self._jitter = jitter  # float em [0, 1)

    def _delay(self, attempt: int, exc: BaseException) -> float:
        retry_after = _retry_after(exc)
        if retry_after is not None:
            return min(retry_after, self._retry_after_cap)
        backoff = min(self._backoff_max, self._backoff_base * 2 ** (attempt - 1))
        return backoff * (0.5 + self._jitter() / 2)  # jitter: 50% a 100% do valor

    def chat(self, messages: list[Message], tools: list[dict]) -> LLMResponse:
        kwargs: dict[str, Any] = {"model": self._model, "messages": messages, "temperature": 0.3}
        if tools:
            kwargs["tools"] = to_openai_tools(tools)
            kwargs["tool_choice"] = "auto"
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self._convert(self._client.chat.completions.create(**kwargs))
                resp.attempts = attempt
                return resp
            except Exception as exc:  # noqa: BLE001 - tudo vira LLMError categorizado
                err = map_exception(exc)
                err.attempts = attempt
                if err.retryable and attempt < self._max_attempts:
                    delay = self._delay(attempt, exc)
                    log.warning("Falha transitória no LLM (%s), tentativa %d/%d, nova tentativa em %.1fs",
                                err.category, attempt, self._max_attempts, delay)
                    self._sleep(delay)
                    continue
                log.warning("Falha no LLM (%s) após %d tentativa(s)%s", err.category, attempt,
                            f"; dica: {err.hint}" if err.hint else "")
                raise err from exc

    @staticmethod
    def _convert(resp: Any) -> LLMResponse:
        choices = getattr(resp, "choices", None)
        if not choices:
            raise LLMError("bad_response", "Resposta do provedor sem conteúdo")
        msg = choices[0].message
        calls = []
        for i, tc in enumerate(getattr(msg, "tool_calls", None) or []):
            args, error = _parse_arguments(tc.function.arguments)
            extra = getattr(tc, "extra_content", None) or (getattr(tc, "model_extra", None) or {}).get("extra_content")
            calls.append(ToolCall(id=tc.id or f"call_{i}", name=tc.function.name, arguments=args,
                                  extra=extra, arguments_error=error))
        return LLMResponse(text=(msg.content or None), tool_calls=calls, usage=_extract_usage(resp))
