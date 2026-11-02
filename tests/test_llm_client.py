"""Cliente OpenAI-compatível e fábrica, com SDK falso (sem rede)."""
from types import SimpleNamespace as NS

import openai
import pytest

from app.core.config import LLMSettings, load_llm_settings
from app.llm.base import LLMError
from app.llm.factory import create_client
from app.llm.mock import MockLLM
from app.llm.openai_compat import OpenAICompatClient, map_exception, to_openai_tools
from app.tools.registry import tool_specs

SETTINGS = LLMSettings("gemini", "m", "http://x/", "segredo-123")


def fake_sdk(response=None, error=None):
    def create(**kwargs):
        create.kwargs = kwargs
        if error:
            raise error
        return response
    return NS(chat=NS(completions=NS(create=create))), create


def make_error(cls, status=None):
    exc = cls.__new__(cls)
    if status:
        exc.status_code = status
    return exc


def test_converte_texto_e_tool_calls():
    msg = NS(content=None, tool_calls=[NS(id="t1", function=NS(name="search_products",
                                                               arguments='{"query": "violão"}'))])
    sdk, create = fake_sdk(NS(choices=[NS(message=msg)]))
    resp = OpenAICompatClient(SETTINGS, client=sdk).chat([{"role": "user", "content": "oi"}], tool_specs())
    assert resp.tool_calls[0].name == "search_products"
    assert resp.tool_calls[0].arguments == {"query": "violão"}
    assert create.kwargs["tool_choice"] == "auto" and create.kwargs["model"] == "m"
    sent = create.kwargs["tools"]
    assert sent[0]["type"] == "function" and "additionalProperties" not in sent[0]["function"]["parameters"]


def test_resposta_so_texto():
    sdk, _ = fake_sdk(NS(choices=[NS(message=NS(content="Olá", tool_calls=None))]))
    assert OpenAICompatClient(SETTINGS, client=sdk).chat([], []).text == "Olá"


def test_schema_com_tipo_em_lista_e_simplificado():
    order = next(t for t in to_openai_tools(tool_specs()) if t["function"]["name"] == "get_order_status")
    assert order["function"]["parameters"]["properties"]["order_id"]["type"] == "integer"


@pytest.mark.parametrize("exc,category", [
    (make_error(openai.APITimeoutError), "timeout"),
    (make_error(openai.APIConnectionError), "connection"),
    (make_error(openai.RateLimitError, 429), "rate_limit"),
    (make_error(openai.AuthenticationError, 401), "auth"),
    (make_error(openai.APIStatusError, 503), "server_error"),
    (make_error(openai.APIStatusError, 400), "bad_request"),
    (ValueError("x"), "bad_response"),
])
def test_erros_viram_llmerror_com_categoria(exc, category):
    sdk, _ = fake_sdk(error=exc)
    with pytest.raises(LLMError) as info:
        OpenAICompatClient(SETTINGS, client=sdk).chat([], [])
    assert info.value.category == category
    assert "segredo-123" not in str(info.value)


def test_resposta_sem_choices_e_erro_de_argumentos_sem_levantar():
    sdk, _ = fake_sdk(NS(choices=[]))
    with pytest.raises(LLMError) as info:
        OpenAICompatClient(SETTINGS, client=sdk).chat([], [])
    assert info.value.category == "bad_response"
    bad = NS(choices=[NS(message=NS(content=None, tool_calls=[NS(id="1", function=NS(name="x", arguments="{ruim"))]))])
    sdk, _ = fake_sdk(bad)
    call = OpenAICompatClient(SETTINGS, client=sdk).chat([], []).tool_calls[0]
    assert call.arguments == {} and call.arguments_error == "malformed_json"


def test_map_exception_preserva_llmerror():
    err = LLMError("auth")
    assert map_exception(err) is err


def test_fabrica_mock_sem_chave_e_erros_de_configuracao(monkeypatch):
    assert isinstance(create_client(LLMSettings("mock", "", "")), MockLLM)
    with pytest.raises(LLMError) as info:
        create_client(LLMSettings("gemini", "m", "http://x/", ""))
    assert info.value.category == "config"
    with pytest.raises(LLMError):
        create_client(LLMSettings("outro", "m", "u", "k"))
    assert isinstance(create_client(LLMSettings("ollama", "m", "http://localhost:11434/v1", "")),
                      OpenAICompatClient)


def test_configuracao_padrao_e_chave_fora_do_repr(monkeypatch):
    for var in ("LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    s = load_llm_settings()
    assert s.provider == "gemini" and s.base_url.startswith("https://generativelanguage.googleapis.com")
    monkeypatch.setenv("LLM_API_KEY", "abc-secreta")
    monkeypatch.setenv("LLM_MODEL", "outro-modelo")
    s = load_llm_settings("groq")
    assert s.model == "outro-modelo" and "abc-secreta" not in repr(s)
