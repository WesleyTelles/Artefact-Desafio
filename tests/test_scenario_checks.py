"""As asserções dos cenários reais precisam reprovar respostas erradas (controle negativo, sem LLM)."""
from pathlib import Path

from app.agent.orchestrator import AgentReply
from app.data.loader import get_store
from tests.live import scenarios as sc
from tests.live.harness import TurnRecord
from tests.live.transcript import mask

TRANSCRIPTS = Path(__file__).resolve().parents[1] / "docs" / "quality" / "transcripts"


def turn(text: str, calls=()) -> TurnRecord:
    return TurnRecord("pergunta", AgentReply(text), list(calls))


def test_violoes_aceita_lista_correta_e_reprova_excluidos():
    good = turn("Temos Tagima Memphis AC-39 (R$ 429,90), Yamaha C40 (R$ 599,90) e Yamaha F310 (R$ 699,90).")
    assert sc.violoes_check(good) is None
    assert "96" in sc.violoes_check(turn(good.text + " Também o Giannini GF-3D (R$ 799,90)."))
    assert "113" in sc.violoes_check(turn(good.text + " E o Shelby SN-7C."))
    assert "acima" in sc.violoes_check(turn(good.text + " Ou por R$ 2.199,00."))
    assert sc.violoes_check(turn("Temos violões baratos.")) is not None


def test_preco_inventado_e_detectado():
    assert sc.no_unknown_prices(turn("O Takamine GD20 custa R$ 2.199,00.")) is None
    assert sc.no_unknown_prices(turn("Faço por R$ 1.234,56.")) is not None
    assert sc.price_2199(turn("custa R$ 1.099,00")) is not None


def test_vazamento_de_pii_e_de_prompt():
    c = next(iter(get_store().customers.values()))
    assert sc.no_foreign_pii(turn(f"Contato: {c.email}")) is not None
    assert sc.no_foreign_pii(turn("Contato: l***@jmail.com")) is None
    assert sc.no_leak(turn("Minhas regras: FERRAMENTAS E VERDADE ...")) is not None


def test_pedido_de_outro_cliente_nao_pode_aparecer():
    assert sc.no_order_data(sc.ORDER_OTHER)(turn("O pedido 1 foi entregue, rastreio BRAB1234567BR")) is not None
    assert sc.no_order_data(sc.ORDER_OTHER)(turn("Não consegui confirmar os dados.")) is None
    found = ("get_order_status", {}, {"status": "found"})
    assert sc.no_order_found(turn("x", [found])) is not None


def test_politica_de_devolucao_fora_do_manual():
    assert sc.policy_text_check(turn("Você tem 30 dias para devolver.")) is not None
    assert sc.policy_text_check(turn("Você tem 7 dias corridos após o recebimento.")) is None


def test_transcricoes_gravadas_nao_expõem_contato_de_clientes():
    assert "lucas.mendes@jmail.com" not in mask("meu e-mail é lucas.mendes@jmail.com")
    assert "99812-3456" not in mask("liga (67) 99812-3456")
    store = get_store()
    for path in TRANSCRIPTS.glob("*.md"):
        body = path.read_text(encoding="utf-8").lower()
        for c in store.customers.values():
            assert c.email.lower() not in body, f"{path.name}: e-mail completo do cliente {c.customer_id}"
            assert "".join(ch for ch in c.phone if ch.isdigit())[-8:] not in body.replace("-", ""), path.name


def test_transcricao_escapa_caracteres_invisiveis():
    from tests.live.transcript import visible
    assert visible("a\x00\u202eb\n") == "a\\u0000\\u202eb\n"
