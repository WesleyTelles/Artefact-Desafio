from datetime import date
import pytest

from app.tools.registry import TOOLS, execute, tool_specs

NOVAS = {"search_store_policies", "check_installments", "check_shipping", "check_return_eligibility",
         "check_pix_discount"}


def test_ferramentas_registradas_com_schema():
    assert NOVAS <= set(TOOLS)
    specs = {s["name"]: s for s in tool_specs()}
    for name in NOVAS:
        assert specs[name]["description"] and specs[name]["parameters"]["type"] == "object"
    assert specs["search_store_policies"]["parameters"]["required"] == ["query"]


def test_busca_via_execute_marca_origem():
    r = execute("search_store_policies", {"query": "horário de sábado"})
    assert r["status"] == "found" and r["source_type"] == "policy_manual"
    assert r["results"][0]["section"] == "2" and r["results"][0]["page_start"] == 2


def test_parcelamento_via_execute():
    r = execute("check_installments", {"amount": 900})
    assert r["max_installments"] == 9 and r["source_type"] == "policy_manual"
    assert r["payment_combination"]["status"] == "not_covered"
    assert execute("check_installments", {"amount": 2000})["payment_combination"]["status"] == "borderline"


def test_frete_via_execute():
    r = execute("check_shipping", {"order_total": 420, "in_metropolitan_region": True})
    assert r["shipping_fee_brl"] == "35.00"
    assert execute("check_shipping", {"order_total": 500, "in_metropolitan_region": True})["status"] == "not_covered"
    assert execute("check_shipping", {"order_total": 800})["status"] == "region_required"


def test_arrependimento_via_execute_com_data_de_referencia():
    hoje = date(2025, 10, 10)
    args = {"received_date": "2025-10-05", "channel": "online"}
    assert execute("check_return_eligibility", args, today=hoje)["status"] == "within_deadline"
    limite = {**args, "received_date": "2025-10-03"}
    assert execute("check_return_eligibility", limite, today=hoje)["status"] == "borderline"
    fora = {**args, "received_date": "2025-10-01"}
    assert execute("check_return_eligibility", fora, today=hoje)["status"] == "outside_deadline"


def test_arrependimento_sem_data_de_referencia_usa_o_dia_atual():
    r = execute("check_return_eligibility", {"received_date": date.today().isoformat(), "channel": "online"})
    assert r["status"] == "within_deadline" and r["days_elapsed"] == 0


def test_pix_via_execute():
    assert execute("check_pix_discount", {"price": 500, "is_promotional": True})["pix_discount_applies"] is False
    assert execute("check_pix_discount", {"price": 500})["pix_price_brl"] == "475.00"


def test_erros_nunca_levantam():
    for name, args in [
        ("search_store_policies", {}),
        ("search_store_policies", {"query": 1}),
        ("check_installments", {"amount": -1}),
        ("check_installments", {"amount": "x"}),
        ("check_shipping", {"order_total": 100, "in_metropolitan_region": "sim"}),
        ("check_return_eligibility", {"received_date": "31/12/2025"}),
        ("check_return_eligibility", {"received_date": "2025-10-01", "channel": "loja"}),
        ("check_pix_discount", {"price": 0}),
    ]:
        r = execute(name, args)
        assert r["status"] == "error" and r["reason"] == "invalid_arguments", (name, args, r)


def test_retorno_da_busca_limita_o_tamanho_dos_trechos():
    r = execute("search_store_policies", {"query": "prazo do SEDEX para outra cidade"})
    assert all(len(x["text"]) <= 620 for x in r["results"])


@pytest.mark.parametrize("pergunta,secao", [
    ("meu violão chegou com defeito", "4.2"),
    ("entregam em Dourados?", "5.2"),
    ("quanto tempo demora o reembolso", "4.1"),
])
def test_perguntas_de_cliente_chegam_a_secao_certa(pergunta, secao):
    r = execute("search_store_policies", {"query": pergunta})
    assert r["status"] == "found"
    assert secao in [x["section"] for x in r["results"]]


def test_reembolso_avisa_que_o_inicio_da_contagem_nao_esta_definido():
    r = execute("search_store_policies", {"query": "quanto tempo demora o reembolso"})
    assert r["status"] == "found"
    assert "não define de que evento" in " ".join(r.get("notes", []))
