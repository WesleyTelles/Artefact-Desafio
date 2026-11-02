# Dados e ferramentas determinísticas

Perfil completo dos CSVs: `docs/discovery/data_profile.md`. Aqui ficam as decisões de implementação (fase 2).

## Carga
- `app/data/loader.py` lê os 6 CSVs (`data/desafio_tecnico_ai_eng - <tabela>.csv`) com `csv` da stdlib, em memória. Dados pequenos e somente leitura: pandas e SQLite não agregam valor. Originais nunca são alterados.
- Pasta configurável por `EMPORIO_DATA_DIR` (`app/core/config.py`); sem segredos.
- Valores monetários em `Decimal` (o CSV mistura `849`, `599.9`); arredondamento a 2 casas com `ROUND_HALF_UP`.
- Valida colunas, tipos, status, ids duplicados e integridade referencial (produto→categoria, pedido→cliente, item→pedido/produto, promoção→produto). Qualquer falha levanta `DataError` com arquivo e linha.

## Regras
- **Disponível** = `status == 'active'` e `stock_quantity > 0`. Estados: `in_stock`, `out_of_stock` (ativo sem estoque, ex.: 96), `discontinued` (113, 136; 136 tem estoque 13 mas não é vendável), `coming_soon` (130), e produto inexistente (`not_found`).
- **Promoção**: só `is_active=1` e produto `active`; sem acúmulo (vale a maior). Retorna preço original, %, preço promocional e `pix_discount_applies: false` (manual §6.2). Não há desconto PIX calculado em lugar nenhum.
- **Busca**: normaliza acentos/caixa/pontuação ("gd-20" casa com "GD20"). Palavras de categoria (violão, guitarra, baixo, bateria, teclado/piano, ukulele, sax, flauta...) viram filtro de categoria, não texto, o que evita trazer o ukulele 128 (cuja descrição cita "violão"). O texto casa com o nome; só se nada casar, tenta a descrição. Com texto e mais de um resultado, retorna `ambiguous` com candidatos ("Yamaha" → 10). Só filtros (categoria/preço) retornam lista `found`.
- **Acessórios**: "cordas", "palhetas", "cabos", "cases", "pedais" etc. sem número na consulta → `not_found` com `out_of_scope_accessory` (a loja só vende instrumentos). Com número ("7 cordas") é busca de produto.
- Categorias sem produtos (sopro, cordas orquestrais) → `not_found` com `category_without_products`.

## Detalhes de produto e qualidade dos dados
Auditor determinístico em `app/data/quality.py` (relatório gerado por `scripts/audit_products.py` em `docs/DATA_QUALITY.md`). Ele compara nome × descrição × `specs` do mesmo produto e não decide qual campo é o verdadeiro.
- `check_product_availability` (por id ou nome) e `search_products` com um único resultado devolvem `details`: descrição truncada em 240 caracteres, `attributes` e `other_specs_not_cross_checked`. Cada atributo vem com `status`: `confirmed` (specs sem contradição, ou nome e descrição concordam), `unverifiable` (só uma fonte em texto livre), `contradictory` (fontes discordam; valor `unknown`) ou `absent` (não existe nos dados; valor `unknown`, nunca completado).
- Divergências relevantes ao cliente (gravidade alta ou média) saem em `data_conflicts` (`field`, `type`, `severity`, `description_says`, `specs_say`, `compared_with`) e em `note`, que instrui o LLM a não afirmar o ponto e a encaminhar a um atendente. Listas e candidatos ambíguos trazem só `data_conflicts` (sem `details`) para não inflar o contexto.
- Cada produto de busca com texto traz `matched_on` (`name` ou `description`). Se casou só pela descrição, vêm também `query_terms_not_in_name` e `match_warning`, para não confirmar "Fender Jazz Bass" num "Music Man Bass 1X".
- Estados `found`, `not_found`, `ambiguous` e `error` não mudaram; os campos novos são aditivos.

## Dados originais x sintéticos
Os seis CSVs e o PDF em `data/` são a base **fornecida pelo desafio** (loja fictícia). **Não há dados sintéticos** no projeto: nada foi gerado, completado ou corrigido. O auditor e os testes só leem; `tests/test_quality.py` confere o SHA-256 dos CSVs.

Contagens conferidas contra os CSVs carregados: 65 produtos (ids 81 a 145), 9 categorias, 50 clientes, 20 pedidos, 22 itens de pedido, 25 promoções (4 ativas).

## Confiabilidade por campo
| Campo | Confiança | Observação |
|---|---|---|
| `price_brl`, `stock_quantity`, `status` | Fonte de verdade para preço/estoque/disponibilidade | Valores só em código; estoque de `discontinued` (136) e `coming_soon` (130) é ignorado pela regra de disponibilidade |
| `name` | Identifica o produto | Em divergência com a descrição (ids 135, 137, 139, 140, 142, 144) o agente só identifica o produto pelo nome; não se afirma qual dos dois está certo |
| `description` | Texto livre, **não confiável para fatos** | Diverge do nome/specs em 7 produtos; só é citada quando não há conflito |
| `specs` | Estruturado, preferível à descrição, mas não infalível | Chaves variam por categoria; nem toda característica existe; também pode divergir do nome |
| `category_id` | Confiável (nenhuma incoerência achada) | Validado contra `categories.csv` e contra o substantivo inicial da descrição |
| pedidos, clientes, promoções | Ver `docs/discovery/data_profile.md` | Totais dos pedidos 3 e 20 divergem dos itens; e-mail não é único (11 e 43) |

## Validações implementadas
- Na carga (`app/data/loader.py`): colunas, tipos, status, ids duplicados, integridade referencial, JSON de `specs`; falha levanta `DataError` com arquivo e linha.
- Na qualidade (`app/data/quality.py`): contradição de nº de cordas/teclas/peças, marca e modelo, madeira, cor, material das cordas, eletrônica e tamanho do ukulele; categoria incoerente; specs ausente/vazio; descrição vazia; preço atípico; estoque incoerente com status.
- Resultado atual: 15 achados em 9 produtos (8 alta, 4 média, 3 baixa); detalhes, critérios e o que não foi verificado em `docs/DATA_QUALITY.md`.

## Pedidos e privacidade
- `get_order_status` exige `order_id` e verificação (e-mail ou telefone completo, comparação normalizada) do cliente **daquele pedido**. Pedido inexistente e verificação errada devolvem exatamente a mesma resposta (`verification_failed`). Verificação ausente → `verification_required` (nada revelado).
- E-mail não é identificador único (clientes 11 e 43), por isso a verificação é sempre contra o cliente do pedido, nunca uma busca por e-mail.
- Resposta traz status em pt-BR, pagamento rotulado, `total_brl` **registrado** (pedidos 3 e 20 divergem da soma dos itens, não recalculado), itens, rastreio/previsão só se existirem e `notes`. Contato do cliente só mascarado (`p***@dominio`, `(67) *****-1098`); nome, e-mail e telefone completos nunca saem.
- Não existe busca de cliente exposta como ferramenta.

## Ferramentas (`app/tools/registry.py`)
`search_products`, `check_product_availability`, `get_promotions`, `get_order_status`, `get_store_info` (e as de política/frete/parcelamento, ver `docs/KNOWLEDGE.md`), cada uma com descrição e JSON schema. `execute(name, args)` valida os argumentos, captura qualquer exceção e devolve `{"status": "error", "reason": ...}`. Nunca levanta. Mensagens de erro não expõem detalhes internos.

`get_store_info` traz só o confirmado no manual v2.1, com seção e página. Os dois telefones divergentes ((67) 3341-4444 no §1.2/capa e WhatsApp (67) 3321-4500 no §7) estão marcados `to_confirm`.

## Limitações
- Frete, parcelamento e política não são tratados nesta camada; ver `docs/KNOWLEDGE.md` (fase 3).
- Divergências entre nome, descrição e specs existem na base (7 produtos com conflito relevante ao cliente: ids 135, 136, 137, 139, 140, 142, 144). O agente as detecta e sinaliza, mas não as corrige; ver `docs/DATA_QUALITY.md`.
- Atributos sem segunda fonte (nº de captadores, trastes, afinação etc.) são entregues como `unverifiable` ou `other_specs_not_cross_checked`. O nº de cordas de violões e ukuleles não existe em specs (só o material), então vira `unknown` salvo quando nome e descrição concordam ("7 Cordas").
- Os léxicos do auditor (marcas, madeiras, modelos) são listas manuais curtas; marca fora da lista não é detectada.
- `delivered` em pedidos: a base só tem a previsão de entrega, não a data efetiva; a ferramenta avisa isso ao LLM.
- Sem data de vigência nas promoções: "ativa" é a flag.
- Sinônimos de categoria são uma lista fixa; termos fora dela só casam por nome/descrição.
- A busca por descrição é um fallback e pode ser menos precisa.

## Testes
`pytest` cobre os casos de aceite, incluindo CSV corrompido em `tmp_path`. `tests/test_quality.py` cobre o auditor (casos 135, 137, 139, 142), atributos `confirmed/absent/contradictory/unverifiable`, produto sem specs, produto sem conflito, `matched_on`, limite de tamanho do payload e SHA-256 dos CSVs. Para regenerar o relatório: `.venv/Scripts/python scripts/audit_products.py` (`--check` falha se estiver desatualizado).

Relatório de qualidade: [`docs/DATA_QUALITY.md`](DATA_QUALITY.md).
