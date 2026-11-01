"""Consulta de pedidos com verificação de identidade e PII mascarada."""
from __future__ import annotations

import re

from app.core.exceptions import ToolInputError
from app.data.loader import get_store
from app.data.models import Customer, DataStore, Order
from app.data.normalize import format_brl, money_str, normalize_email, normalize_phone

STATUS_LABELS = {
    "pending": "Pendente",
    "confirmed": "Confirmado",
    "shipped": "Enviado",
    "delivered": "Entregue",
    "cancelled": "Cancelado",
}
_FIXED_PAYMENT = {"pix": "PIX", "boleto": "Boleto", "debit": "Cartão de débito"}
_CREDIT = re.compile(r"^credit_(\d+)x$")


def payment_label(method: str) -> str:
    if method in _FIXED_PAYMENT:
        return _FIXED_PAYMENT[method]
    m = _CREDIT.match(method)
    return f"Cartão de crédito {m.group(1)}x" if m else method


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def mask_phone(phone: str) -> str:
    digits = normalize_phone(phone)
    if len(digits) < 6:
        return "***"
    return f"({digits[:2]}) *****-{digits[-4:]}" if len(digits) >= 10 else f"****{digits[-4:]}"


def _customer_matches(customer: Customer, verification: str) -> bool:
    """Compara e-mail (se contém '@') ou telefone (>=10 dígitos) de forma normalizada."""
    if "@" in verification:
        return normalize_email(verification) == normalize_email(customer.email)
    digits = normalize_phone(verification)
    return len(digits) >= 10 and digits == normalize_phone(customer.phone)


def _parse_order_id(order_id) -> int:
    if isinstance(order_id, bool):
        raise ToolInputError("order_id inválido")
    if isinstance(order_id, int):
        return order_id
    if isinstance(order_id, str) and re.fullmatch(r"\s*#?\d{1,9}\s*", order_id):
        return int(order_id.strip().lstrip("#"))
    raise ToolInputError("order_id deve ser um número inteiro")


def _failed() -> dict:
    # Mesma resposta para pedido inexistente e verificação errada: não revela existência.
    return {"status": "verification_failed",
            "message": "Não foi possível confirmar os dados informados para este pedido."}


def _order_payload(store: DataStore, order: Order, customer: Customer) -> dict:
    items = [{"product_id": it.product_id, "name": store.products[it.product_id].name,
              "quantity": it.quantity} for it in order.items]
    payload = {
        "status": "found",
        "order_id": order.order_id,
        "order_date": order.order_date.isoformat(),
        "order_status": order.status,
        "order_status_label": STATUS_LABELS.get(order.status, order.status),
        "payment_method": order.payment_method,
        "payment_method_label": payment_label(order.payment_method),
        "total_brl": money_str(order.total_brl),
        "total_display": format_brl(order.total_brl),
        "items": items,
        "contact_on_file": {"email": mask_email(customer.email), "phone": mask_phone(customer.phone)},
    }
    if order.tracking_code:
        payload["tracking_code"] = order.tracking_code
    if order.estimated_delivery:
        payload["estimated_delivery"] = order.estimated_delivery.isoformat()
    if order.notes:
        payload["notes"] = order.notes
    return payload


def get_order_status(order_id, verification: str | None = None,
                     *, store: DataStore | None = None) -> dict:
    """Status do pedido, só com order_id + e-mail/telefone do cliente do pedido."""
    store = store or get_store()
    oid = _parse_order_id(order_id)
    ver = verification.strip() if isinstance(verification, str) else ""
    if not ver:
        return {"status": "verification_required",
                "message": "Informe o e-mail ou o telefone cadastrado no pedido."}
    order = store.orders.get(oid)
    customer = store.customers.get(order.customer_id) if order else None
    if order is None or customer is None or not _customer_matches(customer, ver):
        return _failed()
    return _order_payload(store, order, customer)
