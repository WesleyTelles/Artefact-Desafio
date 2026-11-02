"""Infraestrutura dos cenários com LLM real: grava chamadas e aplica asserções semânticas.

Usado pelo runner (scripts/run_scenarios.py) e pelos testes `live`. Nada aqui lê ou imprime a
chave do provedor: o cliente é criado pelo próprio app (app.llm).
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Callable

from app.agent.orchestrator import Agent, AgentReply
from app.agent.prompts import build_system_prompt
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
    llm_attempts: int = 0          # chamadas ao provedor, contando retries do cliente
    latency_ms: int = 0            # tempo total (parede) da conversa, inclui backoff de retry
    usage: list[dict] = field(default_factory=list)  # `usage` informado pelo provedor, por resposta

    @property
    def tokens(self) -> dict | None:
        """Soma de tokens informados pelo provedor; None se nenhuma resposta trouxe `usage`."""
        if not self.usage:
            return None
        out = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            vals = [u[key] for u in self.usage if isinstance(u.get(key), int)]
            out[key] = sum(vals) if vals else None
        return out

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
    expected: str = ""  # resultado esperado (descrição legível, vai para runs.jsonl)
    # Ferramentas esperadas: cada grupo exige ao menos uma das ferramentas listadas em alguma rodada.
    expected_tools: tuple[tuple[str, ...], ...] = ()
    expect_no_tools: bool = False  # True: o cenário exige não consultar nenhuma ferramenta


class _RecordingLLM:
    def __init__(self, inner, run: Run) -> None:
        self.inner, self.run = inner, run

    def chat(self, messages, tools, *, timeout=None):
        self.run.llm_requests += 1
        try:
            resp = self.inner.chat(messages, tools, timeout=timeout)
        except LLMError as exc:
            self.run.llm_errors.append(exc.category)
            self.run.llm_attempts += exc.attempts
            raise
        self.run.llm_attempts += getattr(resp, "attempts", 1)
        if getattr(resp, "usage", None):
            self.run.usage.append(dict(resp.usage))
        return resp


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

    agent = Agent(_RecordingLLM(llm, run), executor=executor)  # Agent novo = sessão e memória novas
    started = time.perf_counter()
    for question in scenario.turns:
        current.clear()
        reply = agent.reply(question)
        run.turns.append(TurnRecord(question, reply, list(current)))
        if run.rate_limited:
            break
    run.latency_ms = round((time.perf_counter() - started) * 1000)
    return run


def evaluate(scenario: Scenario, run: Run) -> list[str]:
    """Lista de falhas (vazia = passou). Inconclusivo (429) é tratado por quem chama."""
    if len(run.turns) < len(scenario.turns):
        return ["conversa incompleta"]
    return [msg for check in scenario.checks if (msg := check(run.turns[-1]))]


def tools_ok(scenario: Scenario, run: Run) -> bool | None:
    """A ferramenta esperada foi acionada? None quando o cenário não define expectativa."""
    called = [name for turn in run.turns for name in turn.tool_names]
    if scenario.expect_no_tools:
        return not called
    if not scenario.expected_tools:
        return None
    return all(any(n in called for n in group) for group in scenario.expected_tools)


# --- detecção de informação inventada ----------------------------------------------------
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")
_UNIT_RE = re.compile(r"(?<![\d.,])(\d+)(?:\s*(?:a|ate|-)\s*(\d+))?\s*"
                      r"(dias?|horas?|h|x|vezes|%|cordas?|teclas?|unidades?|pecas?)(?![a-z])")


def numbers_in(text: str) -> set[Decimal]:
    """Todos os números do texto, com as duas leituras possíveis de '.' (milhar ou decimal)."""
    out: set[Decimal] = set()
    for tok in _NUM_RE.findall(text):
        variants = []
        if "," in tok:
            variants.append(tok.replace(".", "").replace(",", "."))
        elif "." in tok:
            variants.append(tok)
            if re.fullmatch(r"\d{1,3}(\.\d{3})+", tok):
                variants.append(tok.replace(".", ""))
        else:
            variants.append(tok)
        for v in variants:
            try:
                out.add(Decimal(v))
            except InvalidOperation:
                continue
    return out


def _derived(prices: set[Decimal]) -> set[Decimal]:
    """Valores que o agente pode legitimamente derivar de um preço de ferramenta (PIX 5%, parcelas)."""
    out: set[Decimal] = set()
    for p in prices:
        if p < 50:
            continue
        for v in (p * Decimal("0.95"), *(p / n for n in range(1, 13))):
            out.add(v.quantize(Decimal("0.01")))
            out.add(v.quantize(Decimal("1"), rounding="ROUND_DOWN"))
    return out


def allowed_numbers(run: Run, upto: int) -> set[Decimal]:
    """Números que a resposta do turno `upto` pode citar: resultados das ferramentas até esse turno,
    perguntas do cliente e dados fixos do prompt do sistema (endereço, horário, contatos)."""
    chunks = [build_system_prompt(date.today())]
    tool_prices: set[Decimal] = set()
    for turn in run.turns[: upto + 1]:
        chunks.append(turn.question)
        for _, _, result in turn.calls:
            blob = json.dumps(result, ensure_ascii=False, default=str)
            chunks.append(blob)
            tool_prices |= numbers_in(blob)
    allowed = numbers_in(" ".join(chunks)) | {Decimal(0), Decimal(1)}
    # números falados pelo cliente ("até mil reais", "2 mil"): a resposta pode repeti-los em dígitos
    for q in (turn.question for turn in run.turns[: upto + 1]):
        for count in re.findall(r"(?:(\d+)\s+)?\bmil\b", norm(q)):
            allowed.add(Decimal(count or 1) * 1000)
    return allowed | _derived(tool_prices)


def invented_info(run: Run) -> list[str]:
    """Preços (R$), prazos, horas, parcelas, percentuais e contagens que a resposta cita e que não
    aparecem em nenhum resultado de ferramenta, pergunta do cliente ou dado fixo do prompt."""
    found: list[str] = []
    for i, turn in enumerate(run.turns):
        allowed = allowed_numbers(run, i)
        for price in prices_in(turn.text):
            if price not in allowed:
                found.append(f"preço R$ {price}")
        for first, second, unit in _UNIT_RE.findall(norm(turn.text)):
            for raw in (first, second):
                if raw and Decimal(raw) not in allowed:
                    found.append(f"{raw} {unit}")
    return sorted(set(found))


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
