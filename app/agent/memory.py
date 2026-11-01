"""Memória de conversa por sessão, só em RAM e com janela limitada.

Por que não SQLite: o enunciado não pede retomar conversas entre execuções, e
persistir o histórico guardaria dados pessoais (e-mail, telefone, pedidos) sem
necessidade. Em memória, tudo some com o processo ou com /limpar.

O que entra: apenas o texto do cliente e a resposta final. Resultados brutos de
ferramentas (dados de pedido, por exemplo) nunca são guardados; o contexto de
cada turno é refeito consultando as ferramentas de novo quando preciso.
"""
from __future__ import annotations

from app.core.config import MEMORY_WINDOW


class SessionMemory:
    def __init__(self, window: int = MEMORY_WINDOW) -> None:
        self.window = max(2, window)
        self._messages: list[dict] = []

    def add_exchange(self, user_text: str, assistant_text: str) -> None:
        self._messages.append({"role": "user", "content": user_text})
        self._messages.append({"role": "assistant", "content": assistant_text})
        self._trim()

    def _trim(self) -> None:
        excess = len(self._messages) - self.window
        if excess > 0:
            self._messages = self._messages[excess:]
        # a janela sempre começa em uma fala do cliente
        while self._messages and self._messages[0]["role"] != "user":
            self._messages.pop(0)

    def messages(self) -> list[dict]:
        """Cópia das mensagens da janela atual."""
        return [dict(m) for m in self._messages]

    def user_texts(self) -> list[str]:
        return [m["content"] for m in self._messages if m["role"] == "user"]

    def clear(self) -> None:
        self._messages.clear()

    def __len__(self) -> int:
        return len(self._messages)
