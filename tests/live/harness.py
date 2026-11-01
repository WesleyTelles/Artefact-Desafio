"""Infraestrutura dos cenários com LLM real: grava chamadas e aplica asserções semânticas.

Usado pelo runner (scripts/run_scenarios.py) e pelos testes `live`. Nada aqui lê ou imprime a
chave do provedor: o cliente é criado pelo próprio app (app.llm).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable

from app.agent.orchestrator import Agent, AgentReply
from app.data.loader import get_store
from app.llm.base import LLMError
from app.tools.products import product_summary
from app.tools.registry import execute

Check = Callable[["TurnRecord"], "str | None"]


@dataclass
class TurnRecord:
    question: str
    reply: AgentReply
    calls: list[tuple[str, dict, dict]] = field(default_factory=list)  # (ferramenta, args, resultado)

    @property
    def text(self) -> str:
        return self.reply.text

    @property
    def tool_names(self) -> list[str]:
        return [c[0] for c in self.calls]


@dataclass
class Run:
    scenario_id: str
    turns: list[TurnRecord] = field(default_factory=list)
    llm_errors: list[str] = field(default_factory=list)
    llm_requests: int = 0

    @property
    def rate_limited(self) -> bool:
        return "rate_limit" in self.llm_errors


@dataclass
class Scenario:
    id: str
    name: str
    turns: list[str]
    checks: list[Check]  # aplicadas sobre a última rodada, salvo `all_turns`
    group: str = "core"
    inject: Callable[[str, dict, dict], dict] | None = None  # (ferramenta, args, resultado) -> resultado
    fail_tool: str | None = None  # força falha técnica dessa ferramenta
    note: str = ""


class _RecordingLLM:
    def __init__(self, inner, run: Run) -> None:
        self.inner, self.run = inner, run

    def chat(self, messages, tools):
        self.run.llm_requests += 1
        try:
            return self.inner.chat(messages, tools)
        except LLMError as exc:
            self.run.llm_errors.append(exc.category)
            raise


def run_scenario(scenario: Scenario, llm) -> Run:
    run = Run(scenario.id)
    current: list[tuple[str, dict, dict]] = []

    def executor(name, args=None, **kw):
        if scenario.fail_tool == name:
            result = {"status": "error", "reason": "internal_error", "message": "Falha técnica injetada."}
        else:
            result = execute(name, args, **kw)
            if scenario.inject:
                result = scenario.inject(name, args or {}, result)
        current.append((name, dict(args or {}), result))
        return result

    agent = Agent(_RecordingLLM(llm, run), executor=executor)
    for question in scenario.turns:
        current.clear()
        reply = agent.reply(question)
        run.turns.append(TurnRecord(question, reply, list(current)))
        if run.rate_limited:
            break
    return run


def evaluate(scenario: Scenario, run: Run) -> list[str]:
    """Lista de falhas (vazia = passou). Inconclusivo (429) é tratado por quem chama."""
    if len(run.turns) < len(scenario.turns):
        return ["conversa incompleta"]
    return [msg for check in scenario.checks if (msg := check(run.turns[-1]))]


# --- utilidades de asserção -------------------------------------------------------------
def norm(text: str) -> str:
    base = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in base if not unicodedata.combining(c))


def has_any(text: str, *needles: str) -> bool:
    n = norm(text)
    return any(norm(x) in n for x in needles)


_PRICE_RE = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)")


def prices_in(text: str) -> list[Decimal]:
    return [Decimal(m.replace(".", "").replace(",", ".")) for m in _PRICE_RE.findall(text)]


def known_prices() -> set[Decimal]:
    store = get_store()
    out: set[Decimal] = set()
    for p in store.products.values():
        out.add(Decimal(p.price_brl))
        promo = product_summary(store, p)["promotion"]
        if promo:
            out.add(Decimal(promo["promotional_price_brl"]))
    return out


def unknown_prices(text: str) -> list[Decimal]:
    known = known_prices() | {Decimal(1000)}  # teto citado nas perguntas dos cenários
    return [p for p in prices_in(text) if p not in known]
