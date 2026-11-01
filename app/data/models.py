"""Modelos tipados dos registros dos CSVs."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class Category:
    category_id: int
    name: str
    description: str


@dataclass(frozen=True)
class Product:
    product_id: int
    name: str
    category_id: int
    price_brl: Decimal
    description: str
    stock_quantity: int
    status: str
    specs: dict
    created_at: date


@dataclass(frozen=True)
class Customer:
    customer_id: int
    name: str
    phone: str
    email: str
    city: str


@dataclass(frozen=True)
class OrderItem:
    order_id: int
    product_id: int
    quantity: int


@dataclass(frozen=True)
class Order:
    order_id: int
    customer_id: int
    order_date: date
    status: str
    total_brl: Decimal
    payment_method: str
    tracking_code: str | None
    estimated_delivery: date | None
    notes: str | None
    items: tuple[OrderItem, ...] = ()


@dataclass(frozen=True)
class Promotion:
    promotion_id: int
    product_id: int
    discount_percent: Decimal
    description: str
    is_active: bool


@dataclass(frozen=True)
class DataStore:
    categories: dict[int, Category] = field(default_factory=dict)
    products: dict[int, Product] = field(default_factory=dict)
    customers: dict[int, Customer] = field(default_factory=dict)
    orders: dict[int, Order] = field(default_factory=dict)
    promotions: dict[int, Promotion] = field(default_factory=dict)
