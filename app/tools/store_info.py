"""Dados fixos da loja, somente os confirmados no manual de políticas v2.1.

Cada campo traz a fonte (seção e página do manual). Nada aqui vem dos CSVs.
"""
from __future__ import annotations

from app.core.exceptions import ToolInputError

MANUAL = "Manual de Políticas v2.1 (jun/2025)"

_INFO: dict[str, dict] = {
    "address": {
        "value": "Rua 14 de Maio, 3200 - Centro, Campo Grande - MS, CEP 79202-333",
        "source": f"{MANUAL}, §1.2, p.2 (também capa, p.1)",
    },
    "hours": {
        "value": {"seg_a_sex": "09:00 às 18:00", "sabado": "09:00 às 13:00",
                  "domingo_e_feriados": "Fechado"},
        "note": "Em datas especiais (Black Friday, Aniversário da Loja, Natal) o horário pode ser "
                "estendido; os horários não estão definidos no manual. O WhatsApp segue o mesmo "
                "horário.",
        "source": f"{MANUAL}, §2, p.2",
    },
    "contacts": {
        "phone": {
            "value": "(67) 3341-4444",
            "source": f"{MANUAL}, capa p.1 e §1.2 p.2 ('Telefone / WhatsApp')",
            "to_confirm": True,
        },
        "whatsapp": {
            "value": "(67) 3321-4500",
            "source": f"{MANUAL}, §7, p.6 ('canal principal')",
            "to_confirm": True,
        },
        "email": {
            "value": "contato@emporiodamusica.com.br",
            "source": f"{MANUAL}, capa p.1 (o §1.2 grafa o domínio com acento)",
        },
        "divergence_note": "O manual diverge: §1.2 indica (67) 3341-4444 como telefone/WhatsApp e §7 "
                           "indica (67) 3321-4500 como WhatsApp. Dado a confirmar com a loja.",
    },
    "scope": {
        "value": "Somente instrumentos musicais. Não vende acessórios (cordas, palhetas, cabos, "
                 "cases, pedais, amplificadores).",
        "source": f"{MANUAL}, §1, p.2 e §7.1, p.6",
    },
}


def get_store_info(topic: str | None = None) -> dict:
    """topic: address | hours | contacts | scope; sem topic devolve tudo."""
    if topic in (None, "", "all"):
        return {"status": "found", "info": _INFO}
    if topic not in _INFO:
        raise ToolInputError(f"topic inválido; use um de {sorted(_INFO)}")
    return {"status": "found", "info": {topic: _INFO[topic]}}
