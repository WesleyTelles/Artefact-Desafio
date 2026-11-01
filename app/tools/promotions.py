"""Promoções: preço promocional calculado em Decimal a partir do CSV."""
from __future__ import annotations

from decimal import Decimal

from app.core.exceptions import ToolInputError
from app.data.loader import get_store
from app.data.models import DataStore, Product, Promotion
from app.data.normalize import format_brl, money_str, to_money


def active_promotion_for(store: DataStore, product: Product) -> Promotion | None:
    """Promoção vigente: is_active=1 e produto 'active'. Sem acúmulo: vale a maior."""
    if product.status != "active":
        return None
    candidates = [p for p in store.promotions.values()
                  if p.product_id == product.product_id and p.is_active]
    return max(candidates, key=lambda p: p.discount_percent, default=None)


def promotion_info(product: Product, promo: Promotion) -> dict:
    final = to_money(product.price_brl * (Decimal(100) - promo.discount_percent) / Decimal(100))
    return {
        "promotion_id": promo.promotion_id,
        "description": promo.description,
        "discount_percent": format(promo.discount_percent.normalize(), "f"),
        "original_price_brl": money_str(product.price_brl),
        "promotional_price_brl": money_str(final),
        "original_price_display": format_brl(product.price_brl),
        "promotional_price_display": format_brl(final),
        "pix_discount_applies": False,  # manual 6.2: PIX 5% não vale sobre preço promocional
    }


def _entry(product: Product, promo: Promotion) -> dict:
    return {"product_id": product.product_id, "name": product.name,
            "stock_quantity": product.stock_quantity, **promotion_info(product, promo)}


def get_promotions(product_id: int | None = None, *, store: DataStore | None = None) -> dict:
    """Sem product_id: lista promoções ativas. Com product_id: a do produto."""
    store = store or get_store()
    if product_id is None:
        entries = []
        for product in store.products.values():
            promo = active_promotion_for(store, product)
            if promo:
                entries.append(_entry(product, promo))
        entries.sort(key=lambda e: e["product_id"])
        if not entries:
            return {"status": "not_found", "promotions": []}
        return {"status": "found", "count": len(entries), "promotions": entries}
    if isinstance(product_id, bool) or not isinstance(product_id, int):
        raise ToolInputError("product_id deve ser inteiro")
    product = store.products.get(product_id)
    if product is None:
        return {"status": "not_found", "reason": "product_not_found", "product_id": product_id}
    promo = active_promotion_for(store, product)
    if promo is None:
        return {"status": "not_found", "reason": "no_active_promotion", "product_id": product_id,
                "name": product.name, "price_brl": money_str(product.price_brl)}
    return {"status": "found", "promotions": [_entry(product, promo)]}
