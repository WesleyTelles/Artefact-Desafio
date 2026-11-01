import pytest

from app.tools.registry import TOOLS, Tool, execute, tool_specs


def test_specs_completas():
    specs = tool_specs()
    assert {s["name"] for s in specs} == set(TOOLS)
    for s in specs:
        assert s["description"] and s["parameters"]["type"] == "object"
    assert "search_customer" not in TOOLS


def test_execute_ok(store):
    r = execute("search_products", {"query": "Takamine GD20"}, store=store)
    assert r["status"] == "found" and r["products"][0]["product_id"] == 95


@pytest.mark.parametrize("name,args", [
    ("search_products", {"price_max": "caro"}),
    ("search_products", {"limit": 0}),
    ("search_products", {"sort": "random"}),
    ("search_products", {"inexistente": 1}),
    ("search_products", {}),
    ("get_order_status", {"order_id": 1}),
    ("get_order_status", {"order_id": "abc", "verification": "x@y.com"}),
    ("get_order_status", {"order_id": 1, "verification": 123}),
    ("check_product_availability", {}),
    ("check_product_availability", {"product_id": "95"}),
    ("get_store_info", {"topic": "cnpj"}),
    ("search_products", "texto"),
])
def test_execute_args_invalidos_retornam_erro(name, args, store):
    r = execute(name, args, store=store)
    assert r["status"] == "error" and r["reason"] == "invalid_arguments"


def test_execute_ferramenta_desconhecida():
    assert execute("drop_table", {})["reason"] == "unknown_tool"
    assert execute("search_customer", {"name": "Ana"})["status"] == "error"


def test_execute_nunca_levanta_em_falha_interna(monkeypatch):
    def boom(**_):
        raise RuntimeError("falha qualquer")
    original = TOOLS["get_store_info"]
    monkeypatch.setitem(TOOLS, "get_store_info",
                        Tool(original.name, original.description, original.parameters, boom))
    r = execute("get_store_info", {})
    assert r["status"] == "error" and r["reason"] == "internal_error"
    assert "falha qualquer" not in r["message"]


def test_execute_erro_de_dados(monkeypatch, tmp_path):
    from app.data.loader import _cached
    monkeypatch.setenv("EMPORIO_DATA_DIR", str(tmp_path))
    _cached.cache_clear()
    try:
        r = execute("search_products", {"query": "violão"})
    finally:
        _cached.cache_clear()
    assert r["status"] == "error" and r["reason"] == "data_error"
