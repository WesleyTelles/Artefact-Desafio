from datetime import date

import pytest

from app.core.exceptions import ToolInputError
from app.knowledge import rules


@pytest.mark.parametrize("amount,maximo", [
    (900, 9), (1200, 12), (1199.99, 11), (100, 2), (300, 3), (320, 4), (479.99, 5), (480, 6), (700, 7), (650, 6),
])
def test_parcelamento_maximo(amount, maximo):
    r = rules.installment_options(amount)
    assert r["max_installments"] == maximo and r["interest"] == "sem juros"
    assert "§3.1" in r["source"]


def test_parcelamento_900_nao_permite_12x():
    r = rules.installment_options(900)
    assert 12 not in r["allowed_installments"] and r["installment_value_brl"] == "100.00"
    assert r["status"] == "ok" and r["ambiguity_flags"] == []


def test_parcela_abaixo_de_50_em_ate_3x_e_ambigua():
    r = rules.installment_options(120)
    assert r["status"] == "ambiguous" and r["ambiguity_flags"] == ["I-4"]
    assert r["unclear_installments"] == [3] and r["max_installments"] == 2


def test_valor_pequeno_so_a_vista_sem_afirmar_proibicao():
    r = rules.installment_options(40)
    assert r["allowed_installments"] == [1] and r["unclear_installments"] == [2, 3]


@pytest.mark.parametrize("total,status", [(2000.01, "allowed"), (2000, "borderline"), (1999.99, "not_covered")])
def test_combinacao_de_pagamentos_borda_2000(total, status):
    r = rules.payment_combination(total)
    assert r["status"] == status
    assert (r["ambiguity_flags"] == ["I-7"]) is (status == "borderline")


def test_frete_abaixo_de_500_na_regiao_metropolitana():
    r = rules.shipping_fee(420, True)
    assert r["status"] == "flat_fee" and r["shipping_fee_brl"] == "35.00"
    assert r["delivery_days"] == "1 a 3 dias úteis" and "§5.1" in r["source"]


def test_frete_gratis_acima_de_500():
    r = rules.shipping_fee(500.01, True)
    assert r["status"] == "free" and r["shipping_fee_brl"] == "0.00"


def test_frete_igual_a_500_nao_coberto():
    r = rules.shipping_fee(500, True)
    assert r["status"] == "not_covered" and r["shipping_fee_brl"] is None and r["ambiguity_flags"] == ["I-6"]


def test_frete_fora_da_regiao_e_regiao_desconhecida():
    fora = rules.shipping_fee(300, False)
    assert fora["status"] == "calculated_by_carrier" and fora["shipping_fee_brl"] is None
    assert "§5.2" in fora["source"]
    assert rules.shipping_fee(300)["status"] == "region_required"


HOJE = date(2025, 10, 10)


@pytest.mark.parametrize("recebido,status", [
    ("2025-10-05", "within_deadline"),   # 5 dias
    ("2025-10-04", "within_deadline"),   # 6 dias
    ("2025-10-03", "borderline"),        # 7 dias: limite
    ("2025-10-02", "outside_deadline"),  # 8 dias
    ("2025-09-01", "outside_deadline"),
    ("2025-10-12", "not_received_yet"),
])
def test_arrependimento_com_data(recebido, status):
    r = rules.withdrawal_eligibility(recebido, HOJE, "online")
    assert r["status"] == status and "§4.1" in r["source"]


def test_arrependimento_limite_informa_prazo_sem_afirmar_vencido():
    r = rules.withdrawal_eligibility("2025-10-03", HOJE, "online")
    assert r["days_elapsed"] == 7 and r["deadline_date"] == "2025-10-10" and r["status"] != "outside_deadline"


def test_arrependimento_data_estimada_tem_margem():
    assert rules.withdrawal_eligibility("2025-10-02", HOJE, "online", True)["status"] == "borderline"  # 8 dias
    assert rules.withdrawal_eligibility("2025-10-08", HOJE, "online", True)["status"] == "within_deadline"
    r = rules.withdrawal_eligibility("2025-09-29", HOJE, "online", True)  # 11 dias
    assert r["status"] == "outside_deadline" and "estimated_receipt_date" in r["ambiguity_flags"]


def test_arrependimento_canal():
    assert rules.withdrawal_eligibility("2025-10-08", HOJE)["ambiguity_flags"] == ["I-11"]
    assert rules.withdrawal_eligibility("2025-10-08", HOJE, "online")["ambiguity_flags"] == []
    assert "online" in rules.withdrawal_eligibility("2025-10-08", HOJE, "presencial")["channel_note"]


def test_pix_nao_vale_para_preco_promocional():
    r = rules.pix_discount(1000, True)
    assert r["pix_discount_applies"] is False and r["price_brl"] == "1000.00" and "§6.2" in r["source"]
    ok = rules.pix_discount(849.90)
    assert ok["pix_discount_applies"] and ok["pix_price_brl"] == "807.41"


@pytest.mark.parametrize("call", [
    lambda: rules.installment_options(0),
    lambda: rules.installment_options("abc"),
    lambda: rules.installment_options(True),
    lambda: rules.shipping_fee(-5, True),
    lambda: rules.withdrawal_eligibility("ontem", HOJE),
    lambda: rules.withdrawal_eligibility("2025-10-01", HOJE, "loja"),
    lambda: rules.pix_discount(float("nan")),
])
def test_entradas_invalidas(call):
    with pytest.raises(ToolInputError):
        call()
