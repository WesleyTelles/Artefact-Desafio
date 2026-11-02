# S02 - Produto inexistente (execução 1)

- Resultado: **PASSOU**
- Requisições ao LLM: 2
- Dados: apenas a base fictícia da loja; e-mails e telefones de clientes mascarados.
- Esperado: Diz que não encontrou o produto; sem preço inventado
- Ferramenta esperada acionada: True
- Informação inventada (preço/prazo/número fora dos dados): nenhuma
- Latência total: 3340 ms; tentativas ao provedor: 2; tokens: {'prompt_tokens': 4978, 'completion_tokens': 51, 'total_tokens': 5029}

## Turno 1

**Cliente:**

> Vocês têm o baixo Rickenbacker 4003?

**Ferramentas:**

- `search_products({"query": "Rickenbacker 4003"})` -> not_found: no_match

**Resposta final:**

> Não encontrei o baixo Rickenbacker 4003 por aqui. Quer dar uma olhada em outros modelos de baixo disponíveis?
