"""Auditor determinístico de qualidade dos dados de produtos.

Compara os campos de cada produto entre si (nome, descrição em texto livre e
`specs` estruturado) e relata divergências. NÃO decide qual campo é o
verdadeiro: só prova que dois campos do mesmo produto não concordam.

Os mesmos extratores alimentam as ferramentas do agente
(`product_attributes` / `product_conflicts`), de modo que o que o auditor
relata é exatamente o que o agente recebe como aviso.

Limites conhecidos (ver docs/DATA_QUALITY.md): marcas, madeiras e modelos
dependem de léxicos manuais e curtos; só se comparam atributos que aparecem
em mais de uma fonte; nada é verificado contra o mundo real.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median

from app.data.models import DataStore, Product
from app.data.normalize import normalize_text, tokenize

HIGH, MEDIUM, LOW = "alta", "média", "baixa"

# ---------------------------------------------------------------------------
# Léxicos (manuais, curtos e documentados como limitação)
# ---------------------------------------------------------------------------
BRANDS = {  # marca normalizada -> nome de exibição
    "yamaha": "Yamaha", "tagima": "Tagima", "giannini": "Giannini", "rozini": "Rozini",
    "martin": "Martin", "taylor": "Taylor", "takamine": "Takamine", "crafter": "Crafter",
    "shelby": "Shelby", "kala": "Kala", "ohana": "Ohana", "kalani": "Kalani",
    "fender": "Fender", "gibson": "Gibson", "ibanez": "Ibanez", "prs": "PRS",
    "music man": "Music Man", "pearl": "Pearl", "tama": "Tama", "korg": "Korg",
    "nord": "Nord", "roland": "Roland",
}
# modelo (normalizado) tipicamente associado a uma marca: conhecimento externo aos dados.
MODEL_HINTS = {
    "jazz bass": "Fender", "precision": "Fender", "stratocaster": "Fender",
    "telecaster": "Fender", "stingray": "Music Man", "les paul": "Gibson",
    "export": "Pearl", "stage custom": "Yamaha", "nord stage": "Nord",
    "supernatural": "Roland",
}
WOODS = {  # termo normalizado -> madeira canônica
    "mogno asiatico": "mahogany", "mogno": "mahogany", "mahogany": "mahogany",
    "cedro": "cedar", "cedar": "cedar", "spruce": "spruce", "sitka": "spruce",
    "engelmann": "spruce", "rosewood": "rosewood", "jacaranda": "jacaranda",
    "pau ferro": "pau ferro", "ovangkol": "ovangkol", "walnut": "walnut", "nato": "nato",
    "sapele": "sapele", "linden": "linden", "poplar": "poplar", "birch": "birch",
    "maple": "maple", "bordo": "maple", "alder": "alder", "ash": "ash",
    "basswood": "basswood", "meranti": "meranti", "acacia": "acacia",
    "hardwood": "hardwood",
}
# palavra da descrição -> campos de specs onde essa parte do instrumento aparece
PART_FIELDS = {"corpo": ("body", "top", "back_sides"), "tampo": ("top",),
               "fundo": ("back_sides",), "cascos": ("shells",), "braco": ("neck",)}
PART_STOP = {"com", "para", "fundo", "corpo", "tampo", "braco", "ferragens", "sistema",
             "acabamento", "captacao", "pre", "escala", "afinacao"}
NUM_WORDS = {"um": 1, "uma": 1, "dois": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6,
             "sete": 7, "oito": 8, "nove": 9, "dez": 10, "doze": 12}
COUNT_RE = {
    "strings_count": re.compile(r"\b(\d+|" + "|".join(NUM_WORDS) + r") cordas\b"),
    "keys": re.compile(r"\b(\d+) teclas\b"),
    "pieces": re.compile(r"\b(\d+|" + "|".join(NUM_WORDS) + r") pecas\b"),
}
STRONG_ELECTRONICS = ("eletroacustic", "captacao", "pre amplificador", "piezo", "equalizador",
                      "eletronica")
WEAK_ELECTRONICS = ("afinador",)
UKE_SIZES = {"soprano": 346, "concert": 381, "tenor": 432, "baritono": 502}  # escala em mm
UKE_TOLERANCE_MM = 10
COLORS = {"natural": "natural", "sunburst": "sunburst", "preto": "black", "black": "black"}
LEADING_CATEGORY = {"violao": 5, "ukulele": 9, "guitarra": 1, "contrabaixo": 2, "baixo": 2,
                    "bateria": 3, "teclado": 4, "sintetizador": 4, "piano": 4}
OUTLIER_FACTOR = 5  # preço fora de [Q1/5, Q3*5] da categoria (sem o próprio produto)
MIN_CATEGORY_FOR_OUTLIER = 6
# atributos que um cliente costuma perguntar, por categoria (para marcar "ausente")
EXPECTED_ATTRS = {
    1: ("strings_count",), 2: ("strings_count",), 3: ("pieces",), 4: ("keys",),
    5: ("strings_count", "strings_material", "electronics"),
    9: ("strings_count", "strings_material", "electronics", "size"),
}
ATTR_LABELS = {
    "strings_count": "quantidade de cordas", "strings_material": "material das cordas",
    "keys": "quantidade de teclas", "pieces": "quantidade de peças",
    "electronics": "eletrônica/captação", "size": "tamanho do ukulele", "color": "cor",
    "materials": "madeiras/materiais", "brand_model": "marca/modelo",
    "category": "tipo de instrumento",
}
SOURCE_ORDER = ("description", "name", "specs")


@dataclass(frozen=True)
class Finding:
    product_id: int
    product_name: str
    kind: str              # tipo da divergência
    severity: str          # alta | média | baixa
    field: str             # atributo (chave de ATTR_LABELS ou nome do campo)
    description_says: str  # o que a descrição (ou o campo citado) afirma
    structured_says: str   # o que o campo estruturado/nome afirma
    compared_with: str     # specs | name | catalog
    detail: str = ""

    @property
    def customer_facing(self) -> bool:
        return self.kind not in NON_CUSTOMER_KINDS


KIND_SEVERITY = {
    "count_mismatch": HIGH, "brand_mismatch": HIGH, "category_mismatch": HIGH,
    "size_mismatch": HIGH, "strings_material_mismatch": HIGH, "electronics_mismatch": HIGH,
    "model_hint_mismatch": MEDIUM, "material_mismatch": MEDIUM, "color_mismatch": MEDIUM,
    "specs_missing": MEDIUM, "description_empty": MEDIUM,
    "specs_key_missing": LOW, "specs_empty_value": LOW, "price_outlier": LOW,
    "stock_status_inconsistent": LOW,
}
NON_CUSTOMER_KINDS = {"specs_missing", "description_empty", "specs_key_missing",
                      "specs_empty_value", "price_outlier", "stock_status_inconsistent"}
KIND_LABELS = {
    "count_mismatch": "quantidade divergente (cordas/teclas/peças)",
    "brand_mismatch": "marca do nome ≠ marca na descrição",
    "model_hint_mismatch": "modelo na descrição associado a outra marca",
    "category_mismatch": "tipo de instrumento incoerente com a categoria",
    "size_mismatch": "tamanho do ukulele ≠ escala em specs",
    "strings_material_mismatch": "material das cordas divergente",
    "electronics_mismatch": "eletrônica/captação divergente",
    "material_mismatch": "madeira/material divergente",
    "color_mismatch": "cor divergente",
    "specs_missing": "specs ausente",
    "description_empty": "descrição vazia",
    "specs_key_missing": "chave esperada ausente em specs",
    "specs_empty_value": "valor vazio em specs",
    "price_outlier": "preço atípico para a categoria",
    "stock_status_inconsistent": "estoque incoerente com o status",
}
KIND_IMPACT = {
    "count_mismatch": "O agente pode informar um número errado de cordas/teclas/peças e levar a compra do produto errado.",
    "brand_mismatch": "O agente pode confirmar marca/modelo que não é a do produto vendido pelo nome.",
    "model_hint_mismatch": "A descrição cita um modelo de outra marca; risco de confirmar o modelo errado.",
    "category_mismatch": "Produto pode aparecer na categoria errada ou ser descrito como outro instrumento.",
    "size_mismatch": "O agente pode informar o tamanho (soprano/concert/tenor/barítono) errado.",
    "strings_material_mismatch": "Cliente pode comprar nylon querendo aço (ou vice-versa).",
    "electronics_mismatch": "O agente pode afirmar que o instrumento é (ou não é) eletroacústico sem base.",
    "material_mismatch": "Informação de madeira/acabamento pode estar errada; afeta valor percebido.",
    "color_mismatch": "Cor informada pode não corresponder ao produto.",
    "specs_missing": "Sem ficha técnica: atributos só existem no texto livre, sem verificação.",
    "description_empty": "Sem descrição; só nome e specs para responder.",
    "specs_key_missing": "Atributo esperado da categoria fica 'desconhecido' para o agente.",
    "specs_empty_value": "Atributo existe mas sem valor; fica 'desconhecido'.",
    "price_outlier": "Pode indicar erro de cadastro de preço; não prova erro (produtos premium existem).",
    "stock_status_inconsistent": "Estoque sem efeito prático; o status manda (já tratado em availability).",
}
KIND_TREATMENT = {
    "count_mismatch": "Não afirmar; sinalizar conflito e encaminhar a atendente; corrigir a base na origem.",
    "brand_mismatch": "Usar só o nome como identificação; não repetir a marca/modelo da descrição; corrigir a base.",
    "model_hint_mismatch": "Tratar como suspeita (léxico externo); não citar o modelo da descrição.",
    "category_mismatch": "Revisar categoria na origem; agente não deve afirmar o tipo até confirmar.",
    "size_mismatch": "Não afirmar o tamanho; confirmar com atendente.",
    "strings_material_mismatch": "Não afirmar o material; confirmar com atendente.",
    "electronics_mismatch": "Não afirmar se é eletroacústico; confirmar com atendente.",
    "material_mismatch": "Não afirmar a madeira; informar só o que não diverge.",
    "color_mismatch": "Não afirmar a cor; confirmar com atendente.",
    "specs_missing": "Atributos ficam 'desconhecido'; só citar o que estiver no nome.",
    "description_empty": "Responder só com nome/specs; sem inventar.",
    "specs_key_missing": "Atributo reportado como 'desconhecido' (ausente), nunca completado.",
    "specs_empty_value": "Atributo reportado como 'desconhecido' (ausente), nunca completado.",
    "price_outlier": "Nenhum: preço vem do sistema; revisão humana opcional.",
    "stock_status_inconsistent": "Nenhum: disponibilidade já segue o status.",
}


# ---------------------------------------------------------------------------
# Extração por fonte
# ---------------------------------------------------------------------------
def _to_int(token: str) -> int | None:
    if token.isdigit():
        return int(token)
    return NUM_WORDS.get(token)


def _count(text: str, attr: str) -> int | None:
    match = COUNT_RE[attr].search(normalize_text(text))
    return _to_int(match.group(1)) if match else None


def _spec_int(specs: dict, key: str) -> int | None:
    raw = str(specs.get(key, "")).strip()
    return int(raw) if raw.isdigit() else None


def _brands_in(text: str) -> list[str]:
    padded = f" {normalize_text(text)} "
    return [display for key, display in BRANDS.items() if f" {key} " in padded]


def _woods_in(text: str) -> set[str]:
    padded = f" {normalize_text(text)} "
    return {canon for term, canon in WOODS.items() if f" {term} " in padded}


def _part_woods(description: str) -> dict[str, tuple[set[str], str]]:
    """parte do instrumento -> (madeiras citadas, trecho normalizado)."""
    out: dict[str, tuple[set[str], str]] = {}
    for sentence in re.split(r"[.;!?]", description):
        tokens = tokenize(sentence)
        for i, tok in enumerate(tokens):
            if tok not in PART_FIELDS or tok in out:
                continue
            window = [tok]
            for nxt in tokens[i + 1:i + 8]:
                if nxt in PART_STOP:
                    break
                window.append(nxt)
            woods = _woods_in(" ".join(window[1:]))
            if woods:
                out[tok] = (woods, " ".join(window))
    return out


def _electronics_text(text: str, category_id: int) -> str | None:
    """'strong' | 'weak' | None; só para violões e ukuleles."""
    if category_id not in (5, 9):
        return None
    norm = normalize_text(text)
    if any(k in norm for k in STRONG_ELECTRONICS):
        return "strong"
    return "weak" if any(k in norm for k in WEAK_ELECTRONICS) else None


def _strings_material(text: str) -> str | None:
    norm = normalize_text(text)
    if re.search(r"\b(?:cordas? )?(?:de |em )?nylon\b", norm):
        return "nylon"
    if re.search(r"\b(?:cordas? )?(?:de |em )?aco\b", norm):
        return "steel"
    return None


def _uke_size(text: str) -> str | None:
    for tok in tokenize(text):
        if tok in UKE_SIZES:
            return tok
    return None


def _color(text: str) -> str | None:
    for tok in tokenize(text):
        if tok in COLORS:
            return COLORS[tok]
    return None


def _spec_color(specs: dict) -> frozenset[str] | None:
    """Tokens de cor de specs (ex.: 'Heritage Cherry Sunburst' -> {..., 'sunburst'})."""
    tokens = tokenize(str(specs.get("color", "")))
    return frozenset(COLORS.get(t, t) for t in tokens) or None


def _spec_strings_material(specs: dict) -> str | None:
    raw = normalize_text(str(specs.get("strings", "")))
    return raw if raw in ("nylon", "steel") else None


def _spec_size(specs: dict) -> str | None:
    scale = re.match(r"\d+", str(specs.get("scale", "")))
    if not scale:
        return None
    mm = int(scale.group())
    for size, ref in UKE_SIZES.items():
        if abs(mm - ref) <= UKE_TOLERANCE_MM:
            return size
    return None


def observations(product: Product) -> dict[str, dict[str, object]]:
    """atributo -> {fonte: valor normalizado}; fontes sem valor ficam de fora."""
    cat, specs = product.category_id, product.specs
    name, desc = product.name, product.description
    obs: dict[str, dict[str, object]] = {}

    def put(attr: str, source: str, value: object) -> None:
        if value is not None:
            obs.setdefault(attr, {})[source] = value

    for attr in ("strings_count", "pieces", "keys"):
        put(attr, "description", _count(desc, attr))
        put(attr, "name", _count(name, attr))
    put("strings_count", "specs", _spec_int(specs, "strings"))
    put("pieces", "specs", _spec_int(specs, "pieces"))
    put("keys", "specs", _spec_int(specs, "keys"))

    put("strings_material", "description", _strings_material(desc))
    put("strings_material", "name", _strings_material(name))
    put("strings_material", "specs", _spec_strings_material(specs))

    if cat in (5, 9):
        for source, text in (("description", desc), ("name", name)):
            level = _electronics_text(text, cat)
            if level is None and source == "name" and "eletrico" in tokenize(text):
                level = "strong"
            put("electronics", source, level)
        flag = str(specs.get("electronics", "")).strip().lower()
        if flag in ("yes", "no"):
            put("electronics", "specs", flag)
    if cat == 9:
        put("size", "description", _uke_size(desc))
        put("size", "name", _uke_size(name))
        put("size", "specs", _spec_size(specs))
    put("color", "description", _color(desc))
    put("color", "name", _color(name))
    put("color", "specs", _spec_color(specs))
    return obs


# ---------------------------------------------------------------------------
# Regras de divergência (por produto)
# ---------------------------------------------------------------------------
def _fmt(attr: str, value: object, source: str) -> str:
    unit = {"strings_count": "cordas", "keys": "teclas", "pieces": "peças"}.get(attr)
    if unit:
        return f"{value} {unit}" if source != "specs" else f"{attr_key(attr)}={value}"
    return str(value)


def attr_key(attr: str) -> str:
    return {"strings_count": "strings", "keys": "keys", "pieces": "pieces"}.get(attr, attr)


def _pairs(sources: dict[str, object]) -> list[tuple[str, str]]:
    """(fonte_texto, fonte_comparada) em ordem de prioridade: descr×specs, nome×specs, descr×nome."""
    out = []
    if "description" in sources and "specs" in sources:
        out.append(("description", "specs"))
    if "name" in sources and "specs" in sources:
        out.append(("name", "specs"))
    if "description" in sources and "name" in sources:
        out.append(("description", "name"))
    return out


_ATTR_KIND = {"strings_count": "count_mismatch", "keys": "count_mismatch",
              "pieces": "count_mismatch", "strings_material": "strings_material_mismatch",
              "size": "size_mismatch", "color": "color_mismatch"}


def _disagree(attr: str, text_value: object, other_value: object) -> bool:
    if attr == "color":  # specs pode listar vários termos de cor
        return text_value not in other_value
    return text_value != other_value


def _attribute_findings(product: Product) -> list[Finding]:
    found: list[Finding] = []
    for attr, sources in observations(product).items():
        if attr == "electronics":
            found.extend(_electronics_findings(product, sources))
            continue
        pairs = [p for p in _pairs(sources) if attr != "color" or p[1] == "specs"]
        pair = next((p for p in pairs if _disagree(attr, sources[p[0]], sources[p[1]])), None)
        if pair is None:
            continue
        a, b = pair
        says = _fmt(attr, sources[a], a)
        other = f"color={product.specs.get('color')}" if attr == "color" else _fmt(attr, sources[b], b)
        kind = _ATTR_KIND[attr]
        found.append(Finding(product.product_id, product.name, kind, KIND_SEVERITY[kind], attr,
                             says, other, "specs" if b == "specs" else "name", f"{a} × {b}"))
    return found


def _electronics_findings(product: Product, sources: dict[str, object]) -> list[Finding]:
    specs_flag = sources.get("specs")
    if specs_flag != "no":
        return []
    out = []
    for source in ("description", "name"):
        level = sources.get(source)
        if level in ("strong", "weak"):
            kind = "electronics_mismatch"
            sev = HIGH if level == "strong" else LOW
            says = "cita captação/eletrônica" if source == "description" else "nome diz 'Elétrico'"
            if level == "weak":
                says = "cita afinador integrado"
            out.append(Finding(product.product_id, product.name, kind, sev, "electronics", says,
                               "electronics=no", "specs", f"{source} × specs"))
    return out


def _material_findings(product: Product) -> list[Finding]:
    out = []
    for part, (woods, clause) in _part_woods(product.description).items():
        spec_woods: set[str] = set()
        keys = []
        for field in PART_FIELDS[part]:
            if field in product.specs:
                spec_woods |= _woods_in(str(product.specs[field]))
                keys.append(f"{field}={product.specs[field]}")
        if spec_woods and not (woods & spec_woods):
            out.append(Finding(product.product_id, product.name, "material_mismatch",
                               KIND_SEVERITY["material_mismatch"], "materials", clause,
                               ", ".join(keys), "specs", f"parte '{part}'"))
    return out


def _brand_findings(product: Product) -> list[Finding]:
    name_brands = set(_brands_in(product.name))
    desc_brands = _brands_in(product.description)
    if not name_brands:
        return []
    extra = [b for b in desc_brands if b not in name_brands]
    out = []
    if extra:
        out.append(Finding(product.product_id, product.name, "brand_mismatch", HIGH,
                           "brand_model", f"marca na descrição: {', '.join(extra)}",
                           f"marca no nome: {', '.join(sorted(name_brands))}", "name",
                           "descrição × nome"))
    padded = f" {normalize_text(product.description)} "
    for hint, brand in MODEL_HINTS.items():
        if f" {hint} " in padded and brand not in name_brands and brand not in extra:
            out.append(Finding(product.product_id, product.name, "model_hint_mismatch", MEDIUM,
                               "brand_model", f"modelo '{hint}' (associado à {brand})",
                               f"marca no nome: {', '.join(sorted(name_brands))}", "name",
                               "descrição × nome (léxico externo)"))
    return out


def _category_findings(store: DataStore, product: Product) -> list[Finding]:
    category = store.categories[product.category_id].name
    for label, text in (("descrição", product.description), ("nome", product.name)):
        for tok in tokenize(text)[:3]:
            expected = LEADING_CATEGORY.get(tok)
            if expected is not None:
                if expected != product.category_id:
                    return [Finding(product.product_id, product.name, "category_mismatch", HIGH,
                                    "category", f"{label} começa com '{tok}'",
                                    f"categoria: {category}", "catalog", f"{label} × category_id")]
                break
    return []


def _presence_findings(product: Product) -> list[Finding]:
    out = []
    if not product.description.strip():
        out.append(Finding(product.product_id, product.name, "description_empty", MEDIUM,
                           "description", "(vazia)", "-", "catalog"))
    if not product.specs:
        out.append(Finding(product.product_id, product.name, "specs_missing", MEDIUM,
                           "specs", "-", "(ausente)", "catalog"))
    for key, value in product.specs.items():
        if value is None or str(value).strip() == "":
            out.append(Finding(product.product_id, product.name, "specs_empty_value", LOW,
                               f"specs.{key}", "-", "(vazio)", "catalog"))
    return out


def product_findings(store: DataStore, product: Product) -> list[Finding]:
    """Divergências verificáveis olhando só para o próprio produto."""
    return (_attribute_findings(product) + _material_findings(product)
            + _brand_findings(product) + _category_findings(store, product)
            + _presence_findings(product))


def product_conflicts(store: DataStore, product: Product) -> list[Finding]:
    """Divergências que o agente deve tratar como conflito (alta/média, voltadas ao cliente)."""
    return [f for f in product_findings(store, product)
            if f.customer_facing and f.severity in (HIGH, MEDIUM)]


# ---------------------------------------------------------------------------
# Regras de catálogo (dependem de outros produtos)
# ---------------------------------------------------------------------------
def _quartiles(values: list[float]) -> tuple[float, float]:
    ordered = sorted(values)
    half = len(ordered) // 2
    return median(ordered[:half]), median(ordered[-half:])


def _catalog_findings(store: DataStore) -> list[Finding]:
    out: list[Finding] = []
    by_cat: dict[int, list[Product]] = {}
    for p in store.products.values():
        by_cat.setdefault(p.category_id, []).append(p)
    for cat, items in by_cat.items():
        keys = {k for p in items for k in p.specs}
        expected = {k for k in keys if sum(k in p.specs for p in items) / len(items) >= 0.5}
        for p in items:
            if p.specs:  # specs ausente já é outro tipo
                for key in sorted(expected - set(p.specs)):
                    out.append(Finding(p.product_id, p.name, "specs_key_missing", LOW,
                                       f"specs.{key}", "-", "(chave ausente)", "catalog"))
            if len(items) >= MIN_CATEGORY_FOR_OUTLIER:
                others = [float(o.price_brl) for o in items if o is not p]
                q1, q3 = _quartiles(others)
                price = float(p.price_brl)
                if price < q1 / OUTLIER_FACTOR or price > q3 * OUTLIER_FACTOR:
                    out.append(Finding(p.product_id, p.name, "price_outlier", LOW, "price_brl",
                                       "-", f"R$ {price:.2f} (Q1={q1:.0f}, Q3={q3:.0f} da categoria)",
                                       "catalog"))
            if p.status == "discontinued" and p.stock_quantity > 0:
                out.append(Finding(p.product_id, p.name, "stock_status_inconsistent", LOW,
                                   "stock_quantity", f"estoque {p.stock_quantity}",
                                   "status=discontinued", "catalog"))
            if p.status == "coming_soon" and p.stock_quantity > 0:
                out.append(Finding(p.product_id, p.name, "stock_status_inconsistent", LOW,
                                   "stock_quantity", f"estoque {p.stock_quantity}",
                                   "status=coming_soon", "catalog"))
    return out


def audit_store(store: DataStore) -> list[Finding]:
    """Varre TODOS os produtos. Ordem: product_id, depois gravidade e tipo."""
    findings = _catalog_findings(store)
    for product in store.products.values():
        findings.extend(product_findings(store, product))
    rank = {HIGH: 0, MEDIUM: 1, LOW: 2}
    return sorted(findings, key=lambda f: (f.product_id, rank[f.severity], f.kind, f.field))


def count_by(findings: list[Finding]) -> dict[str, dict[str, int]]:
    """tipo -> {gravidade: n}."""
    table: dict[str, dict[str, int]] = {}
    for f in findings:
        table.setdefault(f.kind, {HIGH: 0, MEDIUM: 0, LOW: 0})[f.severity] += 1
    return table


# ---------------------------------------------------------------------------
# Visão para o agente: atributos classificados
# ---------------------------------------------------------------------------
CONFIRMED, ABSENT, CONTRADICTORY, UNVERIFIABLE = "confirmed", "absent", "contradictory", "unverifiable"
UNKNOWN = "unknown"
_MATERIAL_FIELDS = ("body", "top", "back_sides", "neck", "shells")


def product_attributes(store: DataStore, product: Product,
                       conflicts: list[Finding] | None = None) -> dict[str, dict]:
    """Cada atributo relevante como confirmed | absent | contradictory | unverifiable.

    - confirmed: valor em specs sem contradição, ou nome e descrição concordam.
    - unverifiable: valor só em uma fonte não estruturada (descrição ou nome).
    - contradictory: fontes discordam (ver data_conflicts); nenhum valor é afirmado.
    - absent: não existe nos dados; valor 'unknown' (nunca completado).
    """
    conflicts = product_conflicts(store, product) if conflicts is None else conflicts
    bad = {f.field for f in conflicts}
    obs = observations(product)
    attrs: dict[str, dict] = {}
    names = list(EXPECTED_ATTRS.get(product.category_id, ()))
    names += [a for a in obs if a not in names and a not in ("color",)] + ["color"]
    for attr in names:
        sources = obs.get(attr, {})
        if attr == "electronics":  # texto só vale se afirma captação; 'weak' (afinador) não
            sources = {s: ("yes" if v == "strong" else v) for s, v in sources.items()
                       if s == "specs" or v == "strong"}
        label = ATTR_LABELS[attr]
        if attr in bad:
            attrs[attr] = {"label": label, "status": CONTRADICTORY, "value": UNKNOWN,
                           "see": "data_conflicts"}
        elif "specs" in sources:
            value = product.specs["color"] if attr == "color" else sources["specs"]
            attrs[attr] = {"label": label, "status": CONFIRMED, "value": value, "source": "specs"}
        elif len(sources) == 2 and sources["name"] == sources["description"]:
            attrs[attr] = {"label": label, "status": CONFIRMED, "value": sources["name"],
                           "source": "name+description"}
        elif sources:
            src = next(s for s in SOURCE_ORDER if s in sources)
            attrs[attr] = {"label": label, "status": UNVERIFIABLE, "value": sources[src],
                           "source": src}
        else:
            attrs[attr] = {"label": label, "status": ABSENT, "value": UNKNOWN}
    materials = {k: product.specs[k] for k in _MATERIAL_FIELDS if str(product.specs.get(k, "")).strip()}
    if "materials" in bad:
        attrs["materials"] = {"label": ATTR_LABELS["materials"], "status": CONTRADICTORY,
                              "value": UNKNOWN, "see": "data_conflicts"}
    elif materials:
        attrs["materials"] = {"label": ATTR_LABELS["materials"], "status": CONFIRMED,
                              "value": materials, "source": "specs"}
    else:
        attrs["materials"] = {"label": ATTR_LABELS["materials"], "status": ABSENT, "value": UNKNOWN}
    attrs["brand_model"] = ({"label": ATTR_LABELS["brand_model"], "status": CONTRADICTORY,
                             "value": UNKNOWN, "see": "data_conflicts"}
                            if "brand_model" in bad else
                            {"label": ATTR_LABELS["brand_model"], "status": CONFIRMED,
                             "value": product.name, "source": "name"})
    return attrs
