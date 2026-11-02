"""Audita os produtos dos CSVs e gera docs/DATA_QUALITY.md.

Uso: .venv/Scripts/python scripts/audit_products.py [--check] [--stdout]
  --check   não escreve; sai com 1 se o documento estiver desatualizado
  --stdout  imprime o Markdown em vez de gravar

Somente leitura sobre data/; nunca altera os CSVs.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.data.loader import load_data  # noqa: E402
from app.data.quality import (HIGH, KIND_IMPACT, KIND_TREATMENT, LOW, MEDIUM,  # noqa: E402
                              Finding, audit_store, count_by)

DOC = ROOT / "docs" / "DATA_QUALITY.md"

# casos apontados pela revisão independente: (id, tipo esperado, trecho esperado, alegação)
CITED = [
    (135, "brand_mismatch", "Fender", 'nome "Music Man Bass 1X" × descrição "Fender Jazz Bass"'),
    (139, "brand_mismatch", "Pearl", 'nome "Yamaha Kit 1" × descrição "Pearl Export"'),
    (137, "count_mismatch", "5 cordas", "descrição diz 5 cordas × specs strings=4"),
    (142, "count_mismatch", "88 teclas", "descrição diz 88 teclas × specs keys=61"),
]

SEVERITY_CRITERIA = """\
| Gravidade | Critério (explícito) | Tipos |
|---|---|---|
| alta | Contradição em atributo que o cliente usa para decidir a compra: identidade do produto, quantidade de cordas/teclas/peças, tipo/tamanho do instrumento, material das cordas, eletrônica | brand_mismatch, count_mismatch, category_mismatch, size_mismatch, strings_material_mismatch, electronics_mismatch (captação) |
| média | Contradição em atributo secundário (madeira, cor, modelo associado a outra marca) ou falta de ficha/descrição inteira | material_mismatch, color_mismatch, model_hint_mismatch, specs_missing, description_empty |
| baixa | Lacuna pontual, indício fraco ou incoerência sem efeito sobre a venda | specs_key_missing, specs_empty_value, price_outlier, stock_status_inconsistent, electronics_mismatch (só 'afinador') |"""

CHECKS = [
    ("count_mismatch", "nº de cordas, teclas e peças: descrição × nome × specs"),
    ("brand_mismatch", "marcas do léxico citadas na descrição e ausentes do nome"),
    ("model_hint_mismatch", "modelos do léxico (ex.: Precision, Export) associados a outra marca"),
    ("category_mismatch", "substantivo inicial da descrição/nome × category_id"),
    ("size_mismatch", "soprano/concert/tenor/barítono × escala em mm"),
    ("strings_material_mismatch", "nylon/aço: descrição × nome × specs.strings"),
    ("electronics_mismatch", "captação/eletrônica/'Elétrico' × specs.electronics (violões e ukuleles)"),
    ("material_mismatch", "madeira de corpo/tampo/fundo/cascos/braço na descrição × specs"),
    ("color_mismatch", "cor no nome/descrição × specs.color"),
    ("specs_missing", "specs vazio"),
    ("description_empty", "descrição vazia"),
    ("specs_key_missing", "chave presente em ≥50% da categoria e ausente no produto"),
    ("specs_empty_value", "valor vazio em specs"),
    ("price_outlier", "preço fora de [Q1/5, Q3×5] dos demais da categoria (categorias com ≥6 produtos)"),
    ("stock_status_inconsistent", "estoque > 0 em produto discontinued/coming_soon"),
]

NOT_VERIFIED = """\
- **Verdade externa**: o script só compara campos entre si. Não sabe qual valor é o correto e não consulta catálogos de fabricantes.
- **Léxicos manuais**: marcas, modelos e madeiras vêm de listas curtas em `app/data/quality.py`. Marca ou madeira fora da lista não é detectada; o léxico de modelos (ex.: Precision = Fender) é conhecimento externo aos dados e só gera gravidade média.
- **Atributos sem segunda fonte**: nº de captadores (ex.: id 145 "3 captadores"), de trastes, de bandas do equalizador, afinação, polifonia, ferragens e escala em violões. Existem só no texto ou só em specs; não há contra o que comparar. A ferramenta os entrega como `unverifiable` ou `other_specs_not_cross_checked`.
- **Nº de cordas em violões e ukuleles**: specs.strings guarda o material (nylon/steel), não a quantidade; só nome/descrição ("7 Cordas") informam. Sem número, o atributo é `absent`.
- **Tipo vs descrição fina**: ex.: o id 143 é descrito como "Piano de palco" e specs.type é Synthesizer; o auditor não distingue piano de sintetizador.
- **Preços e estoques**: só incoerência estrutural e atipicidade estatística; não se sabe se o preço está certo.
- **Contradição dentro do mesmo texto** e ortografia.
- **Outras tabelas**: clientes, pedidos e promoções não são auditados aqui (ver `docs/DATA.md`). Os totais de pedido divergentes dos itens (pedidos 3 e 20) já estão documentados lá."""


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def render(findings: list[Finding], total_products: int) -> str:
    counts = count_by(findings)
    sev = {s: sum(1 for f in findings if f.severity == s) for s in (HIGH, MEDIUM, LOW)}
    affected = {f.product_id for f in findings}
    flagged = sorted({f.product_id for f in findings
                      if f.severity in (HIGH, MEDIUM) and f.customer_facing})
    out = [
        "# Qualidade dos dados de produtos", "",
        "> Gerado por `scripts/audit_products.py` (regras em `app/data/quality.py`). Não editar à "
        "mão: rode o script para atualizar. Os CSVs em `data/` nunca são alterados.", "",
        "## O que o auditor faz", "",
        "Varre **todos** os produtos e compara, para o mesmo produto, nome × descrição × `specs` "
        "(e, para estoque/preço, o catálogo). Relata onde dois campos **não concordam**, "
        "**sem escolher qual é o verdadeiro**. Os mesmos extratores alimentam as ferramentas do "
        "agente (`data_conflicts`): o aviso que o agente recebe é o que está listado aqui.", "",
        f"Resumo: {total_products} produtos varridos; {len(findings)} achados em "
        f"{len(affected)} produtos ({sev[HIGH]} alta, {sev[MEDIUM]} média, {sev[LOW]} baixa). "
        f"Produtos com conflito sinalizado ao agente (alta/média, voltado ao cliente): "
        f"{len(flagged)} (ids {', '.join(map(str, flagged))}).", "",
        "## Critério de gravidade", "", SEVERITY_CRITERIA, "",
        "## Contagem por tipo", "",
        "| Tipo | Verificação | Alta | Média | Baixa | Total |", "|---|---|---|---|---|---|",
    ]
    for kind, what in CHECKS:
        row = counts.get(kind, {HIGH: 0, MEDIUM: 0, LOW: 0})
        out.append(f"| {kind} | {_cell(what)} | {row[HIGH]} | {row[MEDIUM]} | {row[LOW]} | "
                   f"{sum(row.values())} |")
    out.append(f"| **Total** | | **{sev[HIGH]}** | **{sev[MEDIUM]}** | **{sev[LOW]}** | "
               f"**{len(findings)}** |")
    out += ["", "Tipos com 0 ocorrências foram verificados e não encontraram nada.", "",
            "## Achados", "",
            "| ID | Campo da descrição / texto | Campo estruturado | Tipo | Gravidade | "
            "Impacto potencial | Tratamento recomendado |",
            "|---|---|---|---|---|---|---|"]
    for f in findings:
        out.append(f"| {f.product_id} | {_cell(f.description_says)} | {_cell(f.structured_says)} "
                   f"({f.compared_with}) | {f.kind} | {f.severity} | {_cell(KIND_IMPACT[f.kind])} "
                   f"| {_cell(KIND_TREATMENT[f.kind])} |")
    out += ["", "## Casos citados na revisão independente", "",
            "| ID | Alegação | Resultado do script |", "|---|---|---|"]
    for pid, kind, snippet, claim in CITED:
        hit = any(f.product_id == pid and f.kind == kind and snippet in f.description_says
                  for f in findings)
        verdict = "**Real**: comprovado pelo script" if hit else "**Não confirmado** pelo script"
        out.append(f"| {pid} | {_cell(claim)} | {verdict} |")
    out += ["", "Conferência manual nas linhas de `products.csv`: os valores de `name`, `description` "
            "e `specs` dos ids acima batem com o que a tabela afirma.", "",
            "## Tratamento no agente", "",
            "- `search_products` e `check_product_availability` devolvem `data_conflicts` "
            "(`field`, `description_says`, `specs_say`, `severity`) e uma `note` instruindo o LLM "
            "a não afirmar o ponto e a encaminhar a um atendente.",
            "- Com um único produto no resultado há `details`: descrição truncada e cada atributo "
            "como `confirmed`, `absent` (valor `unknown`), `contradictory` ou `unverifiable`.",
            "- Busca que casou só pela descrição traz `matched_on: description`, "
            "`query_terms_not_in_name` e `match_warning`.",
            "- Nada é corrigido na base: o agente apenas deixa de afirmar o que a base não sustenta.",
            "", "## O que NÃO foi verificado", "", NOT_VERIFIED, ""]
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    store = load_data()
    findings = audit_store(store)
    text = render(findings, len(store.products))
    if args.stdout:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
        return 0
    if args.check:
        current = DOC.read_text(encoding="utf-8") if DOC.exists() else ""
        if current != text:
            print("docs/DATA_QUALITY.md desatualizado; rode scripts/audit_products.py")
            return 1
        return 0
    DOC.write_text(text, encoding="utf-8", newline="\n")
    print(f"{len(findings)} achados em {len({f.product_id for f in findings})} produtos -> {DOC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
