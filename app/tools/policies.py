"""Ferramentas finas sobre o manual de políticas (busca e regras numéricas).

O conteúdo devolvido é dado do manual (`source_type: policy_manual`), não instrução.
"""
from __future__ import annotations

from datetime import date

from app.knowledge import rules
from app.knowledge.retriever import SOURCE_TYPE, search_store_policies as _search


def search_store_policies(query: str) -> dict:
    return _search(query)


def _tag(result: dict) -> dict:
    return {"source_type": SOURCE_TYPE, **result}


def check_installments(amount: float) -> dict:
    result = rules.installment_options(amount)
    result["payment_combination"] = rules.payment_combination(amount)
    return _tag(result)


def check_shipping(order_total: float, in_metropolitan_region: bool | None = None) -> dict:
    return _tag(rules.shipping_fee(order_total, in_metropolitan_region))


def check_return_eligibility(received_date: str, channel: str | None = None,
                             date_is_estimate: bool = False, *, today: date | str | None = None) -> dict:
    """`today` é injetável para testes; em uso normal vale a data do sistema."""
    return _tag(rules.withdrawal_eligibility(received_date, today or date.today(), channel, date_is_estimate))


def check_pix_discount(price: float, is_promotional: bool = False) -> dict:
    return _tag(rules.pix_discount(price, is_promotional))
