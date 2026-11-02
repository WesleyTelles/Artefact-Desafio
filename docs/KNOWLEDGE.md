# Conhecimento: manual de políticas

Código em `app/knowledge/` (`loader.py`, `retriever.py`, `rules.py`) e ferramentas finas em `app/tools/policies.py`. Análise do manual e inconsistências (I-1 a I-17): `docs/discovery/policy_analysis.md`. A lacuna I-18 (início da contagem do reembolso) foi registrada depois, em `app/knowledge/retriever.py`, e não consta dessa análise inicial.

## Estratégia
Busca lexical (BM25 próprio) por seção, sem embeddings. O manual tem 8 páginas e vocabulário controlado; RAG vetorial traria dependência e ranking opaco sem ganho claro. Cada resultado traz seção, página e score, então a origem é auditável. Regras numéricas ficam em código (`rules.py`), não na busca nem no prompt. Contexto completo no prompt fica como baseline de comparação, não como solução.

## Carga e chunking
- `load_manual()` lê `políticas_da_loja.pdf` da pasta de dados configurada (`EMPORIO_DATA_DIR`, padrão `data/`) com `pypdf` (a extração saiu limpa nas 8 páginas). Se o PDF faltar ou falhar, usa `docs/challenge/politicas_extraido.txt` (fallback registrado em `Manual.source`). Se nem um nem outro existir, o erro diz para colocar o PDF na pasta de dados (`data/` ou `EMPORIO_DATA_DIR`). Os dois textos diferem só em detalhes de grafia (o e-mail do §1.2 aparece com acento no `.txt` e sem acento no PDF).
- 29 trechos, um por subseção (o §7.3 foi dividido em 4 situações). Texto literal, sem cabeçalho/rodapé de página; seção e páginas calculadas pela posição no texto (ex.: §5.2 vai das p.4 a 5).
- Metadados: `section`, `title`, `page_start/end`, `topics`, `aliases` (sinônimos de cliente: devolver, arrependi, parcelar, frete, garantia...), `open_issues` (ids das inconsistências) e `audience` (`internal_procedure` para §7.x, §10 e capa).

## Recuperação
- Normaliza acentos e caixa, remove stopwords, aplica radical simples. Título pesa 3x, apelidos 4x, tópicos 2x; frases-apelido casadas na consulta ganham bônus.
- Devolve até 3 trechos (descarta os abaixo de 45% do melhor). Cada texto é cortado em ~600 caracteres.
- Limiar: `score < 3.0` ou (score `< 7.0` e menos de 50% dos termos cobertos) vira `not_found` com `recommended_action: handoff_to_human`. Score fraco com termos parcialmente cobertos vira `ambiguous` (pedir esclarecimento). Trechos internos pesam 0.8x. Valores calibrados com as 15 perguntas e consultas fora do manual; ajuste no topo de `retriever.py`.
- `notes` traz, em linguagem neutra, avisos de divergência/lacuna do trecho principal. Para defeito, cita §4.2 (30 dias após a compra) e §8.1 (90 dias após o recebimento) e marca `handoff_to_human`. Cancelamento/estorno: aviso de que o manual é omisso. Reembolso (§4.1): aviso I-18 de que os 10 dias úteis não têm marco inicial definido (solicitação? recebimento do produto devolvido?) e de que nenhum início deve ser afirmado; a avaliação real mostrou o LLM completando essa lacuna (R03), o que motivou o aviso e a asserção correspondente (`docs/EVALUATION.md`).
- Trechos são dado (`source_type: policy_manual`). Pedidos tipo "ignore as regras" na consulta são detectados, removidos da busca e sinalizados em `notes`; nada muda nas regras.

## Regras numéricas (`rules.py`)
Parcelamento máximo (§3.1; parcela mínima R$ 80 em 4x-6x e R$ 100 em 7x-12x), combinação de pagamentos (> R$ 2.000), frete (§5.1: grátis acima de R$ 500, R$ 35 abaixo, só região metropolitana), prazo de arrependimento (§4.1) e PIX 5% (não vale para preço promocional). Cada função devolve a fonte e `ambiguity_flags`.
- Igualdade em R$ 500 e R$ 2.000: `not_covered`/`borderline` (I-6, I-7). Parcela abaixo de R$ 50 em até 3x: opção em `unclear_installments` (I-4).
- Arrependimento: data de recebimento = dia 0; até 6 dias `within_deadline`, 7 dias `borderline`, mais que isso `outside_deadline`. Data só estimada ganha margem de 2 dias. Data de referência é injetável (`today`). Canal não online ou desconhecido sinaliza I-11.

## Ferramentas
`search_store_policies`, `check_installments`, `check_shipping`, `check_return_eligibility`, `check_pix_discount`, registradas em `app/tools/registry.py` e executadas por `execute()` (nunca levantam).

## Limitações
- Busca lexical: vocabulário fora dos aliases pode falhar; consultas curtas e genéricas ("tempo") podem casar mal.
- Divergências e lacunas são apenas sinalizadas; a decisão fica com atendente humano.
- O manual é interno; a decisão de citar seção/página ao cliente é da camada de conversa.
- Sem regra para compra presencial, cancelamento, municípios da região metropolitana ou marco dos dias úteis (inclusive o do reembolso, I-18).
- O manual é material da Artefact marcado como uso restrito; a distribuição do PDF e do texto extraído depende de autorização (`docs/PUBLICACAO.md`).
