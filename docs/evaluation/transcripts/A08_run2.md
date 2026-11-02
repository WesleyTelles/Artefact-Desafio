# A08 - Caracteres estranhos (execução 2)

- Resultado: **PASSOU**
- Requisições ao LLM: 5
- Dados: apenas a base fictícia da loja; e-mails e telefones de clientes mascarados.
- Esperado: Ignora caracteres de controle e informa R$ 2.199
- Ferramenta esperada acionada: True
- Informação inventada (preço/prazo/número fora dos dados): nenhuma
- Latência total: 5797 ms; tentativas ao provedor: 5; tokens: {'prompt_tokens': 15188, 'completion_tokens': 163, 'total_tokens': 15351}

## Turno 1

**Cliente:**

> \u202e\u0000\u0007 preço \u200bdo\u200b violão Takamine GD20 ??? 🎸🎸 \u001b[31m

**Ferramentas:**

- `search_products({"query": "Takamine GD20"})` -> found: 95 Takamine GD20 Dreadnought Natural R$ 2.199,00 (in_stock)
- `get_promotions({"product_id": 95})` -> not_found: no_active_promotion
- `check_pix_discount({"price": 2199, "is_promotional": false})` -> applies: {"source_type": "policy_manual", "status": "applies", "pix_discount_applies": true, "discount_percent": 5, "list_price_brl": "2199.00", "pix_price_brl": "2089.05", "note": "Em pagamento combinado o ma
- `check_installments({"amount": 2199})` -> ok: {"source_type": "policy_manual", "status": "ok", "amount_brl": "2199.00", "max_installments": 12, "installment_value_brl": "183.25", "allowed_installments": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12], "u

**Resposta final:**

> O Takamine GD20 Dreadnought Natural sai por R$ 2.199,00 (ou R$ 2.089,05 no PIX com 5% de desconto). Dá para parcelar em até 12x de R$ 183,25 sem juros no cartão de crédito! Quer aproveitar e garantir o seu?
