"""Qualidade dos dados: auditor determinístico e o que as ferramentas entregam ao agente."""
import hashlib
import json
from dataclasses import replace

import pytest

from app.core.config import PROJECT_ROOT
from app.data.quality import audit_store, count_by, product_attributes, product_conflicts
from app.tools.products import check_product_availability, search_products
from app.tools.registry import execute

ORIGINAL_SHA256 = {
    "desafio_tecnico_ai_eng - categories.csv": "7a7901e16c8c6357a956031ada45a6fd6a4cc9bd7bc1edc05448cc55b01b0a9e",
    "desafio_tecnico_ai_eng - customers.csv": "1cd724dc86eac6258913cc890abf23d3893c57a99c9325ebfb91dfad3c7b0f37",
    "desafio_tecnico_ai_eng - order_items.csv": "7656eb681821d48e0c932f61d3188309b955c25446578235f2d8e69604b0f0bc",
    "desafio_tecnico_ai_eng - orders.csv": "deb9c2480605d8d22117d569f0045fd156c5e9a58ffeebb847ff61b3b9512fd5",
    "desafio_tecnico_ai_eng - products.csv": "78d911d96ee891abb163b6c858e895025aa530ab27d0290540f05d5098377c12",
    "desafio_tecnico_ai_eng - promotions.csv": "cbe08c7e91b00437c0c00a7ef1486deba73de52d23e3f97f51a7dbd557d759e0",
}
# conflitos esperados (relevantes ao cliente) na base fornecida
CONFLICT_IDS = {135, 136, 137, 139, 140, 142, 144}
MAX_SINGLE_PRODUCT_CHARS = 3500
MAX_CANDIDATES_CHARS = 14000


def _conflicts(result: dict) -> dict:
    return {c["field"]: c for c in result["product"]["data_conflicts"]}


def _attrs(result: dict) -> dict:
    return result["product"]["details"]["attributes"]


# --- auditor -----------------------------------------------------------------
def test_auditor_varre_todos_e_acha_os_casos_citados(store):
    findings = audit_store(store)
    keyed = {(f.product_id, f.kind) for f in findings}
    assert {(135, "brand_mismatch"), (139, "brand_mismatch"), (137, "count_mismatch"),
            (142, "count_mismatch")} <= keyed
    flagged = {f.product_id for f in findings if f.customer_facing and f.severity in ("alta", "média")}
    assert flagged == CONFLICT_IDS
    counts = count_by(findings)
    assert counts["count_mismatch"]["alta"] == 2 and counts["brand_mismatch"]["alta"] == 6
    assert sum(sum(c.values()) for c in counts.values()) == len(findings)


def test_auditor_nao_escolhe_campo_verdadeiro(store):
    f = next(x for x in audit_store(store) if x.product_id == 137 and x.kind == "count_mismatch")
    assert f.description_says == "5 cordas" and f.structured_says == "strings=4"
    assert f.compared_with == "specs"


def test_auditor_detecta_specs_ausentes_e_descricao_vazia(store):
    p = store.products[81]
    broken = replace(p, specs={}, description="")
    s2 = replace(store, products={**store.products, 81: broken})
    kinds = {f.kind for f in audit_store(s2) if f.product_id == 81}
    assert {"specs_missing", "description_empty"} <= kinds


def test_auditor_detecta_valor_vazio_e_categoria_incoerente(store):
    p = store.products[81]
    s2 = replace(store, products={**store.products, 81: replace(p, specs={**p.specs, "color": ""}, category_id=9)})
    kinds = {f.kind for f in audit_store(s2) if f.product_id == 81}
    assert {"specs_empty_value", "category_mismatch"} <= kinds


def test_auditor_detecta_tamanho_de_ukulele_e_material_das_cordas(store):
    p = store.products[116]  # soprano, escala 346mm, nylon
    nylon = store.products[83]  # descrição: "cordas de nylon"
    s2 = replace(store, products={
        **store.products,
        116: replace(p, specs={**p.specs, "scale": "432mm"}),
        83: replace(nylon, specs={**nylon.specs, "strings": "steel"})})
    found = {(f.product_id, f.kind) for f in audit_store(s2)}
    assert {(116, "size_mismatch"), (83, "strings_material_mismatch")} <= found


def test_auditor_detecta_eletronica_contradita(store):
    p = store.products[122]  # ukulele eletroacústico
    s2 = replace(store, products={**store.products, 122: replace(p, specs={**p.specs, "electronics": "no"})})
    f = [x for x in audit_store(s2) if x.product_id == 122 and x.kind == "electronics_mismatch"]
    assert f and f[0].severity == "alta"


# --- ferramentas: conflitos sinalizados -----------------------------------------
def test_137_cordas_contraditorias_nao_sao_confirmadas(store):
    r = check_product_availability(product_id=137, store=store)
    conflicts = _conflicts(r)
    assert conflicts["strings_count"]["description_says"] == "5 cordas"
    assert conflicts["strings_count"]["specs_say"] == "strings=4"
    attr = _attrs(r)["strings_count"]
    assert attr["status"] == "contradictory" and attr["value"] == "unknown"
    assert "NÃO afirme" in r["note"] and "atendente" in r["note"]


def test_142_teclas_contraditorias(store):
    r = check_product_availability(product_id=142, store=store)
    assert _conflicts(r)["keys"]["description_says"] == "88 teclas"
    assert _conflicts(r)["keys"]["specs_say"] == "keys=61"
    assert _attrs(r)["keys"]["status"] == "contradictory"
    assert _attrs(r)["keys"]["value"] == "unknown"


@pytest.mark.parametrize("pid,desc_brand,name_brand", [(135, "Fender", "Music Man"), (139, "Pearl", "Yamaha")])
def test_nome_vs_descricao_marca(store, pid, desc_brand, name_brand):
    r = check_product_availability(product_id=pid, store=store)
    c = _conflicts(r)["brand_model"]
    assert desc_brand in c["description_says"] and name_brand in c["specs_say"]
    assert c["severity"] == "alta"
    assert _attrs(r)["brand_model"]["status"] == "contradictory"
    assert "description_warning" in r["product"]["details"]


def test_busca_fender_jazz_bass_casa_so_pela_descricao_e_avisa(store):
    r = search_products(query="Fender Jazz Bass", store=store)
    assert r["status"] == "found"
    (p,) = r["products"]
    assert p["product_id"] == 135 and p["matched_on"] == "description"
    assert "fender" in p["query_terms_not_in_name"] and "jazz" in p["query_terms_not_in_name"]
    assert "match_warning" in p and "só pela descrição" in r["note"]
    by_name = check_product_availability(name="Fender Jazz Bass", store=store)
    assert by_name["product"]["product_id"] == 135 and "só pela descrição" in by_name["note"]


def test_busca_por_nome_marca_matched_on_name(store):
    r = search_products(query="Takamine GD20", store=store)
    assert r["products"][0]["matched_on"] == "name"
    assert "match_warning" not in r["products"][0] and "note" not in r


def test_ambiguo_traz_conflitos_dos_candidatos_sem_detalhes(store):
    r = search_products(query="Bass", store=store)
    assert r["status"] == "ambiguous"
    assert all("details" not in c for c in r["candidates"])
    assert any(c.get("data_conflicts") for c in r["candidates"]) and "note" in r
    assert len(json.dumps(r, ensure_ascii=False)) < MAX_CANDIDATES_CHARS


# --- ferramentas: atributos classificados -----------------------------------------
def test_produto_sem_conflito_tem_atributos_confirmados(store):
    r = check_product_availability(product_id=81, store=store)
    assert r["product"]["data_conflicts"] == [] and "note" not in r
    attrs = _attrs(r)
    assert attrs["strings_material"] == {"label": "material das cordas", "status": "confirmed",
                                         "value": "nylon", "source": "specs"}
    assert attrs["electronics"]["status"] == "confirmed" and attrs["electronics"]["value"] == "no"
    assert attrs["materials"]["value"]["top"] == "Spruce"


def test_atributo_inexistente_vem_unknown_nunca_completado(store):
    r = check_product_availability(product_id=81, store=store)  # violão: specs não tem nº de cordas
    assert _attrs(r)["strings_count"]["status"] == "absent"
    assert _attrs(r)["strings_count"]["value"] == "unknown"
    ukulele = check_product_availability(product_id=116, store=store)
    assert _attrs(ukulele)["strings_count"]["value"] == "unknown"


def test_produto_sem_specs_vira_unknown(store):
    p = store.products[137]
    s2 = replace(store, products={**store.products, 137: replace(p, specs={})})
    attrs = product_attributes(s2, s2.products[137])
    assert attrs["strings_count"]["status"] == "unverifiable"  # só a descrição diz "5 cordas"
    assert attrs["materials"]["status"] == "absent" and attrs["materials"]["value"] == "unknown"
    bare = replace(p, specs={}, description="Contrabaixo.", name="Baixo Qualquer")
    s3 = replace(store, products={**store.products, 137: bare})
    attrs = product_attributes(s3, s3.products[137])
    assert attrs["strings_count"] == {"label": "quantidade de cordas", "status": "absent", "value": "unknown"}
    assert attrs["color"]["status"] == "absent"


def test_7_cordas_confirmado_por_nome_e_descricao(store):
    attrs = _attrs(check_product_availability(product_id=109, store=store))
    assert attrs["strings_count"]["status"] == "confirmed" and attrs["strings_count"]["value"] == 7
    assert attrs["strings_count"]["source"] == "name+description"


def test_produto_sem_conflito_nao_e_marcado_como_conflito(store):
    assert product_conflicts(store, store.products[95]) == []
    assert {f.product_id for f in audit_store(store) if f.customer_facing and f.severity != "baixa"} == CONFLICT_IDS


# --- tamanho do payload ----------------------------------------------------------
def test_payload_de_um_produto_e_limitado(store):
    for pid in store.products:
        text = json.dumps(check_product_availability(product_id=pid, store=store), ensure_ascii=False)
        assert len(text) < MAX_SINGLE_PRODUCT_CHARS, pid


def test_descricao_truncada_no_limite(store):
    p = store.products[81]
    long = replace(p, description="x" * 5000)
    s2 = replace(store, products={**store.products, 81: long})
    r = check_product_availability(product_id=81, store=s2)
    assert len(r["product"]["details"]["description"]) <= 241


def test_lista_grande_nao_inclui_detalhes(store):
    r = search_products(category="violão", store=store)
    assert r["status"] == "found" and len(r["products"]) == 20
    assert all("details" not in p for p in r["products"])
    assert len(json.dumps(r, ensure_ascii=False)) < 10000


def test_registry_executa_com_detalhes(store):
    r = execute("check_product_availability", {"product_id": 137}, store=store)
    assert r["status"] == "found" and r["product"]["data_conflicts"]


# --- dados originais intactos -------------------------------------------------------
def test_dados_originais_nao_mudam_apos_auditoria_e_ferramentas(store):
    audit_store(store)
    for pid in (135, 137, 142):
        check_product_availability(product_id=pid, store=store)
    for name, expected in ORIGINAL_SHA256.items():
        digest = hashlib.sha256((PROJECT_ROOT / "data" / name).read_bytes()).hexdigest()
        assert digest == expected, name
    assert len(list((PROJECT_ROOT / "data").glob("*.pdf"))) == 1
