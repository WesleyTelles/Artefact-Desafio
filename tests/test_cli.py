from app.agent.orchestrator import Agent
from app.interfaces import cli
from app.llm.mock import MockLLM


def run(inputs, debug=False):
    out = []
    it = iter(inputs)

    def read(prompt):
        try:
            return next(it)
        except StopIteration:
            raise EOFError

    agent = Agent(MockLLM())
    cli.run_chat(agent, read=read, write=out.append, debug=debug)
    return agent, "\n".join(out)


def test_chat_responde_e_sai():
    agent, out = run(["Qual o preço da Takamine GD20?", "/sair"])
    assert "R$ 2.199,00" in out and "Até mais!" in out


def test_limpar_apaga_memoria():
    agent, out = run(["quais violões vocês têm?", "/limpar"])
    assert len(agent.memory) == 0 and "Conversa limpa." in out


def test_debug_mostra_ferramentas_e_argumentos():
    _, out = run(["Qual o preço da Takamine GD20?"], debug=True)
    assert '[ferramenta] search_products({"query": "takamine gd20"}) -> found' in out
    _, quiet = run(["Qual o preço da Takamine GD20?"])
    assert "[ferramenta]" not in quiet


def test_eof_encerra_sem_erro():
    _, out = run([])
    assert "Até mais!" in out


def test_main_sem_chave_da_erro_claro_sem_stacktrace(monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_env_file", lambda: None)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    assert cli.main([]) == 2
    err = capsys.readouterr().err
    assert "LLM_API_KEY" in err and "Traceback" not in err and "--mock" in err


def test_debug_mascara_email_e_telefone_nos_argumentos():
    from app.llm.base import LLMResponse, ToolCall
    from tests.fakes import FakeLLM, text_step
    email, phone = "maria.segredo@exemplo.com", "(67) 98432-1098"
    steps = [LLMResponse(tool_calls=[ToolCall("c", "get_order_status", {"order_id": 2, "verification": email})]),
             LLMResponse(tool_calls=[ToolCall("d", "get_order_status", {"order_id": 2, "verification": phone})]),
             LLMResponse(tool_calls=[ToolCall("e", "search_products", {"query": f"fale com {email} ou 67984321098"})]),
             text_step("ok")]
    out, it = [], iter([f"pedido 2 {email} {phone}", "/sair"])
    cli.run_chat(Agent(FakeLLM(steps)), read=lambda _: next(it), write=out.append, debug=True)
    text = "\n".join(out)
    assert "[ferramenta] get_order_status(" in text and "-> verification_failed" in text
    for secret in ("maria.segredo", "98432", "67984321098"):
        assert secret not in text.split("Atendente:")[0]
    assert '"order_id": 2' in text and "m***@exemplo.com" in text and "(67) *****-1098" in text


def test_dica_ao_operador_vai_para_stderr_e_nao_ao_cliente():
    from app.llm.base import LLMError
    from tests.fakes import FakeLLM
    out, err = [], []
    it = iter(["oi", "/sair"])
    llm = FakeLLM([LLMError("not_found", hint="verifique LLM_MODEL/LLM_BASE_URL")])
    cli.run_chat(Agent(llm), read=lambda _: next(it), write=out.append, write_err=err.append)
    assert any("LLM_MODEL/LLM_BASE_URL" in e for e in err)
    assert "LLM_MODEL" not in "\n".join(out)


def test_categoria_de_falha_aparece_no_debug():
    from app.llm.base import LLMError
    from tests.fakes import FakeLLM
    err = []
    it = iter(["oi", "/sair"])
    cli.run_chat(Agent(FakeLLM([LLMError("rate_limit")])), read=lambda _: next(it), write=lambda s: None,
                 write_err=err.append, debug=True)
    assert err == ["[operador] falha técnica: rate_limit"]
    err.clear()
    it = iter(["oi", "/sair"])
    cli.run_chat(Agent(FakeLLM([LLMError("rate_limit")])), read=lambda _: next(it), write=lambda s: None,
                 write_err=err.append)
    assert err == []
