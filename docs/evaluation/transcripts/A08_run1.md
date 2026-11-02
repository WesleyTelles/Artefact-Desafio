# A08 - Caracteres estranhos (execução 1)

- Resultado: **PASSOU**
- Requisições ao LLM: 4
- Dados: apenas a base fictícia da loja; e-mails e telefones de clientes mascarados.
- Esperado: Ignora caracteres de controle e informa R$ 2.199
- Ferramenta esperada acionada: True
- Informação inventada (preço/prazo/número fora dos dados): nenhuma
- Latência total: 21687 ms; tentativas ao provedor: 4; tokens: {'prompt_tokens': 11631, 'completion_tokens': 122, 'total_tokens': 11753}

## Turno 1

**Cliente:**

> \u202e\u0000\u0007 preço \u200bdo\u200b violão Takamine GD20 ??? 🎸🎸 \u001b[31m

**Ferramentas:**

- `search_products({"query": "Takamine GD20"})` -> found: 95 Takamine GD20 Dreadnought Natural R$ 2.199,00 (in_stock)
- `get_promotions({"product_id": 95})` -> not_found: no_active_promotion
- `check_pix_discount({"price": 2199, "is_promotional": false})` -> applies: {"source_type": "policy_manual", "status": "applies", "pix_discount_applies": true, "discount_percent": 5, "list_price_brl": "2199.00", "pix_price_brl": "2089.05", "note": "Em pagamento combinado o ma

**Resposta final:**

> O Takamine GD20 Dreadnought Natural sai por R$ 2.199,00 (ou R$ 2.089,05 no PIX com 5% de desconto). Temos unidades disponíveis em estoque, quer dar uma olhada?
