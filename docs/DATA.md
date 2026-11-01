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

## Pedidos e privacidade
- `get_order_status` exige `order_id` e verificação (e-mail ou telefone completo, comparação normalizada) do cliente **daquele pedido**. Pedido inexistente e verificação errada devolvem exatamente a mesma resposta (`verification_failed`). Verificação ausente → `verification_required` (nada revelado).
- E-mail não é identificador único (clientes 11 e 43), por isso a verificação é sempre contra o cliente do pedido, nunca uma busca por e-mail.
- Resposta traz status em pt-BR, pagamento rotulado, `total_brl` **registrado** (pedidos 3 e 20 divergem da soma dos itens, não recalculado), itens, rastreio/previsão só se existirem e `notes`. Contato do cliente só mascarado (`p***@dominio`, `(67) *****-1098`); nome, e-mail e telefone completos nunca saem.
- Não existe busca de cliente exposta como ferramenta.

## Ferramentas (`app/tools/registry.py`)
`search_products`, `check_product_availability`, `get_promotions`, `get_order_status`, `get_store_info`, cada uma com descrição e JSON schema. `execute(name, args)` valida os argumentos, captura qualquer exceção e devolve `{"status": "error", "reason": ...}`. Nunca levanta. Mensagens de erro não expõem detalhes internos.

`get_store_info` traz só o confirmado no manual v2.1, com seção e página. Os dois telefones divergentes ((67) 3341-4444 no §1.2/capa e WhatsApp (67) 3321-4500 no §7) estão marcados `to_confirm`.

## Limitações
- Sem frete, parcelamento nem política: fora do escopo desta fase.
- Sem data de vigência nas promoções: "ativa" é a flag.
- Sinônimos de categoria são uma lista fixa; termos fora dela só casam por nome/descrição.
- A busca por descrição é um fallback e pode ser menos precisa.

## Testes
`pytest` (63 testes) cobre os casos de aceite, incluindo CSV corrompido em `tmp_path`.
