"""Normalização de texto, contatos e valores monetários."""
from __future__ import annotations

import re
import unicodedata
from decimal import ROUND_HALF_UP, Decimal

_CENT = Decimal("0.01")


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def normalize_text(text: str) -> str:
    """Minúsculas, sem acentos, pontuação vira espaço, espaços colapsados."""
    base = strip_accents(text).lower()
    return re.sub(r"[^a-z0-9]+", " ", base).strip()


def tokenize(text: str) -> list[str]:
    norm = normalize_text(text)
    return norm.split() if norm else []


def compact(text: str) -> str:
    return normalize_text(text).replace(" ", "")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_phone(phone: str) -> str:
    """Só dígitos, sem o código do país 55 quando presente."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) > 11 and digits.startswith("55"):
        digits = digits[2:]
    return digits


def to_money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def money_str(value: Decimal) -> str:
    return f"{to_money(value):.2f}"


def format_brl(value: Decimal) -> str:
    inteiro, centavos = money_str(value).split(".")
    inteiro = f"{int(inteiro):,}".replace(",", ".")
    return f"R$ {inteiro},{centavos}"
