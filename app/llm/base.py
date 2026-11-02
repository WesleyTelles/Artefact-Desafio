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

# Categorias de falha do provedor. Só as transitórias admitem nova tentativa.
ERROR_CATEGORIES = ("bad_request", "auth", "not_found", "rate_limit", "server_error", "timeout",
                    "connection", "bad_response", "config", "budget")
RETRYABLE_CATEGORIES = frozenset({"rate_limit", "server_error", "timeout", "connection"})
# Categorias que indicam problema de configuração/credencial: dica ao operador, nunca ao cliente.
OPERATOR_CATEGORIES = frozenset({"auth", "not_found", "bad_request", "config"})


class LLMError(AppError):
    """Falha técnica ao falar com o LLM, com categoria.

    A mensagem nunca contém chave, corpo bruto da resposta ou dados do cliente.
    `hint` é uma orientação curta ao operador (stderr/--debug); `attempts` é quantas
    chamadas ao provedor foram feitas até a falha.
    """

    def __init__(self, category: str, message: str = "", *, hint: str = "", attempts: int = 1) -> None:
        super().__init__(message or category)
        self.category = category
        self.hint = hint
        self.attempts = attempts

    @property
    def retryable(self) -> bool:
        return self.category in RETRYABLE_CATEGORIES


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict
    # Dados opacos do provedor que precisam voltar na próxima rodada (ex.: assinatura de raciocínio do Gemini 3).
    extra: dict | None = None
    # Preenchido quando o modelo devolveu argumentos que não são um objeto JSON válido
    # ("malformed_json" ou "not_object"); `arguments` fica vazio e nunca deve ser executado.
    arguments_error: str | None = None


@dataclass
class LLMResponse:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    # {"prompt_tokens", "completion_tokens", "total_tokens"} quando o provedor informa; senão None.
    usage: dict | None = None
    attempts: int = 1  # chamadas ao provedor nesta resposta (1 = sem retry)


class LLMClient(Protocol):
    def chat(self, messages: list[Message], tools: list[dict], *,
             timeout: float | None = None) -> LLMResponse:
        """Envia a conversa e as definições de ferramentas; devolve texto e/ou tool_calls.

        `timeout` é o orçamento em segundos para esta chamada, retries incluídos; None = sem teto extra.
        Levanta LLMError em falha técnica (categoria "budget" se o orçamento acabou).
        """
        ...
