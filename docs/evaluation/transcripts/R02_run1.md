# R02 - Entrega em Dourados (§5.2) (execução 1)

- Resultado: **PASSOU**
- Requisições ao LLM: 2
- Dados: apenas a base fictícia da loja; e-mails e telefones de clientes mascarados.
- Esperado: Dourados: Correios/Jadlog (§5.2), frete por CEP; sem 1-3 dias, R$ 35 ou frete grátis
- Ferramenta esperada acionada: True
- Informação inventada (preço/prazo/número fora dos dados): nenhuma
- Latência total: 7473 ms; tentativas ao provedor: 2; tokens: {'prompt_tokens': 5491, 'completion_tokens': 78, 'total_tokens': 5569}

## Turno 1

**Cliente:**

> vocês entregam em Dourados?

**Ferramentas:**

- `search_store_policies({"query": "entrega Dourados frete envio"})` -> found: {"status": "found", "source_type": "policy_manual", "query": "entrega Dourados frete envio", "results": [{"chunk_id": "s5.2", "section": "5.2", "title": "Entregas para Outras Cidades", "page_start": 4

**Resposta final:**

> Sim, entregamos em Dourados! Para fora da região metropolitana de Campo Grande, enviamos pelos Correios (PAC e SEDEX) ou transportadora Jadlog, com o frete calculado pelo CEP. Quer dar uma olhada em algum instrumento?
