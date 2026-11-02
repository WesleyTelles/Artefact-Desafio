"""Erros do provedor (categorias), retry com backoff e Retry-After, com SDK/httpx falsos e sem dormir."""
from types import SimpleNamespace as NS

import openai
import pytest

from app.core.config import LLMSettings, load_llm_settings
from app.llm.base import LLMError
from app.llm.openai_compat import OpenAICompatClient

SETTINGS = LLMSettings("gemini", "m", "http://x/", "segredo-123")
REQ = NS(method="POST", url="http://x/chat")  # o SDK só guarda a requisição; sem httpx real
OK = NS(choices=[NS(message=NS(content="ok", tool_calls=None))],
        usage=NS(prompt_tokens=10, completion_tokens=5, total_tokens=15))


def status_error(code, headers=None, body="corpo-bruto-secreto"):
    resp = NS(status_code=code, headers=headers or {}, request=REQ, text=body)
    cls = {400: openai.BadRequestError, 401: openai.AuthenticationError, 403: openai.PermissionDeniedError,
           404: openai.NotFoundError, 429: openai.RateLimitError}.get(code)
    if cls is None:
        cls = openai.InternalServerError if code >= 500 else openai.APIStatusError
    return cls(f"erro {code}", response=resp, body=None)


class Scripted:
    """SDK falso: cada chamada consome um item (exceção é levantada, outro valor é devolvido)."""

    def __init__(self, *items):
        self.items = list(items)
        self.calls = 0
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kwargs):
        self.calls += 1
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(sdk, **kw):
    sleeps = []
    kw.setdefault("jitter", lambda: 1.0)
    c = OpenAICompatClient(SETTINGS, client=sdk, sleep=sleeps.append, **kw)
    return c, sleeps


@pytest.mark.parametrize("code,category", [(400, "bad_request"), (401, "auth"), (403, "auth"), (404, "not_found"),
                                           (422, "bad_request"), (429, "rate_limit"), (500, "server_error"),
                                           (503, "server_error")])
def test_categorias_por_status_http(code, category):
    sdk = Scripted(*[status_error(code)] * 3)
    c, _ = client(sdk)
    with pytest.raises(LLMError) as info:
        c.chat([], [])
    assert info.value.category == category
    assert "segredo-123" not in str(info.value) and "corpo-bruto-secreto" not in str(info.value)


def test_timeout_e_conexao():
    for exc, category in ((openai.APITimeoutError(request=REQ), "timeout"),
                          (openai.APIConnectionError(request=REQ), "connection")):
        c, _ = client(Scripted(exc, exc, exc))
        with pytest.raises(LLMError) as info:
            c.chat([], [])
        assert info.value.category == category and info.value.attempts == 3


def test_404_traz_dica_de_modelo_e_url():
    c, _ = client(Scripted(status_error(404)))
    with pytest.raises(LLMError) as info:
        c.chat([], [])
    assert "LLM_MODEL" in info.value.hint and "LLM_BASE_URL" in info.value.hint


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_permanentes_nunca_sao_repetidos(code):
    sdk = Scripted(status_error(code), OK)
    c, sleeps = client(sdk)
    with pytest.raises(LLMError):
        c.chat([], [])
    assert sdk.calls == 1 and sleeps == []


@pytest.mark.parametrize("first", [status_error(429), status_error(500), status_error(503),
                                   openai.APITimeoutError(request=REQ), openai.APIConnectionError(request=REQ)])
def test_transitorios_sao_repetidos_e_recuperam(first):
    sdk = Scripted(first, OK)
    c, sleeps = client(sdk)
    resp = c.chat([], [])
    assert resp.text == "ok" and resp.attempts == 2 and sdk.calls == 2 and len(sleeps) == 1


def test_maximo_de_tentativas_e_backoff_exponencial_com_teto():
    sdk = Scripted(*[status_error(503)] * 5)
    c, sleeps = client(sdk, max_attempts=4, backoff_base=1.0, backoff_max=3.0)
    with pytest.raises(LLMError) as info:
        c.chat([], [])
    assert sdk.calls == 4 and info.value.attempts == 4
    assert sleeps == [1.0, 2.0, 3.0]  # jitter 1.0; terceira espera limitada pelo teto


def test_padrao_sao_tres_tentativas_no_total():
    sdk = Scripted(*[status_error(500)] * 5)
    c, sleeps = client(sdk)
    with pytest.raises(LLMError):
        c.chat([], [])
    assert sdk.calls == 3 and len(sleeps) == 2


def test_jitter_reduz_a_espera_entre_metade_e_o_total():
    sdk = Scripted(status_error(500), OK)
    c, sleeps = client(sdk, backoff_base=2.0, jitter=lambda: 0.0)
    c.chat([], [])
    assert sleeps == [1.0]


def test_retry_after_e_respeitado_e_limitado_pelo_teto():
    c, sleeps = client(Scripted(status_error(429, {"retry-after": "4"}), OK), retry_after_cap=10)
    c.chat([], [])
    assert sleeps == [4.0]
    c, sleeps = client(Scripted(status_error(429, {"retry-after": "999"}), OK), retry_after_cap=10)
    c.chat([], [])
    assert sleeps == [10.0]
    c, sleeps = client(Scripted(status_error(429, {"retry-after": "amanha"}), OK), backoff_base=1.0)
    c.chat([], [])
    assert sleeps == [1.0]  # valor inválido: cai no backoff


def test_sdk_sem_retry_proprio_e_max_attempts_configuravel(monkeypatch):
    captured = {}
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: captured.update(kw) or NS())
    OpenAICompatClient(SETTINGS)
    assert captured["max_retries"] == 0
    monkeypatch.setenv("LLM_MAX_ATTEMPTS", "5")
    assert load_llm_settings("gemini").max_attempts == 5
    monkeypatch.setenv("LLM_MAX_ATTEMPTS", "abc")
    assert load_llm_settings("gemini").max_attempts == 3


def test_usage_e_extra_content_preservados():
    msg = NS(content=None, tool_calls=[NS(id="t", function=NS(name="get_store_info", arguments="{}"),
                                          extra_content={"google": {"thought_signature": "sig"}})])
    sdk = Scripted(NS(choices=[NS(message=msg)], usage=NS(prompt_tokens=7, completion_tokens=3, total_tokens=10)))
    resp, _ = client(sdk)[0].chat([], []), None
    assert resp.tool_calls[0].extra == {"google": {"thought_signature": "sig"}}
    assert resp.usage == {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}
    sdk = Scripted(NS(choices=[NS(message=NS(content="x", tool_calls=None))]))
    assert client(sdk)[0].chat([], []).usage is None
