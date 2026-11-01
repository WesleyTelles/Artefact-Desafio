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
