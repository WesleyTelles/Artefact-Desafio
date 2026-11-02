# S07 - Endereço (execução 3)

- Resultado: **PASSOU**
- Requisições ao LLM: 2
- Dados: apenas a base fictícia da loja; e-mails e telefones de clientes mascarados.
- Esperado: Endereço do manual (Rua 14 de Maio, 3200, Campo Grande)
- Ferramenta esperada acionada: None
- Informação inventada (preço/prazo/número fora dos dados): nenhuma
- Latência total: 14157 ms; tentativas ao provedor: 2; tokens: {'prompt_tokens': 5018, 'completion_tokens': 62, 'total_tokens': 5080}

## Turno 1

**Cliente:**

> Qual o endereço da loja?

**Ferramentas:**

- `get_store_info({"topic": "address"})` -> found: {"status": "found", "info": {"address": {"value": "Rua 14 de Maio, 3200 - Centro, Campo Grande - MS, CEP 79202-333", "source": "Manual de Políticas v2.1 (jun/2025), §1.2, p.2 (também capa, p.1)"}}}

**Resposta final:**

> Nossa loja fica na Rua 14 de Maio, 3200, no Centro de Campo Grande/MS (CEP 79202-333). Como posso te ajudar hoje?
