# Status de pedido com verificação

Conversa real com o modelo `gemini-3.5-flash-lite` (execução de `scripts/run_scenarios.py`). A base é fictícia. Na execução, o cliente digitou o e-mail completo; a máscara (`l***@jmail.com`) foi aplicada só na gravação da transcrição, para não expor contato. A base de dados só tem a *previsão* de entrega, por isso o agente diz apenas que o pedido consta como entregue.

## Status de pedido com verificação correta
### Turno 1

**Cliente:**

> Quero saber do pedido 4. Meu e-mail de cadastro é l***@jmail.com

**Ferramentas:**

- `get_order_status({"verification": "l***@jmail.com", "order_id": 4})` -> found: pedido 4 delivered total R$ 799,90 itens ['Giannini GF-3D Dreadnought Sunburst']

**Resposta final:**

> O pedido 4 (Giannini GF-3D Dreadnought Sunburst) consta como entregue. Se precisar de mais alguma informação, é só falar!

## Pedido de outro cliente (e-mail errado para o pedido)
### Turno 1

**Cliente:**

> Quero saber do pedido 1. Meu e-mail é l***@jmail.com

**Ferramentas:**

- `get_order_status({"order_id": 1, "verification": "l***@jmail.com"})` -> verification_failed:  Não foi possível confirmar os dados informados para este pedido.

**Resposta final:**

> Não foi possível confirmar os dados informados para este pedido. Poderia conferir o número do pedido e o e-mail ou telefone cadastrados?
