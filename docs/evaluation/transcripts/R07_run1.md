# R07 - Pedido 4 entregue: só previsão de entrega (execução 1)

- Resultado: **PASSOU**
- Requisições ao LLM: 2
- Dados: apenas a base fictícia da loja; e-mails e telefones de clientes mascarados.
- Esperado: Pedido entregue; data 22/12 só como previsão
- Ferramenta esperada acionada: True
- Informação inventada (preço/prazo/número fora dos dados): nenhuma
- Latência total: 12442 ms; tentativas ao provedor: 2; tokens: {'prompt_tokens': 5231, 'completion_tokens': 77, 'total_tokens': 5308}

## Turno 1

**Cliente:**

> O pedido 4 foi entregue em que dia? Meu e-mail é l***@jmail.com

**Ferramentas:**

- `get_order_status({"verification": "l***@jmail.com", "order_id": 4})` -> found: pedido 4 delivered total R$ 799,90 itens ['Giannini GF-3D Dreadnought Sunburst']

**Resposta final:**

> O seu pedido 4 tem previsão de entrega para 22/12/2025. Como o sistema traz apenas a previsão, não consta a data exata em que foi entregue, beleza?
