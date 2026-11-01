"""Configuração central. Nenhum segredo aqui: só caminhos e nomes de arquivo."""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR_ENV = "EMPORIO_DATA_DIR"
CSV_PREFIX = "desafio_tecnico_ai_eng - "
TABLES = ("categories", "products", "customers", "orders", "order_items", "promotions")


def get_data_dir() -> Path:
    """Pasta dos CSVs: variável EMPORIO_DATA_DIR ou <raiz>/data."""
    override = os.environ.get(DATA_DIR_ENV)
    return Path(override) if override else PROJECT_ROOT / "data"


def csv_path(table: str, data_dir: Path | None = None) -> Path:
    return (data_dir or get_data_dir()) / f"{CSV_PREFIX}{table}.csv"
