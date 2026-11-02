# S06b - Pedido inexistente (execução 1)

- Resultado: **PASSOU**
- Requisições ao LLM: 2
- Dados: apenas a base fictícia da loja; e-mails e telefones de clientes mascarados.
- Esperado: Não confirma existência do pedido 9999; pede conferência
- Ferramenta esperada acionada: True
- Informação inventada (preço/prazo/número fora dos dados): nenhuma
- Latência total: 4056 ms; tentativas ao provedor: 2; tokens: {'prompt_tokens': 5010, 'completion_tokens': 66, 'total_tokens': 5076}

## Turno 1

**Cliente:**

> Status do pedido 9999? Meu e-mail é l***@jmail.com

**Ferramentas:**

- `get_order_status({"verification": "l***@jmail.com", "order_id": 9999})` -> verification_failed:  Não foi possível confirmar os dados informados para este pedido.

**Resposta final:**

> Não foi possível confirmar os dados informados para este pedido. Poderia conferir o número do pedido e o e-mail ou telefone cadastrados?
