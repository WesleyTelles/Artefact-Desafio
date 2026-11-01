"""Regras numéricas explícitas do manual, como funções puras e determinísticas.

Só entra aqui o que o manual diz com número (parcelamento §3.1, frete §5.1,
prazo de arrependimento §4.1, desconto de PIX §3/§6.2). Casos que o texto não
cobre (igualdade nos limiares, base de cálculo, canal da compra) voltam
sinalizados em `ambiguity_flags`, sem decisão. Valores monetários em Decimal e
devolvidos como texto 'NNN.NN'.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from app.core.exceptions import ToolInputError
from app.data.normalize import money_str, to_money

MANUAL = "Manual de Políticas v2.1"

# §3.1: (parcelas até, parcela mínima). Em até 3x o manual diz "sem valor mínimo (exceto abaixo de R$ 50,00)".
INSTALLMENT_TIERS = ((6, Decimal("80.00")), (12, Decimal("100.00")))
MAX_INSTALLMENTS = 12
SMALL_INSTALLMENT_LIMIT = Decimal("50.00")
COMBINATION_THRESHOLD = Decimal("2000.00")  # §3.1: "acima de R$ 2.000,00"
FREE_SHIPPING_THRESHOLD = Decimal("500.00")  # §5.1
FLAT_SHIPPING_FEE = Decimal("35.00")
WITHDRAWAL_DAYS = 7  # §4.1: dias corridos após o recebimento
ESTIMATE_MARGIN_DAYS = 2  # tolerância quando a data de recebimento é só uma estimativa
PIX_DISCOUNT_PERCENT = Decimal("5")


def _src(section: str, page: int | str) -> str:
    return f"{MANUAL}, §{section}, p.{page}"


def _money(value: object, name: str) -> Decimal:
    if isinstance(value, bool):
        raise ToolInputError(f"'{name}' deve ser um valor numérico")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ToolInputError(f"'{name}' deve ser um valor numérico") from exc
    if not amount.is_finite() or amount <= 0:
        raise ToolInputError(f"'{name}' deve ser maior que zero")
    return amount


def _min_installment(n: int) -> Decimal | None:
    """Parcela mínima da faixa de n parcelas (None em até 3x, regra à parte)."""
    if n <= 3:
        return None
    return next(minimum for upto, minimum in INSTALLMENT_TIERS if n <= upto)


def installment_options(amount: object) -> dict:
    """Parcelamento permitido no cartão de crédito para um valor (§3.1, sempre sem juros).

    `max_installments` considera só o que o manual permite sem dúvida. Em até 3x com
    parcela abaixo de R$ 50,00 o texto é ambíguo: essas opções ficam em `unclear`.
    """
    total = _money(amount, "amount")
    allowed: list[int] = [1]
    unclear: list[int] = []
    for n in range(2, MAX_INSTALLMENTS + 1):
        minimum = _min_installment(n)
        if minimum is None:
            (allowed if total / n >= SMALL_INSTALLMENT_LIMIT else unclear).append(n)
        elif total >= minimum * n:
            allowed.append(n)
    flags = ["I-4"] if unclear else []
    best = max(allowed)
    return {
        "status": "ambiguous" if unclear else "ok",
        "amount_brl": money_str(total),
        "max_installments": best,
        "installment_value_brl": money_str(total / best),
        "allowed_installments": allowed,
        "unclear_installments": unclear,
        "interest": "sem juros",
        "min_installment_by_tier": {"1x-3x": "sem mínimo (exceto abaixo de R$ 50,00)",
                                    "4x-6x": "80.00", "7x-12x": "100.00"},
        "ambiguity_flags": flags,
        "source": _src("3.1", 3) + " (e tabela do §3)",
    }


def payment_combination(total: object) -> dict:
    """Combinação de formas de pagamento: permitida 'acima de R$ 2.000,00' (§3.1)."""
    value = _money(total, "total")
    if value > COMBINATION_THRESHOLD:
        status, flags = "allowed", []
    elif value == COMBINATION_THRESHOLD:
        status, flags = "borderline", ["I-7"]
    else:
        status, flags = "not_covered", []
    return {"status": status, "total_brl": money_str(value), "threshold_brl": money_str(COMBINATION_THRESHOLD),
            "ambiguity_flags": flags, "source": _src("3.1", 3)}


def shipping_fee(order_total: object, in_metropolitan_region: bool | None = None) -> dict:
    """Frete conforme o §5.1 (região metropolitana de Campo Grande).

    Fora da região o manual só diz que o frete é calculado por CEP, peso e dimensões (§5.2).
    Região desconhecida: o manual não lista os municípios (I-16).
    """
    total = _money(order_total, "order_total")
    base = {"order_total_brl": money_str(total)}
    if in_metropolitan_region is None:
        return {**base, "status": "region_required", "shipping_fee_brl": None, "ambiguity_flags": ["I-16"],
                "source": _src("5.1", 4)}
    if not in_metropolitan_region:
        return {**base, "status": "calculated_by_carrier", "shipping_fee_brl": None, "ambiguity_flags": [],
                "source": _src("5.2", "4-5")}
    source = _src("5.1", 4)
    if total > FREE_SHIPPING_THRESHOLD:
        return {**base, "status": "free", "shipping_fee_brl": "0.00", "delivery_days": "1 a 3 dias úteis",
                "ambiguity_flags": [], "source": source}
    if total < FREE_SHIPPING_THRESHOLD:
        return {**base, "status": "flat_fee", "shipping_fee_brl": money_str(FLAT_SHIPPING_FEE),
                "delivery_days": "1 a 3 dias úteis", "ambiguity_flags": [], "source": source}
    return {**base, "status": "not_covered", "shipping_fee_brl": None, "ambiguity_flags": ["I-6"],
            "source": source}


def _parse_date(value: object, name: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ToolInputError(f"'{name}' deve estar no formato AAAA-MM-DD") from exc


def withdrawal_eligibility(received_on: object, today: object, channel: str | None = None,
                           date_is_estimate: bool = False) -> dict:
    """Prazo do direito de arrependimento (§4.1): 7 dias corridos após o recebimento.

    A data do recebimento é o dia 0. O manual não define a contagem nem a hora do
    recebimento, então o 7º dia (e uma margem, se a data é estimada) volta como
    'borderline', sem afirmar que o prazo venceu.
    """
    received = _parse_date(received_on, "received_date")
    ref = _parse_date(today, "today")
    if channel not in (None, "online", "presencial"):
        raise ToolInputError("'channel' deve ser 'online' ou 'presencial'")
    elapsed = (ref - received).days
    deadline = received + timedelta(days=WITHDRAWAL_DAYS)
    margin = ESTIMATE_MARGIN_DAYS if date_is_estimate else 0
    flags = ["I-11"] if channel != "online" else []
    if date_is_estimate:
        flags.append("estimated_receipt_date")
    if elapsed < 0:
        status = "not_received_yet"
    elif elapsed < WITHDRAWAL_DAYS - margin:
        status = "within_deadline"
    elif elapsed <= WITHDRAWAL_DAYS + margin:
        status = "borderline"
    else:
        status = "outside_deadline"
    result = {
        "status": status,
        "received_on": received.isoformat(),
        "reference_date": ref.isoformat(),
        "days_elapsed": elapsed,
        "deadline_date": deadline.isoformat(),
        "window_days": WITHDRAWAL_DAYS,
        "ambiguity_flags": flags,
        "source": _src("4.1", 4),
    }
    if channel == "presencial":
        result["channel_note"] = "O §4.1 se refere a compras online; o manual não trata compra presencial."
    return result


def pix_discount(price: object, is_promotional: bool = False) -> dict:
    """Desconto de 5% no PIX sobre o preço de tabela; não vale para preço promocional (§3 e §6.2)."""
    value = _money(price, "price")
    if is_promotional:
        return {"status": "not_applicable", "pix_discount_applies": False, "price_brl": money_str(value),
                "reason": "O desconto de PIX não se aplica a preços já promocionais.",
                "ambiguity_flags": [], "source": _src("6.2", 6) + " (e §3, p.3)"}
    final = to_money(value * (Decimal(100) - PIX_DISCOUNT_PERCENT) / Decimal(100))
    return {"status": "applies", "pix_discount_applies": True, "discount_percent": 5,
            "list_price_brl": money_str(value), "pix_price_brl": money_str(final),
            "note": "Em pagamento combinado o manual não define a base do desconto.",
            "ambiguity_flags": [], "source": _src("3", 3)}
