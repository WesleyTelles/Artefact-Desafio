"""Conversão e validação de campos dos CSVs. Falhas viram DataError."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from app.core.exceptions import DataError


def _where(table: str, line: int, column: str) -> str:
    return f"{table}.csv linha {line}, coluna '{column}'"


def parse_int(raw: str, table: str, line: int, column: str, minimum: int | None = None) -> int:
    try:
        value = int(raw.strip())
    except (ValueError, AttributeError):
        raise DataError(f"Inteiro inválido ({raw!r}) em {_where(table, line, column)}") from None
    if minimum is not None and value < minimum:
        raise DataError(f"Valor {value} menor que {minimum} em {_where(table, line, column)}")
    return value


def parse_decimal(raw: str, table: str, line: int, column: str, minimum: Decimal | None = None) -> Decimal:
    try:
        value = Decimal(raw.strip())
    except (InvalidOperation, AttributeError):
        raise DataError(f"Decimal inválido ({raw!r}) em {_where(table, line, column)}") from None
    if not value.is_finite() or (minimum is not None and value < minimum):
        raise DataError(f"Valor {raw!r} fora do permitido em {_where(table, line, column)}")
    return value


def parse_date(raw: str, table: str, line: int, column: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except (ValueError, AttributeError):
        raise DataError(f"Data inválida ({raw!r}) em {_where(table, line, column)}") from None


def parse_optional(raw: str | None) -> str | None:
    value = (raw or "").strip()
    return value or None


def require_choice(raw: str, allowed: set[str], table: str, line: int, column: str) -> str:
    value = (raw or "").strip()
    if value not in allowed:
        raise DataError(f"Valor {value!r} desconhecido em {_where(table, line, column)}")
    return value


def require_text(raw: str | None, table: str, line: int, column: str) -> str:
    value = (raw or "").strip()
    if not value:
        raise DataError(f"Campo vazio em {_where(table, line, column)}")
    return value
