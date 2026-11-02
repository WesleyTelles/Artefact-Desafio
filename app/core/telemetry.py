"""Log estruturado (JSONL) por turno, para diagnóstico operacional.

Desligado por padrão; ligue com EMPORIO_LOG_FILE=logs/agent.jsonl. Cada linha traz só metadados:
session_id, turn_id, ferramentas (nome, status, duração), tentativas e latência do LLM, tokens
(null se o provedor não informou), categoria de erro e, quando derivável sem LLM, a intenção.
NUNCA grava texto do cliente, e-mail, telefone nem argumentos de ferramentas. Falha ao gravar
nunca derruba o atendimento.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import LOG_FILE_ENV

log = logging.getLogger(__name__)

# Intenção derivada só da primeira ferramenta acionada (sem LLM); sem ferramenta, omitida.
_INTENT_BY_TOOL = {
    "search_products": "product_search", "check_product_availability": "product_availability",
    "get_promotions": "promotions", "get_order_status": "order_status",
    "search_store_policies": "policy", "check_installments": "payment", "check_pix_discount": "payment",
    "check_shipping": "shipping", "check_return_eligibility": "returns", "get_store_info": "store_info",
}


def derive_intent(tool_names: list[str]) -> str | None:
    return next((_INTENT_BY_TOOL[n] for n in tool_names if n in _INTENT_BY_TOOL), None)


class Telemetry:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else None

    @classmethod
    def from_env(cls) -> "Telemetry":
        return cls(os.environ.get(LOG_FILE_ENV) or None)

    @property
    def enabled(self) -> bool:
        return self.path is not None

    def emit(self, record: dict[str, Any]) -> None:
        if self.path is None:
            return
        record = {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"), **record}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except OSError as exc:
            log.warning("Não foi possível gravar o log de telemetria (%s)", type(exc).__name__)
