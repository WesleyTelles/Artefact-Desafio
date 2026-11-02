"""Log JSONL por turno: campos esperados e ausência de PII."""
import json

from app.agent.orchestrator import Agent
from app.core.telemetry import Telemetry, derive_intent
from app.llm.base import LLMError, LLMResponse
from tests.fakes import FakeLLM, text_step, tool_step
from tests.test_agent_guardrails import Recorder

EMAIL = "maria.segredo@exemplo.com"
PHONE = "(67) 98432-1098"


def read_log(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_desligado_por_padrao(monkeypatch, tmp_path):
    monkeypatch.delenv("EMPORIO_LOG_FILE", raising=False)
    Agent(FakeLLM([text_step("oi")])).reply("oi")
    assert list(tmp_path.iterdir()) == [] and not Telemetry.from_env().enabled


def test_habilitado_por_variavel_e_registra_campos(monkeypatch, tmp_path):
    path = tmp_path / "logs" / "agent.jsonl"
    monkeypatch.setenv("EMPORIO_LOG_FILE", str(path))
    llm = FakeLLM([tool_step("get_store_info", {"topic": "hours"}),
                   LLMResponse(text="Abrimos às 9h.", usage={"prompt_tokens": 20, "completion_tokens": 4,
                                                             "total_tokens": 24}, attempts=2)])
    Agent(llm, executor=Recorder(), session_id="sess1").reply("qual o horário?")
    rec = read_log(path)[0]
    assert rec["session_id"] == "sess1" and rec["turn_id"] == 1
    assert rec["tools"][0]["name"] == "get_store_info" and rec["tools"][0]["status"] == "found"
    assert isinstance(rec["tools"][0]["duration_ms"], int)
    assert rec["llm_calls"] == 2 and rec["llm_attempts"] == 3 and isinstance(rec["latency_ms"], int)
    assert rec["tokens"] == {"prompt": 20, "completion": 4, "total": 24}
    assert rec["error_category"] is None and rec["failed"] is False and rec["intent"] == "store_info"


def test_tokens_nulos_e_intent_omitida_sem_ferramenta(tmp_path):
    path = tmp_path / "a.jsonl"
    Agent(FakeLLM([text_step("oi!")]), telemetry=Telemetry(path)).reply("oi")
    rec = read_log(path)[0]
    assert rec["tokens"] == {"prompt": None, "completion": None, "total": None}
    assert "intent" not in rec and rec["tools"] == []


def test_categoria_de_erro_e_turnos_incrementais(tmp_path):
    path = tmp_path / "a.jsonl"
    err = LLMError("auth", hint="verifique LLM_API_KEY", attempts=1)
    agent = Agent(FakeLLM([err, text_step("ok")]), telemetry=Telemetry(path))
    r1 = agent.reply("oi")
    agent.reply("oi de novo")
    recs = read_log(path)
    assert recs[0]["error_category"] == "auth" and recs[0]["failed"] is True
    assert [r["turn_id"] for r in recs] == [1, 2]
    assert r1.operator_hint == "verifique LLM_API_KEY" and "LLM_API_KEY" not in r1.text


def test_log_nao_contem_pii_nem_texto_do_cliente_nem_argumentos(tmp_path):
    path = tmp_path / "a.jsonl"
    llm = FakeLLM([tool_step("get_order_status", {"order_id": 2, "verification": EMAIL}),
                   text_step(f"Pedido de {EMAIL} {PHONE}")])
    Agent(llm, telemetry=Telemetry(path)).reply(f"meu pedido 2, e-mail {EMAIL}, tel {PHONE}")
    raw = path.read_text(encoding="utf-8")
    for secret in (EMAIL, "segredo", "98432", "1098", "meu pedido", "order_id", "arguments"):
        assert secret not in raw
    assert json.loads(raw)["intent"] == "order_status"


def test_nome_de_ferramenta_desconhecida_nao_vaza_para_o_log(tmp_path):
    path = tmp_path / "a.jsonl"
    Agent(FakeLLM([tool_step("tool_com_" + EMAIL, {}), text_step("ok")]), telemetry=Telemetry(path)).reply("x")
    assert EMAIL not in path.read_text(encoding="utf-8")
    assert read_log(path)[0]["tools"][0]["name"] == "unknown_tool"


def test_falha_ao_gravar_nao_derruba_o_atendimento(tmp_path):
    bloqueio = tmp_path / "arquivo"
    bloqueio.write_text("x")
    reply = Agent(FakeLLM([text_step("oi")]), telemetry=Telemetry(bloqueio / "sub" / "a.jsonl")).reply("oi")
    assert reply.text == "oi"


def test_derive_intent():
    assert derive_intent(["check_shipping"]) == "shipping" and derive_intent([]) is None
