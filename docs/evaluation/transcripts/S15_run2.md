# S15 - Falha de ferramenta (injetada) (execução 2)

- Resultado: **PASSOU**
- Requisições ao LLM: 2
- Dados: apenas a base fictícia da loja; e-mails e telefones de clientes mascarados.
- Esperado: Indisponibilidade fixa com contatos, sem preço (falha injetada)
- Ferramenta esperada acionada: True
- Informação inventada (preço/prazo/número fora dos dados): nenhuma
- Latência total: 3029 ms; tentativas ao provedor: 2; tokens: {'prompt_tokens': 4967, 'completion_tokens': 50, 'total_tokens': 5017}
- Falha injetada na ferramenta `search_products`.

## Turno 1

**Cliente:**

> Qual o preço do violão Takamine GD20?

**Ferramentas:**

- `search_products({"query": "Takamine GD20"})` -> error: internal_error Falha técnica injetada.

**Resposta final:**

> Não consegui consultar isso agora. Tente de novo em alguns instantes ou fale com a loja pelo (67) 3341-4444 ou (67) 3321-4500 (WhatsApp); os dois números ainda precisam de confirmação.
