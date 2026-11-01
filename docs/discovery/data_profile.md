# Data profile (Discovery) - Empório da Música

Gerado com Python stdlib (`csv`, `json`), UTF-8 (sem BOM). Originais não alterados. Arquivos: `data/desafio_tecnico_ai_eng - <nome>.csv`.

## 1. Volumes, colunas e nulos
| Arquivo | Linhas | Colunas | Vazios |
|---|---|---|---|
| categories | 9 | category_id, name, description | 0 |
| products | 65 (ids 81-145) | product_id, price_brl, name, category_id, description, stock_quantity, status, specs (JSON em texto), created_at | 0 |
| customers | 50 | customer_id, name, phone, email, city | 0 |
| orders | 20 | order_id, customer_id, order_date, status, total_brl, payment_method, tracking_code, estimated_delivery, notes | tracking 12, estimated_delivery 12, notes 16 (esperado) |
| order_items | 22 | order_id, quantity, product_id (sem preço unitário) | 0 |
| promotions | 25 | promotion_id, product_id, discount_percent, description, is_active | 0 |

Tipos: ids/quantity/stock inteiros; price_brl/total_brl decimais, às vezes inteiros sem ".00" (`849`, `599.9`) -> usar Decimal; datas ISO; is_active 0/1. Pedidos: 2025-10-15 a 2026-03-22. products.created_at: 2020-02-28 a 2025-05-15.

## 2. Catálogo vs política
- Catálogo tem **65 produtos**; a política diz "mais de 300". Não repetir o número 300.
- Categorias **6, 7, 8 (Sopro Madeiras, Sopro Metais, Cordas Orquestrais) têm 0 produtos**, embora a política diga que a loja vende sopro e cordas orquestrais.
- Distribuição: Violões (5)=35, Ukuleles (9)=15, Guitarras (1)=5, Baixos (2)=4, Baterias (3)=3, Teclados (4)=3.
- Não há acessórios no catálogo (política: loja não vende cordas, palhetas, cabos, cases, pedais, amplificadores). Falso positivo: "Cordas" aparece em nomes de violões de 7 cordas (ids 109-113) e na categoria "Cordas Orquestrais". Tratar escopo/acessório antes da busca.
- Nomes de produtos: **sem duplicatas** (normalizado sem acento/caixa/espaços).
- specs: 65/65 JSON válido. Chaves variam: cordas (top, back_sides, neck, strings, scale, electronics, color; 50), guitarras/baixos (body, neck, strings, color; 9), baterias (shells, pieces, hardware, color; 3), teclados (keys, type, polyphony...; 3). Tratar como dict opcional.
- Preço de 159.9 a 19567; nenhum <=0. Nenhum texto com instruções/prompt injection encontrado.

## 3. Status e estoque
- status: `active` 62, `discontinued` 2, `coming_soon` 1.
- Não-active: **113** Shelby SN-7C 7 Cordas (discontinued, estoque 0); **136** Ibanez Bass 2X Electric Bass (discontinued, estoque 13); **130** Kala KA-ABP-CTG Barítono Cedar (coming_soon, estoque 2).
- Estoque 0: **96** Giannini GF-3D Dreadnought Sunburst (status `active` mas estoque 0) e 113.
- Disponível = `status=='active' AND stock_quantity>0` -> 61 produtos.
- Produto 130 (coming_soon) consta em pedidos 3 e 14.

## 4. Integridade referencial
Íntegra: products->categories, orders->customers, order_items->orders, order_items->products, promotions->products: 0 órfãos. Todos os 20 pedidos têm >=1 item. Sem duplicata (order_id, product_id). quantity: 21 itens com 1, 1 com 2 (pedido 3).
- Clientes: 50; só 18 têm pedidos (19-50 sem pedidos). Cliente 3 e 7 têm 2 pedidos.
- **Email duplicado**: `bruno.martins@jmail.com` em clientes 11 (Bruno Carvalho Martins) e 43 (Bruno Martins). Email não é identificador único. Telefones e nomes completos são únicos.
- Primeiros nomes repetidos (Thiago, Camila, Bruno x3; Lucas, Ana, Pedro, Mariana, Rafael... x2): busca por primeiro nome é ambígua.
- Cidades: Campo Grande 24, Dourados 7, Três Lagoas 7, Corumbá 6, Ponta Porã 6.

## 5. Pedidos
- status: delivered 7, confirmed 4, pending 4, cancelled 4, shipped 1.
- payment_method (cru): pix 5, credit_12x 4, credit_6x 3, credit_3x 3, boleto 3, debit 2 -> mapear para rótulos pt-BR.
- tracking_code/estimated_delivery só em delivered (7) e shipped (1); formato `BR[A-Z0-9]{9}BR` válido e único. confirmed/pending/cancelled sem rastreio: não inventar prazo. Não há data de entrega efetiva.
- notes (só os 4 cancelled): cancelado pelo cliente antes do processamento; item fora de estoque no momento do pedido; pagamento não confirmado no prazo; endereço de entrega inválido.
- **total_brl vs soma(preço atual x qty)**: 18/20 batem exatamente. Divergências: **pedido 3** (cliente 12, delivered, 2x prod 130 a 1749): soma 3498, total 3450 (-48); **pedido 20** (cancelled, prods 107+84): soma 1488, total 1400 (-88). Nenhuma promoção (ativa ou inativa) explica. Sem preço unitário em order_items; preço atual pode diferir do histórico. Mostrar `total_brl` registrado, não recalcular.
- Pedidos PIX (1, 5, 10, 13, 17) estão a preço de tabela: **nenhum aplica o desconto PIX de 5%** da política. total_brl aparentemente não inclui frete.
- Parcelamento vs política (parcela mínima R$80 para 4-6x, R$100 para 7-12x): violam pedidos **9** (349.9 em 6x = 58.32), **16** (429.9 em 6x = 71.65), **18** (459.9 em 12x = 38.32). Dados de exemplo inconsistentes com a política; não usar como evidência de regra.

## 6. Promoções
- 25 linhas, **4 ativas** (is_active=1): #12 prod 127 Kalani KAL-700T Tenor 10% (359, estoque 11); #14 prod 121 Ohana CK-20 Concert 20% (estoque 6); #19 prod 90 Crafter HT-100 Folk 18% (2399, estoque 3); #24 prod 94 Taylor 110e 8% (5999, estoque 4). Os 4 produtos são `active` com estoque>0.
- 21 inativas (Black Friday, Páscoa, etc.). Produtos 93, 96, 99 têm 2-3 promoções, todas inativas. Nenhum produto com >1 promoção ativa. Sem datas de vigência: "ativa" = flag.
- Inativas para 96 (estoque 0) e 113 (discontinued): não oferecer.
- Política 6.2: não cumulativas, PIX 5% não vale sobre preço promocional, mostrar preço original + % + preço final.

## 7. Ambiguidade de busca
- **"Takamine GD20" existe**: id 95 "Takamine GD20 Dreadnought Natural", R$2199, estoque 5, active, sem promoção. Outros Takamine: 100 GC5CE, 105 GN51CE, 115 GC1CE.
- "violão/violões" **não aparece em nenhum nome**; só na categoria 5 e descrições. Precisa mapear sinônimo -> categoria (violão -> 5, guitarra -> 1, baixo -> 2, bateria -> 3, teclado/piano -> 4, ukulele -> 9) e normalizar acentos.
- Marca sozinha ambígua: Yamaha em 10 produtos de várias categorias (violões, baixo, baterias); Tagima, Giannini, Takamine, Crafter, Taylor etc. em vários.
- Nomes genéricos: "Bass 1X-4X Electric Bass", "Synth 1-3 Pro", "Kit 1-3 Studio".
- "Elétrico Nylon/Aço" no nome = violão eletroacústico, não guitarra.
- Prod 128 Kala KA-B Barítono Mogno (cat 9, ukulele) cita "violão" na descrição: busca em texto livre pode trazê-lo em consulta de violão.

## 8. Violões (cat 5) até R$ 1000
14 com preço <=1000; **12 disponíveis** (id, preço, estoque):
83 Tagima Memphis AC-39 429.9 (15); 85 Rozini RC-104 459.9 (10); 89 Shelby SN-100 549 (5); 88 Giannini GF-1R 579.9 (7); 81 Yamaha C40 599.9 (12); 84 Giannini GN-15 689 (6); 87 Yamaha F310 699.9 (14); 86 Tagima Dallas Tuner 749 (9); 107 Shelby SGD-195E 799 (6); 82 Yamaha C70 849 (8); 91 Tagima Woodstock 899 (11); 112 Tagima TW-7 7 Cordas 999 (6).
Indisponíveis: 96 Giannini GF-3D 799.9 (estoque 0, active) e 113 Shelby SN-7C 749 (estoque 0, discontinued). Nenhum dos 12 tem promoção ativa. Próximo acima: 101 Giannini GNF-3 CEQ 1049.

## 9. PII
customers: nome completo, telefone BR, email (LGPD, política seção 9). Domínios fictícios. Sem CPF, endereço ou cartão; orders sem endereço. Recomendações: pedido exige order_id + verificação (email ou telefone do cliente); nunca listar clientes por nome; mascarar telefone/email nas respostas; não expor tracking/notes de outro cliente; não logar PII crua.

## 10. Divergências CSV x PDF
- ">300 instrumentos" vs 65; sopro/cordas orquestrais "vendidos" vs 0 itens.
- Telefone: 3341-4444 (capa/dados) vs WhatsApp (67) 3321-4500 (seção 7); e-mail com e sem acento (`emporiodamusica` vs `empóriodamusica`).
- PIX 5% e parcela mínima não refletidos nos pedidos (seção 5).
- Frete (grátis >R$500 em Campo Grande, R$35 abaixo) não está nos CSVs.

## 11. Implicações para as ferramentas
1. Disponibilidade = active AND stock>0 (96 é armadilha; 136 e 113 descontinuados; 130 coming_soon).
2. Promoção só com is_active=1 e produto disponível; Decimal; sem PIX sobre promo.
3. Busca: normalização de acentos, sinônimos de categoria, retorno found/not_found/ambiguous (ex.: "Yamaha").
4. Pedido: exigir order_id + verificação; email não é único.
5. Não recalcular total do pedido (3 e 20 divergem).
6. Categorias vazias e política desatualizada: responder com base nos dados e escalar o resto.
