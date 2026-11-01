from app.tools.products import check_product_availability
from app.tools.promotions import get_promotions


def test_promocoes_ativas(store):
    r = get_promotions(store=store)
    assert [p["product_id"] for p in r["promotions"]] == [90, 94, 121, 127]


def test_calculo_do_preco_promocional(store):
    by_id = {p["product_id"]: p for p in get_promotions(store=store)["promotions"]}
    assert by_id[90]["original_price_brl"] == "2399.00" and by_id[90]["promotional_price_brl"] == "1967.18"
    assert by_id[90]["discount_percent"] == "18"
    assert by_id[127]["promotional_price_brl"] == "323.10"
    assert by_id[94]["promotional_price_brl"] == "5519.08"
    assert all(p["pix_discount_applies"] is False for p in by_id.values())


def test_promocao_inativa_nao_e_oferecida(store):
    r = get_promotions(product_id=96, store=store)  # só tem promoções inativas
    assert r["status"] == "not_found" and r["reason"] == "no_active_promotion"
    assert get_promotions(product_id=113, store=store)["status"] == "not_found"


def test_promocao_aparece_na_busca(store):
    p = check_product_availability(product_id=121, store=store)["product"]
    assert p["promotion"]["discount_percent"] == "20"
    assert p["promotion"]["promotional_price_brl"] == "439.20"


def test_promocao_produto_inexistente(store):
    assert get_promotions(product_id=9999, store=store)["reason"] == "product_not_found"
