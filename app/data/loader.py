"""Carga dos CSVs em memória com validação de integridade.

Por que stdlib `csv` e não pandas/SQLite: o conjunto é minúsculo (65 produtos,
50 clientes, 20 pedidos), somente leitura e as consultas são filtros simples.
pandas adicionaria uma dependência pesada sem ganho; SQLite exigiria um passo
de importação e um esquema paralelo. Dicionários em memória bastam, são
fáceis de testar e mantêm o Decimal exato para valores monetários.
"""
from __future__ import annotations

import csv
import json
from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from app.core.config import TABLES, csv_path, get_data_dir
from app.core.exceptions import DataError
from app.data import validators as v
from app.data.models import (
    Category, Customer, DataStore, Order, OrderItem, Product, Promotion,
)

PRODUCT_STATUSES = {"active", "discontinued", "coming_soon"}
ORDER_STATUSES = {"pending", "confirmed", "shipped", "delivered", "cancelled"}

_COLUMNS = {
    "categories": ["category_id", "name", "description"],
    "products": ["product_id", "price_brl", "name", "category_id", "description",
                 "stock_quantity", "status", "specs", "created_at"],
    "customers": ["customer_id", "name", "phone", "email", "city"],
    "orders": ["order_id", "customer_id", "order_date", "status", "total_brl",
               "payment_method", "tracking_code", "estimated_delivery", "notes"],
    "order_items": ["order_id", "quantity", "product_id"],
    "promotions": ["promotion_id", "product_id", "discount_percent", "description", "is_active"],
}


def _read(table: str, data_dir: Path) -> list[tuple[int, dict[str, str]]]:
    path = csv_path(table, data_dir)
    try:
        with path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            missing = [c for c in _COLUMNS[table] if c not in (reader.fieldnames or [])]
            if missing:
                raise DataError(f"{path.name}: colunas ausentes {missing}")
            rows = []
            for line, row in enumerate(reader, start=2):
                if None in row or None in row.values():
                    raise DataError(f"{path.name} linha {line}: número de colunas incorreto")
                rows.append((line, row))
            return rows
    except FileNotFoundError:
        raise DataError(f"Arquivo não encontrado: {path}") from None
    except (UnicodeDecodeError, csv.Error) as exc:
        raise DataError(f"{path.name}: arquivo ilegível ({exc})") from None


def _unique(mapping: dict, key: int, table: str, line: int) -> None:
    if key in mapping:
        raise DataError(f"{table}.csv linha {line}: id duplicado {key}")


def _load_categories(rows) -> dict[int, Category]:
    out: dict[int, Category] = {}
    for line, r in rows:
        cid = v.parse_int(r["category_id"], "categories", line, "category_id", 1)
        _unique(out, cid, "categories", line)
        out[cid] = Category(cid, v.require_text(r["name"], "categories", line, "name"),
                            r["description"].strip())
    return out


def _load_products(rows, categories) -> dict[int, Product]:
    out: dict[int, Product] = {}
    for line, r in rows:
        pid = v.parse_int(r["product_id"], "products", line, "product_id", 1)
        _unique(out, pid, "products", line)
        cid = v.parse_int(r["category_id"], "products", line, "category_id")
        if cid not in categories:
            raise DataError(f"products.csv linha {line}: category_id {cid} inexistente")
        try:
            specs = json.loads(r["specs"]) if r["specs"].strip() else {}
        except json.JSONDecodeError:
            raise DataError(f"products.csv linha {line}: specs não é JSON válido") from None
        if not isinstance(specs, dict):
            raise DataError(f"products.csv linha {line}: specs deve ser um objeto JSON")
        out[pid] = Product(
            product_id=pid,
            name=v.require_text(r["name"], "products", line, "name"),
            category_id=cid,
            price_brl=v.parse_decimal(r["price_brl"], "products", line, "price_brl", Decimal("0.01")),
            description=r["description"].strip(),
            stock_quantity=v.parse_int(r["stock_quantity"], "products", line, "stock_quantity", 0),
            status=v.require_choice(r["status"], PRODUCT_STATUSES, "products", line, "status"),
            specs=specs,
            created_at=v.parse_date(r["created_at"], "products", line, "created_at"),
        )
    return out


def _load_customers(rows) -> dict[int, Customer]:
    out: dict[int, Customer] = {}
    for line, r in rows:
        cid = v.parse_int(r["customer_id"], "customers", line, "customer_id", 1)
        _unique(out, cid, "customers", line)
        out[cid] = Customer(cid, v.require_text(r["name"], "customers", line, "name"),
                            r["phone"].strip(), r["email"].strip(), r["city"].strip())
    return out


def _load_items(rows, products) -> dict[int, list[OrderItem]]:
    items: dict[int, list[OrderItem]] = {}
    seen: set[tuple[int, int]] = set()
    for line, r in rows:
        oid = v.parse_int(r["order_id"], "order_items", line, "order_id", 1)
        pid = v.parse_int(r["product_id"], "order_items", line, "product_id", 1)
        qty = v.parse_int(r["quantity"], "order_items", line, "quantity", 1)
        if pid not in products:
            raise DataError(f"order_items.csv linha {line}: product_id {pid} inexistente")
        if (oid, pid) in seen:
            raise DataError(f"order_items.csv linha {line}: item repetido ({oid}, {pid})")
        seen.add((oid, pid))
        items.setdefault(oid, []).append(OrderItem(oid, pid, qty))
    return items


def _load_orders(rows, customers, items) -> dict[int, Order]:
    out: dict[int, Order] = {}
    for line, r in rows:
        oid = v.parse_int(r["order_id"], "orders", line, "order_id", 1)
        _unique(out, oid, "orders", line)
        cid = v.parse_int(r["customer_id"], "orders", line, "customer_id")
        if cid not in customers:
            raise DataError(f"orders.csv linha {line}: customer_id {cid} inexistente")
        est = v.parse_optional(r["estimated_delivery"])
        out[oid] = Order(
            order_id=oid, customer_id=cid,
            order_date=v.parse_date(r["order_date"], "orders", line, "order_date"),
            status=v.require_choice(r["status"], ORDER_STATUSES, "orders", line, "status"),
            total_brl=v.parse_decimal(r["total_brl"], "orders", line, "total_brl", Decimal(0)),
            payment_method=v.require_text(r["payment_method"], "orders", line, "payment_method"),
            tracking_code=v.parse_optional(r["tracking_code"]),
            estimated_delivery=v.parse_date(est, "orders", line, "estimated_delivery") if est else None,
            notes=v.parse_optional(r["notes"]),
            items=tuple(items.get(oid, ())),
        )
    orphans = set(items) - set(out)
    if orphans:
        raise DataError(f"order_items.csv referencia pedidos inexistentes: {sorted(orphans)}")
    return out


def _load_promotions(rows, products) -> dict[int, Promotion]:
    out: dict[int, Promotion] = {}
    for line, r in rows:
        pid = v.parse_int(r["promotion_id"], "promotions", line, "promotion_id", 1)
        _unique(out, pid, "promotions", line)
        prod = v.parse_int(r["product_id"], "promotions", line, "product_id")
        if prod not in products:
            raise DataError(f"promotions.csv linha {line}: product_id {prod} inexistente")
        pct = v.parse_decimal(r["discount_percent"], "promotions", line, "discount_percent", Decimal(0))
        if pct > 100:
            raise DataError(f"promotions.csv linha {line}: desconto acima de 100%")
        flag = v.require_choice(r["is_active"], {"0", "1"}, "promotions", line, "is_active")
        out[pid] = Promotion(pid, prod, pct, r["description"].strip(), flag == "1")
    return out


def load_data(data_dir: Path | str | None = None) -> DataStore:
    """Carrega e valida todas as tabelas; levanta DataError em qualquer falha."""
    base = Path(data_dir) if data_dir else get_data_dir()
    raw = {t: _read(t, base) for t in TABLES}
    categories = _load_categories(raw["categories"])
    products = _load_products(raw["products"], categories)
    customers = _load_customers(raw["customers"])
    items = _load_items(raw["order_items"], products)
    orders = _load_orders(raw["orders"], customers, items)
    promotions = _load_promotions(raw["promotions"], products)
    return DataStore(categories, products, customers, orders, promotions)


@lru_cache(maxsize=4)
def _cached(path: str) -> DataStore:
    return load_data(path)


def get_store() -> DataStore:
    """Store compartilhado (cache por caminho de dados)."""
    return _cached(str(get_data_dir()))
