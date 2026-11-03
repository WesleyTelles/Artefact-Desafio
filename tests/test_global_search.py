"""Busca global (todas as categorias), busca por categoria e escopo declarado no resultado.

Regressão: "qual o instrumento mais barato da loja?" foi respondido com uma busca só de violões,
apresentada como se fosse da loja inteira. Os valores esperados vêm dos dados reais (products.csv).
"""
import dataclasses
from decimal import Decimal

import pytest

from app.agent.orchestrator import Agent
from app.agent.prompts import build_system_prompt
from app.core.exceptions import ToolInputError
from app.data.models import DataStore
from app.llm.mock import MockLLM
from app.tools.products import is_available, search_products
from app.tools.registry import TOOLS, execute
from tests.fakes import FakeLLM, text_step, tool_step


def _catalogo(store, available_only=False):
    return [p for p in store.products.values() if not available_only or is_available(p)]


def _ordenado(store, available_only=False):
    return sorted(_catalogo(store, available_only), key=lambda p: (p.price_brl, p.product_id))


# --- ordenação global -----------------------------------------------------------------------------
def test_ordenacao_global_crescente_e_deterministica(store):
    r = search_products(all_categories=True, sort="price_asc", store=store)
    assert r["status"] == "found" and r["scope"]["categories"] == "all"
    ids = [p["product_id"] for p in r["products"]]
    esperado = [p.product_id for p in _ordenado(store)][:len(ids)]
    assert ids == esperado and r["total_matches"] == len(store.products)
    assert search_products(all_categories=True, sort="price_asc", store=store) == r


def test_produto_mais_barato_da_loja_vem_dos_dados_nao_do_codigo(store):
    r = search_products(all_categories=True, sort="price_asc", limit=1, store=store)
    (p,) = r["products"]
    menor = _ordenado(store)[0]
    assert (p["product_id"], p["price_brl"]) == (menor.product_id, f"{menor.price_brl:.2f}")
    assert r["truncated"] is True and r["scope"]["sort"] == "price_asc"


def test_regressao_shelby_su21s_e_o_mais_barato_do_catalogo_atual(store):
    r = search_products(all_categories=True, sort="price_asc", limit=1, available_only=True, store=store)
    (p,) = r["products"]
    assert p["name"] == "Shelby SU-21S Soprano Sunburst" and p["price_brl"] == "159.90"
    assert p["category"] != "Violões"


def test_cinco_mais_baratos_de_categorias_diferentes(store):
    r = search_products(all_categories=True, sort="price_asc", limit=5, store=store)
    precos = [Decimal(p["price_brl"]) for p in r["products"]]
    assert len(precos) == 5 and precos == sorted(precos)
    assert [p["product_id"] for p in r["products"]] == [p.product_id for p in _ordenado(store)][:5]
    # a ordenação global não se limita a uma categoria: o 6º colocado do catálogo é de outra categoria
    top = [p["category"] for p in search_products(all_categories=True, sort="price_asc", limit=20,
                                                  store=store)["products"]]
    assert len(set(top)) > 1


def test_mais_caro_global(store):
    r = search_products(all_categories=True, sort="price_desc", limit=1, store=store)
    assert r["products"][0]["product_id"] == max(_catalogo(store), key=lambda p: (p.price_brl, -p.product_id)).product_id


# --- categoria específica nunca é apresentada como global -----------------------------------------
def test_busca_por_violao_declara_o_escopo_violoes(store):
    r = search_products(category="violão", sort="price_asc", limit=1, store=store)
    assert r["scope"]["categories"] == ["Violões"]
    assert r["products"][0]["category"] == "Violões"
    assert r["products"][0]["product_id"] != search_products(
        all_categories=True, sort="price_asc", limit=1, store=store)["products"][0]["product_id"]


def test_busca_por_outra_categoria_so_traz_essa_categoria(store):
    r = search_products(category="ukulele", sort="price_asc", store=store)
    assert r["scope"]["categories"] == ["Ukuleles"]
    assert {p["category"] for p in r["products"]} == {"Ukuleles"}


def test_busca_por_categoria_com_varias_categorias_ambigua_orienta_a_busca_global(store):
    r = search_products(query="instrumento de sopro e corda", store=store)
    if r["status"] == "ambiguous" and r.get("reason") == "multiple_categories":
        assert "all_categories" in r["hint"]


# --- faixa de preço -------------------------------------------------------------------------------
def test_faixa_de_preco_cobre_todas_as_categorias(store):
    r = search_products(price_max=300, sort="price_asc", store=store)
    esperado = {p.product_id for p in store.products.values() if p.price_brl <= 300}
    assert {p["product_id"] for p in r["products"]} == esperado
    assert r["scope"]["categories"] == "all" and r["scope"]["price_max"] == "300.00"
    assert len({p["category"] for p in r["products"]}) >= 1


# --- critério obrigatório e flag explícita --------------------------------------------------------
def test_sem_criterio_continua_recusado_e_a_mensagem_aponta_o_caminho(store):
    with pytest.raises(ToolInputError, match="all_categories"):
        search_products(sort="price_asc", store=store)
    resposta = execute("search_products", {"sort": "price_asc"})
    assert resposta["status"] == "error" and resposta["reason"] == "invalid_arguments"
    assert "all_categories" in resposta["message"]


def test_busca_global_exige_ordenacao_quando_nao_ha_outro_criterio(store):
    with pytest.raises(ToolInputError):
        search_products(all_categories=True, store=store)


def test_all_categories_nao_combina_com_category(store):
    with pytest.raises(ToolInputError, match="excludentes"):
        search_products(all_categories=True, category="violão", sort="price_asc", store=store)


@pytest.mark.parametrize("valor", ["true", 1, 0])
def test_all_categories_so_aceita_booleano(store, valor):
    with pytest.raises(ToolInputError):
        search_products(all_categories=valor, sort="price_asc", store=store)


def test_schema_expoe_all_categories_ao_modelo():
    props = TOOLS["search_products"].parameters["properties"]
    assert props["all_categories"]["type"] == "boolean"
    assert "scope" in TOOLS["search_products"].description


# --- compatibilidade ------------------------------------------------------------------------------
def test_comportamento_anterior_preservado(store):
    r = search_products(query="Takamine GD20", store=store)
    assert r["products"][0]["product_id"] == 95 and r["scope"]["categories"] == "all"
    r = search_products(category="violão", price_max=1000, available_only=True, sort="price_asc", store=store)
    assert len(r["products"]) == 12 and r["scope"]["categories"] == ["Violões"]
    assert search_products(category="violão", store=store)["status"] == "found"


# --- empate e catálogo vazio ----------------------------------------------------------------------
def _loja(store, produtos):
    return DataStore(categories=store.categories, products={p.product_id: p for p in produtos},
                     customers=store.customers, orders=store.orders, promotions={})


def test_empate_de_preco_desempata_por_product_id(store):
    base = store.products[119]
    a = dataclasses.replace(base, product_id=9002, name="Empate B", price_brl=Decimal("10.00"))
    b = dataclasses.replace(base, product_id=9001, name="Empate A", price_brl=Decimal("10.00"))
    c = dataclasses.replace(base, product_id=9003, name="Caro", price_brl=Decimal("20.00"))
    loja = _loja(store, [c, a, b])
    r = search_products(all_categories=True, sort="price_asc", store=loja)
    assert [p["product_id"] for p in r["products"]] == [9001, 9002, 9003]
    r = search_products(all_categories=True, sort="price_asc", limit=1, store=loja)
    assert r["products"][0]["product_id"] == 9001 and r["truncated"] is True


def test_catalogo_vazio_nao_inventa_produto(store):
    r = search_products(all_categories=True, sort="price_asc", limit=1, store=_loja(store, []))
    assert r["status"] == "not_found" and "products" not in r


# --- agente: escopo, ambiguidade e falha ----------------------------------------------------------
def _mock_agent():
    return Agent(MockLLM())


def test_agente_cenario_a_mais_barato_da_loja():
    texto = _mock_agent().reply("Qual é o instrumento mais barato da loja?").text
    assert "Shelby SU-21S" in texto and "159,90" in texto and "todas as categorias" in texto
    assert "Tagima" not in texto


def test_agente_cenario_b_cinco_mais_baratos():
    texto = _mock_agent().reply("Quais são os cinco instrumentos mais baratos?").text
    for nome in ("Shelby SU-21S", "Kalani KAL-300S", "Kala KA-15S", "Ohana SK-10", "Kala KA-C"):
        assert nome in texto
    assert texto.index("Shelby SU-21S") < texto.index("Kala KA-C")


def test_agente_cenario_c_violao_mais_barato_nao_vira_global():
    texto = _mock_agent().reply("Qual é o violão mais barato?").text
    assert "Tagima Memphis AC-39" in texto and "429,90" in texto
    assert "da loja" not in texto and "Violões" in texto


def test_agente_cenario_d_ambiguo_sem_contexto_pergunta():
    texto = _mock_agent().reply("Qual é o mais barato?").text
    assert "?" in texto and "R$" not in texto and "loja inteira" in texto


def test_agente_cenario_d_com_contexto_usa_a_listagem_anterior_e_diz_isso():
    agent = _mock_agent()
    agent.reply("quero ver violões")
    texto = agent.reply("Qual é o mais barato?").text
    assert texto.startswith("Entre os que mostrei") and "Tagima" in texto


def test_pergunta_global_apos_listagem_nao_reaproveita_o_contexto():
    agent = _mock_agent()
    agent.reply("quero ver violões")
    texto = agent.reply("Qual o instrumento mais barato da loja?").text
    assert "Shelby SU-21S" in texto and "Tagima" not in texto


def test_agente_cenario_e_faixa_de_preco_em_todas_as_categorias():
    texto = _mock_agent().reply("Quais instrumentos custam até R$ 300?").text
    for nome in ("Shelby SU-21S", "Kalani KAL-300S", "Kala KA-15S", "Ohana SK-10"):
        assert nome in texto
    assert "todas as categorias" in texto


def test_agente_cenario_f_falha_na_consulta_global_nao_vira_conclusao():
    def falha(name, args):
        return {"status": "error", "reason": "internal_error", "message": "falha simulada"}

    llm = FakeLLM([tool_step("search_products", {"all_categories": True, "sort": "price_asc", "limit": 1}),
                   text_step("O mais barato da loja é o Shelby SU-21S por R$ 159,90")])
    reply = Agent(llm, executor=falha).reply("qual o instrumento mais barato da loja?")
    assert reply.failed and "159" not in reply.text


def test_resultado_parcial_declara_truncado_para_o_modelo(store):
    r = search_products(all_categories=True, sort="price_asc", limit=5, store=store)
    assert r["truncated"] is True and r["total_matches"] > 5 and r["scope"]["categories"] == "all"


def test_prompt_traz_as_regras_de_escopo():
    prompt = build_system_prompt()
    for trecho in ("scope.categories", "all_categories=true", "Nunca escolha uma categoria"):
        assert trecho in prompt
