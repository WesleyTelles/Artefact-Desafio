"""Orçamento de tempo por turno, resposta vazia do provedor e falha parcial de ferramentas."""
import json
from types import SimpleNamespace as NS

import pytest

from app.agent.orchestrator import Agent
from app.agent.prompts import TIMEOUT_MESSAGE, UNAVAILABLE_MESSAGE
from app.core import config
from app.core.config import LLMSettings
from app.core.telemetry import Telemetry
from app.llm.base import LLMError
from app.llm.openai_compat import OpenAICompatClient
from tests.fakes import FakeLLM, text_step, tool_step
from tests.test_llm_resilience import OK, Scripted, status_error

SETTINGS = LLMSettings("gemini", "m", "http://x/", "segredo-123")
EMPTY = NS(choices=[NS(message=NS(content=None, tool_calls=None))], usage=None)
NO_CHOICES = NS(choices=[], usage=None)


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.now += s


def make(sdk, clock, **kw):
    kw.setdefault("jitter", lambda: 1.0)
    return OpenAICompatClient(SETTINGS, client=sdk, sleep=clock.sleep, clock=clock, **kw)


# --- orçamento no cliente -----------------------------------------------------------------------
def test_retry_nao_ultrapassa_o_orcamento():
    clock = Clock()
    sdk = Scripted(*[status_error(429, {"retry-after": "8"})] * 3)
    c = make(sdk, clock, max_attempts=5)
    with pytest.raises(LLMError) as info:
        c.chat([], [], timeout=10)
    assert info.value.category == "budget"
    assert sdk.calls == 2  # a segunda espera de 8 s estouraria os 10 s: desiste sem dormir
    assert clock.now <= 10


def test_sem_orcamento_o_comportamento_antigo_continua():
    clock = Clock()
    sdk = Scripted(status_error(503), OK)
    assert make(sdk, clock).chat([], []).text == "ok"


def test_requisicao_recebe_o_tempo_restante_como_timeout():
    seen = []

    class Sdk(Scripted):
        def _create(self, **kw):
            seen.append(kw.get("timeout"))
            return super()._create(**kw)

    clock = Clock()
    make(Sdk(OK), clock, timeout=30.0).chat([], [], timeout=5)
    assert seen == [5]
    seen.clear()
    make(Sdk(OK), clock, timeout=30.0).chat([], [], timeout=100)
    assert seen == [30.0]


def test_orcamento_esgotado_antes_da_chamada_nao_chama_o_provedor():
    sdk = Scripted(OK)
    with pytest.raises(LLMError) as info:
        make(sdk, Clock()).chat([], [], timeout=0)
    assert info.value.category == "budget" and sdk.calls == 0


# --- resposta inválida do provedor --------------------------------------------------------------
def test_resposta_vazia_e_repetida_uma_vez_e_recupera():
    sdk = Scripted(EMPTY, OK)
    resp = make(sdk, Clock()).chat([], [])
    assert resp.text == "ok" and resp.attempts == 2 and sdk.calls == 2


def test_resposta_vazia_persistente_falha_com_so_uma_repeticao():
    sdk = Scripted(EMPTY, EMPTY, EMPTY)
    with pytest.raises(LLMError) as info:
        make(sdk, Clock(), max_attempts=5).chat([], [])
    assert info.value.category == "bad_response" and sdk.calls == 2


@pytest.mark.parametrize("resp", [NO_CHOICES, NS(), NS(choices=None)])
def test_resposta_sem_choices_nao_e_repetida_indefinidamente(resp):
    sdk = Scripted(resp, resp, resp)
    with pytest.raises(LLMError) as info:
        make(sdk, Clock(), max_attempts=5).chat([], [])
    assert info.value.category == "bad_response" and sdk.calls == 1


def test_estrutura_invalida_nao_e_repetida():
    sdk = Scripted(NS(choices=[NS()]), OK)  # sem .message: erro de estrutura
    with pytest.raises(LLMError) as info:
        make(sdk, Clock()).chat([], [])
    assert info.value.category == "bad_response" and sdk.calls == 1


def test_json_incompleto_de_ferramenta_chega_marcado_sem_retry():
    tc = NS(id="c1", function=NS(name="search_products", arguments='{"query": "viol'))
    sdk = Scripted(NS(choices=[NS(message=NS(content=None, tool_calls=[tc]))], usage=None))
    resp = make(sdk, Clock()).chat([], [])
    assert resp.tool_calls[0].arguments_error == "malformed_json" and sdk.calls == 1


def test_resposta_vazia_respeita_o_orcamento():
    sdk = Scripted(EMPTY, OK)
    with pytest.raises(LLMError):
        make(sdk, Clock(), backoff_base=3.0).chat([], [], timeout=2)
    assert sdk.calls == 1


# --- orçamento no agente ------------------------------------------------------------------------
class SlowLLM(FakeLLM):
    """Cada chamada gasta tempo do relógio falso."""

    def __init__(self, steps, clock, cost):
        super().__init__(steps)
        self.clock, self.cost, self.timeouts = clock, cost, []

    def chat(self, messages, tools, *, timeout=None):
        self.timeouts.append(timeout)
        self.clock.now += self.cost
        return super().chat(messages, tools, timeout=timeout)


def test_agente_interrompe_com_mensagem_clara_quando_o_tempo_acaba(tmp_path):
    clock = Clock()
    log = tmp_path / "t.jsonl"
    llm = SlowLLM([tool_step("get_store_info", {"topic": "contacts"}),
                   tool_step("get_store_info", {"topic": "hours"}), text_step("nunca chega")], clock, cost=40)
    agent = Agent(llm, turn_timeout=60, clock=clock, telemetry=Telemetry(str(log)))
    reply = agent.reply("qual o horário?")
    assert reply.text == TIMEOUT_MESSAGE and reply.failed and reply.error_category == "turn_timeout"
    assert "3341" in reply.text  # orienta o cliente a falar com a loja
    assert llm.timeouts == [60, 20]  # a segunda chamada recebe só o que restava
    rec = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert rec["error_category"] == "turn_timeout" and rec["failed"] is True


def test_agente_converte_budget_do_cliente_em_mensagem_de_tempo():
    agent = Agent(FakeLLM([LLMError("budget", "x", attempts=2)]), turn_timeout=60)
    reply = agent.reply("oi")
    assert reply.text == TIMEOUT_MESSAGE and reply.error_category == "turn_timeout"


def test_timeout_do_turno_e_configuravel_por_ambiente(monkeypatch):
    monkeypatch.setenv("TURN_TIMEOUT_SECONDS", "90")
    assert config.turn_timeout_from_env() == 90
    monkeypatch.setenv("TURN_TIMEOUT_SECONDS", "lixo")
    assert config.turn_timeout_from_env() == config.TURN_TIMEOUT_SECONDS
    monkeypatch.setenv("TURN_TIMEOUT_SECONDS", "0.1")
    assert config.turn_timeout_from_env() == 5


# --- falha parcial de ferramentas ---------------------------------------------------------------
def _executor(fail):
    from app.tools.registry import execute

    def run(name, args):
        if name in fail:
            return {"status": "error", "reason": "internal_error", "message": "falha simulada"}
        return execute(name, args)
    return run


def test_falha_parcial_o_modelo_recebe_os_dois_resultados_e_a_resposta_parcial_e_preservada():
    seen = {}

    def final(messages):
        seen["tools"] = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
        return text_step("O horário é esse; não consegui consultar a política agora.")

    llm = FakeLLM([tool_step("get_store_info", {"topic": "hours"}, "a"),
                   tool_step("search_store_policies", {"query": "troca"}, "b"), final])
    reply = Agent(llm, executor=_executor({"search_store_policies"})).reply("horário e política de troca?")
    statuses = {t["tool"]: t["data"]["status"] for t in seen["tools"]}
    assert statuses["get_store_info"] != "error" and statuses["search_store_policies"] == "error"
    assert not reply.failed and "não consegui" in reply.text


def test_todas_as_ferramentas_falham_resposta_fixa_sem_dado_inventado():
    llm = FakeLLM([tool_step("search_products", {"query": "Takamine GD20"}),
                   text_step("O Takamine GD20 custa R$ 1.234,00")])
    reply = Agent(llm, executor=_executor({"search_products"})).reply("quanto custa o Takamine GD20?")
    assert reply.text == UNAVAILABLE_MESSAGE and reply.failed and reply.error_category == "tool_error"
    assert "1.234" not in reply.text


def test_ferramenta_que_falha_e_depois_funciona_nao_marca_o_turno_como_falho():
    from app.tools.registry import execute
    state = {"n": 0}

    def flaky(name, args):
        state["n"] += 1
        if state["n"] == 1:
            return {"status": "error", "reason": "internal_error", "message": "x"}
        return execute(name, args)

    llm = FakeLLM([tool_step("get_store_info", {"topic": "hours"}, "a"),
                   tool_step("get_store_info", {"topic": "contacts"}, "b"), text_step("Aqui estão os dados.")])
    reply = Agent(llm, executor=flaky).reply("horário e contatos?")
    assert not reply.failed and reply.text == "Aqui estão os dados."
