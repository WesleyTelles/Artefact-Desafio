"""Busca de produtos e checagem de disponibilidade (determinísticas)."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.core.exceptions import ToolInputError
from app.data.loader import get_store
from app.data.models import DataStore, Product
from app.data.normalize import format_brl, money_str, normalize_text, tokenize
from app.tools.promotions import active_promotion_for, promotion_info

# sinônimo normalizado -> category_id (ids do categories.csv)
CATEGORY_SYNONYMS: dict[str, int] = {
    **dict.fromkeys(["violao", "violoes"], 5),
    **dict.fromkeys(["guitarra", "guitarras"], 1),
    **dict.fromkeys(["baixo", "baixos"], 2),
    **dict.fromkeys(["bateria", "baterias", "percussao"], 3),
    **dict.fromkeys(["teclado", "teclados", "piano", "pianos", "sintetizador", "sintetizadores"], 4),
    **dict.fromkeys(["ukulele", "ukuleles", "ukelele", "uke"], 9),
    **dict.fromkeys(["sax", "saxofone", "saxofones", "flauta", "flautas", "clarinete", "clarinetes",
                     "obo", "oboe"], 6),
    **dict.fromkeys(["trompete", "trompetes", "trombone", "trombones", "tuba", "tubas",
                     "trompa", "trompas"], 7),
    **dict.fromkeys(["violino", "violinos", "viola", "violoncelo", "violoncelos", "cello"], 8),
}
# acessórios que a loja não vende (manual §1). "cordas" aparece em "7 Cordas".
ACCESSORY_WORDS = {"corda", "cordas", "encordoamento", "palheta", "palhetas", "cabo", "cabos",
                   "case", "cases", "capa", "pedal", "pedais", "amplificador", "amplificadores",
                   "afinador", "correia"}
STOPWORDS = {"de", "do", "da", "dos", "das", "um", "uma", "o", "a", "os", "as", "com", "para",
             "por", "em", "no", "na", "e", "ou", "quero", "queria", "procuro", "tem", "voces",
             "que", "ate", "reais", "r"}
MAX_RESULTS = 20
MAX_CANDIDATES = 10

AVAILABILITY_LABELS = {
    "in_stock": "Em estoque",
    "out_of_stock": "Ativo, sem estoque no momento",
    "discontinued": "Descontinuado",
    "coming_soon": "Em breve (ainda não disponível para compra)",
    "unavailable": "Indisponível",
}


def availability_of(product: Product) -> str:
    if product.status == "active":
        return "in_stock" if product.stock_quantity > 0 else "out_of_stock"
    if product.status in ("discontinued", "coming_soon"):
        return product.status
    return "unavailable"


def is_available(product: Product) -> bool:
    return product.status == "active" and product.stock_quantity > 0


def product_summary(store: DataStore, product: Product) -> dict:
    code = availability_of(product)
    out = {
        "product_id": product.product_id,
        "name": product.name,
        "category": store.categories[product.category_id].name,
        "price_brl": money_str(product.price_brl),
        "price_display": format_brl(product.price_brl),
        "stock_quantity": product.stock_quantity,
        "product_status": product.status,
        "availability": code,
        "availability_label": AVAILABILITY_LABELS[code],
        "available": code == "in_stock",
    }
    promo = active_promotion_for(store, product)
    out["promotion"] = promotion_info(product, promo) if promo else None
    return out


def _to_decimal(value, field: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ToolInputError(f"{field} deve ser numérico")
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ToolInputError(f"{field} deve ser numérico") from None
    if not number.is_finite() or number < 0:
        raise ToolInputError(f"{field} deve ser um número não negativo")
    return number


def resolve_category(store: DataStore, category: str) -> int | None:
    """Aceita nome oficial ou sinônimo (com/sem acento, singular/plural)."""
    norm = normalize_text(category)
    for cid, cat in store.categories.items():
        if normalize_text(cat.name) == norm:
            return cid
    tokens = tokenize(category)
    hits = {CATEGORY_SYNONYMS[t] for t in tokens if t in CATEGORY_SYNONYMS}
    return hits.pop() if len(hits) == 1 else None


def _query_parts(query: str) -> tuple[set[int], list[str]]:
    """Separa a consulta em categorias (sinônimos) e termos de texto."""
    cats: set[int] = set()
    terms: list[str] = []
    for token in tokenize(query):
        if token in CATEGORY_SYNONYMS:
            cats.add(CATEGORY_SYNONYMS[token])
        elif token not in STOPWORDS:
            terms.append(token)
    return cats, terms


def _is_accessory_query(query: str) -> bool:
    """'cordas' sozinho é acessório; '7 cordas' (com número) é violão de 7 cordas."""
    tokens = tokenize(query)
    return (any(t in ACCESSORY_WORDS for t in tokens)
            and not any(t.isdigit() for t in tokens))


def _matches_text(haystack: str, terms: list[str]) -> bool:
    words = haystack.split()
    joined = haystack.replace(" ", "")
    if len("".join(terms)) >= 4 and "".join(terms) in joined:
        return True  # "gd 20" casa com "GD20"
    for term in terms:
        in_words = any(w == term or (len(term) >= 3 and w.startswith(term)) for w in words)
        if not in_words and not (len(term) >= 3 and term in joined):
            return False
    return True


def _text_match(product: Product, terms: list[str]) -> bool:
    return _matches_text(normalize_text(product.name), terms)


def _description_match(product: Product, terms: list[str]) -> bool:
    text = normalize_text(f"{product.name} {product.description}")
    return _matches_text(text, terms)


def search_products(query: str | None = None, category: str | None = None,
                    price_max=None, price_min=None, available_only: bool = False,
                    sort: str | None = None, limit: int = MAX_RESULTS,
                    *, store: DataStore | None = None) -> dict:
    """Busca por texto/categoria/preço. Retorna found | not_found | ambiguous."""
    store = store or get_store()
    pmax, pmin = _to_decimal(price_max, "price_max"), _to_decimal(price_min, "price_min")
    if pmax is not None and pmin is not None and pmin > pmax:
        raise ToolInputError("price_min não pode ser maior que price_max")
    if sort not in (None, "price_asc", "price_desc"):
        raise ToolInputError("sort deve ser price_asc ou price_desc")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ToolInputError("limit deve ser inteiro positivo")
    limit = min(limit, MAX_RESULTS)

    query = (query or "").strip()
    if query and _is_accessory_query(query):
        return {"status": "not_found", "reason": "out_of_scope_accessory", "query": query,
                "message": "A loja vende somente instrumentos musicais, sem acessórios."}

    cats: set[int] = set()
    terms: list[str] = []
    if query:
        cats, terms = _query_parts(query)
    if category:
        cid = resolve_category(store, category)
        if cid is None:
            return {"status": "error", "reason": "unknown_category", "category": category,
                    "valid_categories": [c.name for c in store.categories.values()]}
        cats = {cid}
    if not cats and not terms and pmax is None and pmin is None:
        raise ToolInputError("Informe ao menos um critério: query, category ou faixa de preço")
    if len(cats) > 1:
        return {"status": "ambiguous", "reason": "multiple_categories",
                "categories": sorted(store.categories[c].name for c in cats)}

    pool = list(store.products.values())
    if cats:
        cid = next(iter(cats))
        pool = [p for p in pool if p.category_id == cid]
        if not pool:
            return {"status": "not_found", "reason": "category_without_products",
                    "category": store.categories[cid].name}
    if pmax is not None:
        pool = [p for p in pool if p.price_brl <= pmax]
    if pmin is not None:
        pool = [p for p in pool if p.price_brl >= pmin]
    if available_only:
        pool = [p for p in pool if is_available(p)]

    match_scope = "filters"
    if terms:
        by_name = [p for p in pool if _text_match(p, terms)]
        if by_name:
            pool, match_scope = by_name, "name"
        else:
            pool = [p for p in pool if _description_match(p, terms)]
            match_scope = "description"

    if not pool:
        return {"status": "not_found", "reason": "no_match", "query": query or None}

    if sort == "price_asc" or (sort is None and (pmax is not None or pmin is not None)):
        pool.sort(key=lambda p: (p.price_brl, p.product_id))
    elif sort == "price_desc":
        pool.sort(key=lambda p: (-p.price_brl, p.product_id))
    else:
        pool.sort(key=lambda p: p.product_id)

    if terms and len(pool) > 1:
        return {"status": "ambiguous", "reason": "multiple_matches", "query": query,
                "match_scope": match_scope, "total_matches": len(pool),
                "candidates": [product_summary(store, p) for p in pool[:MAX_CANDIDATES]]}
    shown = pool[:limit]
    return {"status": "found", "match_scope": match_scope, "total_matches": len(pool),
            "truncated": len(pool) > len(shown),
            "products": [product_summary(store, p) for p in shown]}


def check_product_availability(product_id: int | None = None, name: str | None = None,
                               *, store: DataStore | None = None) -> dict:
    """Distingue: em estoque, ativo sem estoque, descontinuado, em breve, inexistente."""
    store = store or get_store()
    if product_id is None and not (name or "").strip():
        raise ToolInputError("Informe product_id ou name")
    if product_id is not None:
        if isinstance(product_id, bool) or not isinstance(product_id, int):
            raise ToolInputError("product_id deve ser inteiro")
        product = store.products.get(product_id)
        if product is None:
            return {"status": "not_found", "reason": "product_not_found", "product_id": product_id}
        return {"status": "found", "product": product_summary(store, product)}
    result = search_products(query=name, store=store)
    if result["status"] == "found":
        if len(result["products"]) == 1:
            return {"status": "found", "product": result["products"][0]}
        return {"status": "ambiguous", "reason": "multiple_matches", "query": name,
                "total_matches": result["total_matches"], "candidates": result["products"][:MAX_CANDIDATES]}
    return result
