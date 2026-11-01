"""Contrato mínimo entre o orquestrador e qualquer provedor de LLM.

Mensagens seguem o formato de chat com ferramentas (role/content, `tool_calls` nas
respostas do modelo e `tool_call_id` nos resultados), o mesmo dos provedores
compatíveis com OpenAI. Assim o histórico não precisa de conversão.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.core.exceptions import AppError

Message = dict  # {"role": "system|user|assistant|tool", "content": str, ...}

# Categorias de falha do provedor; o orquestrador só precisa saber que houve falha técnica.
ERROR_CATEGORIES = ("auth", "rate_limit", "timeout", "network", "server", "bad_response", "config")


class LLMError(AppError):
    """Falha técnica ao falar com o LLM, com categoria."""

    def __init__(self, category: str, message: str = "") -> None:
        super().__init__(message or category)
        self.category = category


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMClient(Protocol):
    def chat(self, messages: list[Message], tools: list[dict]) -> LLMResponse:
        """Envia a conversa e as definições de ferramentas; devolve texto e/ou tool_calls.

        Levanta LLMError em falha técnica.
        """
        ...
