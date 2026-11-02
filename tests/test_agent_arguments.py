"""Argumentos inválidos de ferramenta: erro estruturado, uma correção por turno, sem executar nem entrar em loop."""
import json

import pytest

from app.agent.orchestrator import ARGS_FAILURE_MESSAGE, Agent
from app.llm.base import LLMResponse, ToolCall
from tests.fakes import FakeLLM, last_tool_data, text_step, tool_step
from tests.test_agent_guardrails import Recorder


def bad_json(error="malformed_json", name="search_products", call_id="c1"):
    return LLMResponse(tool_calls=[ToolCall(call_id, name, {}, arguments_error=error)])


def run(steps, **kw):
    llm = FakeLLM(steps)
    ex = Recorder()
    return Agent(llm, executor=ex, **kw), llm, ex


@pytest.mark.parametrize("step,reason", [
    (bad_json("malformed_json"), "invalid_arguments"),               # JSON malformado/truncado
    (bad_json("not_object"), "invalid_arguments"),                   # JSON válido mas não objeto
    (tool_step("check_installments", {}), "invalid_arguments"),      # campo obrigatório ausente (incompleto)
    (tool_step("check_installments", {"amount": "mil"}), "invalid_arguments"),   # tipo errado
    (tool_step("get_store_info", {"topic": "address", "extra": 1}), "invalid_arguments"),  # campo extra
    (tool_step("get_store_info", {"topic": "xyz"}), "invalid_arguments"),        # enum inválido
    (tool_step("apagar_tudo", {}), "unknown_tool"),                  # ferramenta inexistente
])
def test_erro_estruturado_volta_ao_modelo_e_nada_executa(step, reason):
    agent, llm, ex = run([step, text_step("Não consegui.")])
    reply = agent.reply("oi")
    data = last_tool_data(llm.seen[1])
    assert data["status"] == "error" and data["reason"] == reason
    assert data["tool"] == step.tool_calls[0].name and data["expected"] and data["detail"]
    assert ex.calls == []  # argumentos não validados nunca chegam à ferramenta
    assert reply.trace[0]["status"] == "error" and not reply.failed


def test_erro_traz_schema_resumido():
    agent, llm, _ = run([tool_step("check_installments", {}), text_step("ok")])
    agent.reply("parcelas?")
    expected = last_tool_data(llm.seen[1])["expected"]
    assert expected["required"] == ["amount"] and expected["properties"]["amount"] == "number"


def test_uma_correcao_e_aceita_e_executa_validada():
    agent, llm, ex = run([bad_json(), tool_step("search_products", {"query": "violão"}, "c2"),
                          text_step("Achei.")])
    reply = agent.reply("violão")
    assert ex.calls == [("search_products", {"query": "violão"})]
    assert reply.text == "Achei." and not reply.failed
    assert len(llm.seen) == 3  # sem chamadas extras ao LLM


def test_correcao_que_falha_encerra_com_resposta_fixa_sem_novas_chamadas():
    agent, llm, ex = run([bad_json(), bad_json(call_id="c2"), text_step("nunca deve ser pedido")])
    reply = agent.reply("violão")
    assert reply.text == ARGS_FAILURE_MESSAGE and reply.failed
    assert reply.error_category == "invalid_arguments"
    assert len(llm.seen) == 2 and ex.calls == [] and len(llm.steps) == 1


def test_limite_de_correcoes_e_configuravel():
    steps = [bad_json(call_id=f"c{i}") for i in range(2)] + [text_step("ok")]
    agent, llm, _ = run(steps, max_arg_corrections=2)
    reply = agent.reply("x")
    assert not reply.failed and len(llm.seen) == 3
    agent, llm, _ = run([bad_json(call_id=f"c{i}") for i in range(5)], max_arg_corrections=2)
    assert agent.reply("x").failed and len(llm.seen) == 3
    agent, llm, _ = run([bad_json(call_id=f"c{i}") for i in range(5)], max_arg_corrections=0)
    assert agent.reply("x").failed and len(llm.seen) == 1


def test_sem_loop_infinito_com_modelo_que_insiste():
    agent, llm, _ = run([bad_json(call_id=f"c{i}") for i in range(50)], max_iterations=50)
    assert agent.reply("x").failed
    assert len(llm.seen) == 2


def test_mensagem_do_assistente_nao_reenvia_argumentos_quebrados():
    agent, llm, _ = run([bad_json(), text_step("ok")])
    agent.reply("x")
    assistant = next(m for m in llm.seen[1] if m["role"] == "assistant")
    assert json.loads(assistant["tool_calls"][0]["function"]["arguments"]) == {}


def test_erro_de_argumento_nao_conta_como_falha_tecnica():
    agent, _, _ = run([tool_step("check_installments", {}), text_step("Preciso do valor da compra.")])
    reply = agent.reply("parcelas?")
    assert reply.text == "Preciso do valor da compra." and not reply.failed
