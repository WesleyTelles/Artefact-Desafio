"""Registro das ferramentas expostas ao LLM e executor seguro.

`execute` valida os argumentos contra o JSON schema, captura qualquer exceção
e devolve {"status": "error"}: nunca levanta para quem chama.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from app.core.exceptions import DataError, ToolInputError
from app.tools.orders import get_order_status
from app.tools.products import check_product_availability, search_products
from app.tools.promotions import get_promotions
from app.tools.store_info import get_store_info

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    func: Callable[..., dict]

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}


def _schema(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or [],
            "additionalProperties": False}


TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("search_products",
         "Busca produtos do catálogo por texto (nome/marca/modelo), categoria e faixa de preço. "
         "Retorna status found, not_found ou ambiguous. Preço e estoque vêm sempre do sistema.",
         _schema({
             "query": {"type": "string", "description": "Texto livre: nome, marca, modelo ou tipo (ex.: 'violão')."},
             "category": {"type": "string", "description": "Categoria ou sinônimo (violão, guitarra, baixo, bateria, teclado, ukulele...)."},
             "price_max": {"type": "number", "minimum": 0, "description": "Preço máximo em reais."},
             "price_min": {"type": "number", "minimum": 0, "description": "Preço mínimo em reais."},
             "available_only": {"type": "boolean", "description": "Só produtos ativos com estoque."},
             "sort": {"type": "string", "enum": ["price_asc", "price_desc"]},
             "limit": {"type": "integer", "minimum": 1, "maximum": 20},
         }),
         search_products),
    Tool("check_product_availability",
         "Informa se um produto está em estoque, ativo sem estoque, descontinuado, em breve ou não existe. "
         "Informe product_id ou name.",
         _schema({
             "product_id": {"type": "integer", "minimum": 1},
             "name": {"type": "string", "description": "Nome do produto (ex.: 'Takamine GD20')."},
         }),
         check_product_availability),
    Tool("get_promotions",
         "Lista promoções ativas, ou a do produto indicado, com preço original, percentual e preço promocional. "
         "Desconto PIX não se aplica a preço promocional.",
         _schema({"product_id": {"type": "integer", "minimum": 1}}),
         get_promotions),
    Tool("get_order_status",
         "Consulta status de pedido. Exige order_id E verificação (e-mail ou telefone cadastrado no pedido). "
         "Nunca revela se o pedido existe quando a verificação falha.",
         _schema({
             "order_id": {"type": ["integer", "string"], "description": "Número do pedido."},
             "verification": {"type": "string", "description": "E-mail ou telefone do cliente do pedido."},
         }, ["order_id", "verification"]),
         get_order_status),
    Tool("get_store_info",
         "Dados fixos da loja confirmados no manual: endereço, horário, contatos (com divergências "
         "sinalizadas) e escopo (somente instrumentos).",
         _schema({"topic": {"type": "string", "enum": ["address", "hours", "contacts", "scope", "all"]}}),
         get_store_info),
]}


def tool_specs() -> list[dict]:
    """Definições (nome, descrição, JSON schema) para o provedor de LLM."""
    return [t.spec() for t in TOOLS.values()]


_TYPES = {"string": str, "boolean": bool, "object": dict}


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, _TYPES[expected])


def validate_args(schema: dict, args: Any) -> None:
    """Validação mínima de JSON schema (tipo, required, enum, minimum/maximum, props extras)."""
    if not isinstance(args, dict):
        raise ToolInputError("Argumentos devem ser um objeto JSON")
    props = schema["properties"]
    extra = set(args) - set(props)
    if extra:
        raise ToolInputError(f"Argumentos desconhecidos: {sorted(extra)}")
    for name in schema.get("required", []):
        if args.get(name) is None:
            raise ToolInputError(f"Argumento obrigatório ausente: {name}")
    for name, value in args.items():
        if value is None:
            continue
        rule = props[name]
        types = rule["type"] if isinstance(rule["type"], list) else [rule["type"]]
        if not any(_type_ok(value, t) for t in types):
            raise ToolInputError(f"Argumento '{name}' com tipo inválido (esperado {'/'.join(types)})")
        if "enum" in rule and value not in rule["enum"]:
            raise ToolInputError(f"Argumento '{name}' deve ser um de {rule['enum']}")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in rule and value < rule["minimum"]:
                raise ToolInputError(f"Argumento '{name}' abaixo do mínimo {rule['minimum']}")
            if "maximum" in rule and value > rule["maximum"]:
                raise ToolInputError(f"Argumento '{name}' acima do máximo {rule['maximum']}")


def execute(name: str, args: dict | None = None, **kwargs: Any) -> dict:
    """Executa uma ferramenta. Nunca levanta; falhas viram {'status': 'error'}.

    kwargs (ex.: store=...) são repassados à função, útil em testes.
    """
    tool = TOOLS.get(name) if isinstance(name, str) else None
    if tool is None:
        return {"status": "error", "reason": "unknown_tool", "message": f"Ferramenta desconhecida: {name}"}
    try:
        validate_args(tool.parameters, {} if args is None else args)
        return tool.func(**(args or {}), **kwargs)
    except ToolInputError as exc:
        return {"status": "error", "reason": "invalid_arguments", "message": str(exc)}
    except DataError as exc:
        log.error("Falha de dados na ferramenta %s: %s", name, exc)
        return {"status": "error", "reason": "data_error",
                "message": "Falha técnica ao consultar os dados da loja."}
    except Exception:  # noqa: BLE001 - contrato: execute nunca levanta
        log.exception("Erro inesperado na ferramenta %s", name)
        return {"status": "error", "reason": "internal_error",
                "message": "Falha técnica ao executar a consulta."}
