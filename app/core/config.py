"""Configuração central. Nenhum segredo aqui: só caminhos e nomes de arquivo."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
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


# --- LLM e conversa -------------------------------------------------------
# Segredos (LLM_API_KEY) só via ambiente/.env; nunca têm valor padrão.
PROVIDER_DEFAULTS: dict[str, dict[str, str]] = {
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
               "model": "gemini-3.8-flash"},
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-120b"},
    "ollama": {"base_url": "http://localhost:11434/v1", "model": "qwen3.8"},
}
MAX_TOOL_ITERATIONS = 6
MEMORY_WINDOW = 20          # mensagens (usuário + resposta) mantidas por sessão
MAX_INPUT_CHARS = 1000
LLM_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class LLMSettings:
    provider: str
    model: str
    base_url: str
    api_key: str = field(default="", repr=False)  # nunca aparece em repr/logs


def load_env_file() -> None:
    """Carrega .env da raiz se python-dotenv estiver instalado (variáveis já definidas prevalecem)."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def load_llm_settings(provider: str | None = None) -> LLMSettings:
    """Lê LLM_PROVIDER, LLM_MODEL, LLM_BASE_URL e LLM_API_KEY do ambiente."""
    provider = (provider or os.environ.get("LLM_PROVIDER") or "gemini").strip().lower()
    defaults = PROVIDER_DEFAULTS.get(provider, {})
    return LLMSettings(
        provider=provider,
        model=os.environ.get("LLM_MODEL") or defaults.get("model", ""),
        base_url=os.environ.get("LLM_BASE_URL") or defaults.get("base_url", ""),
        api_key=os.environ.get("LLM_API_KEY", ""),
    )
