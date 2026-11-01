"""FakeLLM roteirizado por teste: cada passo é uma resposta, um erro ou uma função das mensagens."""
from __future__ import annotations

import json
from typing import Callable

from app.llm.base import LLMError, LLMResponse, ToolCall


def tool_step(name: str, args: dict, call_id: str = "c1") -> LLMResponse:
    return LLMResponse(tool_calls=[ToolCall(call_id, name, args)])


def text_step(text: str) -> LLMResponse:
    return LLMResponse(text=text)


def last_tool_data(messages: list[dict]) -> dict:
    tools = [m for m in messages if m["role"] == "tool"]
    return json.loads(tools[-1]["content"])["data"]


class FakeLLM:
    def __init__(self, steps: list) -> None:
        self.steps = list(steps)
        self.seen: list[list[dict]] = []

    def chat(self, messages, tools):
        self.seen.append([dict(m) for m in messages])
        if not self.steps:
            raise AssertionError("FakeLLM sem passos restantes")
        step = self.steps.pop(0)
        if isinstance(step, LLMError):
            raise step
        return step(messages) if isinstance(step, Callable) else step
