from decimal import Decimal

from app.tools.products import check_product_availability, search_products

VIOLOES_ATE_1000 = {83, 85, 89, 88, 81, 84, 87, 86, 107, 82, 91, 112}


def test_takamine_gd20_exato(store):
    r = search_products(query="Takamine GD20", store=store)
    assert r["status"] == "found"
    (p,) = r["products"]
    assert p["product_id"] == 95
    assert p["price_brl"] == "2199.00" and p["stock_quantity"] == 5
    assert p["available"] and p["promotion"] is None


def test_busca_ignora_acento_e_caixa(store):
    r = search_products(query="TAKAMINE gd-20", store=store)
    assert [p["product_id"] for p in r["products"]] == [95]


def test_violoes_ate_1000_disponiveis(store):
    r = search_products(query="violões", price_max=1000, available_only=True,
                        sort="price_asc", store=store)
    ids = [p["product_id"] for p in r["products"]]
    assert set(ids) == VIOLOES_ATE_1000 and len(ids) == 12
    assert 96 not in ids and 113 not in ids
    prices = [Decimal(p["price_brl"]) for p in r["products"]]
    assert prices == sorted(prices) and max(prices) <= 1000


def test_violoes_ate_1000_sem_filtro_de_estoque_traz_14(store):
    r = search_products(category="violão", price_max=1000, store=store)
    ids = {p["product_id"] for p in r["products"]}
    assert ids == VIOLOES_ATE_1000 | {96, 113}


def test_categoria_nao_inclui_ukulele_com_violao_na_descricao(store):
    r = search_products(query="violão", store=store)
    assert 128 not in {p["product_id"] for p in r["products"]}


def test_yamaha_sozinho_e_ambiguo(store):
    r = search_products(query="Yamaha", store=store)
    assert r["status"] == "ambiguous"
    assert r["total_matches"] == 10
    assert all("Yamaha" in c["name"] for c in r["candidates"])


def test_cordas_nao_vira_violao_de_7_cordas(store):
    r = search_products(query="cordas", store=store)
    assert r["status"] == "not_found" and r["reason"] == "out_of_scope_accessory"
    assert search_products(query="palhetas para violão", store=store)["status"] == "not_found"


def test_sete_cordas_e_produto(store):
    r = search_products(query="violão 7 cordas", store=store)
    ids = {p["product_id"] for p in r.get("products", r.get("candidates", []))}
    assert ids == {109, 110, 111, 112, 113}


def test_categoria_sem_produtos(store):
    r = search_products(query="saxofone", store=store)
    assert r["status"] == "not_found" and r["reason"] == "category_without_products"


def test_sinonimos_de_categoria(store):
    for termo, esperado in [("guitarra", "Guitarras"), ("baixo", "Baixos"), ("bateria", "Baterias e Percussão"),
                            ("piano", "Teclados e Pianos"), ("ukulele", "Ukuleles")]:
        r = search_products(query=termo, store=store)
        assert r["status"] == "found"
        assert {p["category"] for p in r["products"]} == {esperado}


def test_produto_inexistente(store):
    r = search_products(query="Gibson SG Mega Deluxe", store=store)
    assert r["status"] == "not_found"
    assert check_product_availability(product_id=9999, store=store)["status"] == "not_found"


def test_faixa_de_preco_min_max(store):
    r = search_products(category="guitarras", price_min=6000, price_max=8000, store=store)
    assert {p["product_id"] for p in r["products"]} == {132, 133}


def test_disponibilidade_ativo_sem_estoque(store):
    p = check_product_availability(product_id=96, store=store)["product"]
    assert p["availability"] == "out_of_stock" and not p["available"] and p["product_status"] == "active"


def test_disponibilidade_coming_soon(store):
    p = check_product_availability(product_id=130, store=store)["product"]
    assert p["availability"] == "coming_soon" and not p["available"]


def test_disponibilidade_descontinuados(store):
    for pid in (113, 136):
        p = check_product_availability(product_id=pid, store=store)["product"]
        assert p["availability"] == "discontinued" and not p["available"]
    # 136 tem estoque 13, mas descontinuado não é disponível
    assert check_product_availability(product_id=136, store=store)["product"]["stock_quantity"] == 13


def test_disponibilidade_em_estoque_por_nome(store):
    p = check_product_availability(name="Takamine GD20", store=store)["product"]
    assert p["availability"] == "in_stock" and p["product_id"] == 95


def test_disponibilidade_por_nome_ambiguo(store):
    assert check_product_availability(name="Yamaha", store=store)["status"] == "ambiguous"
