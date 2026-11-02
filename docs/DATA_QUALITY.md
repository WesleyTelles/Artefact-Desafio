# Qualidade dos dados de produtos

> Gerado por `scripts/audit_products.py` (regras em `app/data/quality.py`). Não editar à mão: rode o script para atualizar. Os CSVs em `data/` nunca são alterados.

## O que o auditor faz

Varre **todos** os produtos e compara, para o mesmo produto, nome × descrição × `specs` (e, para estoque/preço, o catálogo). Relata onde dois campos **não concordam**, **sem escolher qual é o verdadeiro**. Os mesmos extratores alimentam as ferramentas do agente (`data_conflicts`): o aviso que o agente recebe é o que está listado aqui.

Resumo: 65 produtos varridos; 15 achados em 9 produtos (8 alta, 4 média, 3 baixa). Produtos com conflito sinalizado ao agente (alta/média, voltado ao cliente): 7 (ids 135, 136, 137, 139, 140, 142, 144).

## Critério de gravidade

| Gravidade | Critério (explícito) | Tipos |
|---|---|---|
| alta | Contradição em atributo que o cliente usa para decidir a compra: identidade do produto, quantidade de cordas/teclas/peças, tipo/tamanho do instrumento, material das cordas, eletrônica | brand_mismatch, count_mismatch, category_mismatch, size_mismatch, strings_material_mismatch, electronics_mismatch (captação) |
| média | Contradição em atributo secundário (madeira, cor, modelo associado a outra marca) ou falta de ficha/descrição inteira | material_mismatch, color_mismatch, model_hint_mismatch, specs_missing, description_empty |
| baixa | Lacuna pontual, indício fraco ou incoerência sem efeito sobre a venda | specs_key_missing, specs_empty_value, price_outlier, stock_status_inconsistent, electronics_mismatch (só 'afinador') |

## Contagem por tipo

| Tipo | Verificação | Alta | Média | Baixa | Total |
|---|---|---|---|---|---|
| count_mismatch | nº de cordas, teclas e peças: descrição × nome × specs | 2 | 0 | 0 | 2 |
| brand_mismatch | marcas do léxico citadas na descrição e ausentes do nome | 6 | 0 | 0 | 6 |
| model_hint_mismatch | modelos do léxico (ex.: Precision, Export) associados a outra marca | 0 | 1 | 0 | 1 |
| category_mismatch | substantivo inicial da descrição/nome × category_id | 0 | 0 | 0 | 0 |
| size_mismatch | soprano/concert/tenor/barítono × escala em mm | 0 | 0 | 0 | 0 |
| strings_material_mismatch | nylon/aço: descrição × nome × specs.strings | 0 | 0 | 0 | 0 |
| electronics_mismatch | captação/eletrônica/'Elétrico' × specs.electronics (violões e ukuleles) | 0 | 0 | 1 | 1 |
| material_mismatch | madeira de corpo/tampo/fundo/cascos/braço na descrição × specs | 0 | 3 | 0 | 3 |
| color_mismatch | cor no nome/descrição × specs.color | 0 | 0 | 0 | 0 |
| specs_missing | specs vazio | 0 | 0 | 0 | 0 |
| description_empty | descrição vazia | 0 | 0 | 0 | 0 |
| specs_key_missing | chave presente em ≥50% da categoria e ausente no produto | 0 | 0 | 0 | 0 |
| specs_empty_value | valor vazio em specs | 0 | 0 | 0 | 0 |
| price_outlier | preço fora de [Q1/5, Q3×5] dos demais da categoria (categorias com ≥6 produtos) | 0 | 0 | 0 | 0 |
| stock_status_inconsistent | estoque > 0 em produto discontinued/coming_soon | 0 | 0 | 2 | 2 |
| **Total** | | **8** | **4** | **3** | **15** |

Tipos com 0 ocorrências foram verificados e não encontraram nada.

## Achados

| ID | Campo da descrição / texto | Campo estruturado | Tipo | Gravidade | Impacto potencial | Tratamento recomendado |
|---|---|---|---|---|---|---|
| 86 | cita afinador integrado | electronics=no (specs) | electronics_mismatch | baixa | O agente pode afirmar que o instrumento é (ou não é) eletroacústico sem base. | Não afirmar se é eletroacústico; confirmar com atendente. |
| 130 | estoque 2 | status=coming_soon (catalog) | stock_status_inconsistent | baixa | Estoque sem efeito prático; o status manda (já tratado em availability). | Nenhum: disponibilidade já segue o status. |
| 135 | marca na descrição: Fender | marca no nome: Music Man (name) | brand_mismatch | alta | O agente pode confirmar marca/modelo que não é a do produto vendido pelo nome. | Usar só o nome como identificação; não repetir a marca/modelo da descrição; corrigir a base. |
| 135 | corpo em alder e dois captadores single coil | body=Ash (specs) | material_mismatch | média | Informação de madeira/acabamento pode estar errada; afeta valor percebido. | Não afirmar a madeira; informar só o que não diverge. |
| 136 | modelo 'precision' (associado à Fender) | marca no nome: Ibanez (name) | model_hint_mismatch | média | A descrição cita um modelo de outra marca; risco de confirmar o modelo errado. | Tratar como suspeita (léxico externo); não citar o modelo da descrição. |
| 136 | estoque 13 | status=discontinued (catalog) | stock_status_inconsistent | baixa | Estoque sem efeito prático; o status manda (já tratado em availability). | Nenhum: disponibilidade já segue o status. |
| 137 | marca na descrição: Ibanez | marca no nome: Yamaha (name) | brand_mismatch | alta | O agente pode confirmar marca/modelo que não é a do produto vendido pelo nome. | Usar só o nome como identificação; não repetir a marca/modelo da descrição; corrigir a base. |
| 137 | 5 cordas | strings=4 (specs) | count_mismatch | alta | O agente pode informar um número errado de cordas/teclas/peças e levar a compra do produto errado. | Não afirmar; sinalizar conflito e encaminhar a atendente; corrigir a base na origem. |
| 139 | marca na descrição: Pearl | marca no nome: Yamaha (name) | brand_mismatch | alta | O agente pode confirmar marca/modelo que não é a do produto vendido pelo nome. | Usar só o nome como identificação; não repetir a marca/modelo da descrição; corrigir a base. |
| 139 | cascos em poplar e mogno asiatico | shells=Maple (specs) | material_mismatch | média | Informação de madeira/acabamento pode estar errada; afeta valor percebido. | Não afirmar a madeira; informar só o que não diverge. |
| 140 | marca na descrição: Tama | marca no nome: Pearl (name) | brand_mismatch | alta | O agente pode confirmar marca/modelo que não é a do produto vendido pelo nome. | Usar só o nome como identificação; não repetir a marca/modelo da descrição; corrigir a base. |
| 140 | cascos 100 birch e | shells=Maple (specs) | material_mismatch | média | Informação de madeira/acabamento pode estar errada; afeta valor percebido. | Não afirmar a madeira; informar só o que não diverge. |
| 142 | marca na descrição: Roland | marca no nome: Korg (name) | brand_mismatch | alta | O agente pode confirmar marca/modelo que não é a do produto vendido pelo nome. | Usar só o nome como identificação; não repetir a marca/modelo da descrição; corrigir a base. |
| 142 | 88 teclas | keys=61 (specs) | count_mismatch | alta | O agente pode informar um número errado de cordas/teclas/peças e levar a compra do produto errado. | Não afirmar; sinalizar conflito e encaminhar a atendente; corrigir a base na origem. |
| 144 | marca na descrição: Yamaha | marca no nome: Roland (name) | brand_mismatch | alta | O agente pode confirmar marca/modelo que não é a do produto vendido pelo nome. | Usar só o nome como identificação; não repetir a marca/modelo da descrição; corrigir a base. |

## Casos citados na revisão independente

| ID | Alegação | Resultado do script |
|---|---|---|
| 135 | nome "Music Man Bass 1X" × descrição "Fender Jazz Bass" | **Real**: comprovado pelo script |
| 139 | nome "Yamaha Kit 1" × descrição "Pearl Export" | **Real**: comprovado pelo script |
| 137 | descrição diz 5 cordas × specs strings=4 | **Real**: comprovado pelo script |
| 142 | descrição diz 88 teclas × specs keys=61 | **Real**: comprovado pelo script |

Conferência manual nas linhas de `products.csv`: os valores de `name`, `description` e `specs` dos ids acima batem com o que a tabela afirma.

## Tratamento no agente

- `search_products` e `check_product_availability` devolvem `data_conflicts` (`field`, `description_says`, `specs_say`, `severity`) e uma `note` instruindo o LLM a não afirmar o ponto e a encaminhar a um atendente.
- Com um único produto no resultado há `details`: descrição truncada e cada atributo como `confirmed`, `absent` (valor `unknown`), `contradictory` ou `unverifiable`.
- Busca que casou só pela descrição traz `matched_on: description`, `query_terms_not_in_name` e `match_warning`.
- Nada é corrigido na base: o agente apenas deixa de afirmar o que a base não sustenta.

## O que NÃO foi verificado

- **Verdade externa**: o script só compara campos entre si. Não sabe qual valor é o correto e não consulta catálogos de fabricantes.
- **Léxicos manuais**: marcas, modelos e madeiras vêm de listas curtas em `app/data/quality.py`. Marca ou madeira fora da lista não é detectada; o léxico de modelos (ex.: Precision = Fender) é conhecimento externo aos dados e só gera gravidade média.
- **Atributos sem segunda fonte**: nº de captadores (ex.: id 145 "3 captadores"), de trastes, de bandas do equalizador, afinação, polifonia, ferragens e escala em violões. Existem só no texto ou só em specs; não há contra o que comparar. A ferramenta os entrega como `unverifiable` ou `other_specs_not_cross_checked`.
- **Nº de cordas em violões e ukuleles**: specs.strings guarda o material (nylon/steel), não a quantidade; só nome/descrição ("7 Cordas") informam. Sem número, o atributo é `absent`.
- **Tipo vs descrição fina**: ex.: o id 143 é descrito como "Piano de palco" e specs.type é Synthesizer; o auditor não distingue piano de sintetizador.
- **Preços e estoques**: só incoerência estrutural e atipicidade estatística; não se sabe se o preço está certo.
- **Contradição dentro do mesmo texto** e ortografia.
- **Outras tabelas**: clientes, pedidos e promoções não são auditados aqui (ver `docs/DATA.md`). Os totais de pedido divergentes dos itens (pedidos 3 e 20) já estão documentados lá.
