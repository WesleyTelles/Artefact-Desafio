# S12 - Pergunta ambígua (execução 3)

- Resultado: **PASSOU**
- Requisições ao LLM: 2
- Dados: apenas a base fictícia da loja; e-mails e telefones de clientes mascarados.
- Esperado: Pergunta qual modelo Yamaha, sem escolher um preço
- Ferramenta esperada acionada: True
- Informação inventada (preço/prazo/número fora dos dados): nenhuma
- Latência total: 10783 ms; tentativas ao provedor: 2; tokens: {'prompt_tokens': 6442, 'completion_tokens': 86, 'total_tokens': 6528}

## Turno 1

**Cliente:**

> Quanto custa a Yamaha?

**Ferramentas:**

- `search_products({"query": "Yamaha"})` -> ambiguous: 81 Yamaha C40 Nylon Natural R$ 599,90 (in_stock); 82 Yamaha C70 Nylon Natural R$ 849,00 (in_stock); 87 Yamaha F310 Aço Natural R$ 699,90 (in_stock); 92 Yamaha FG800 Dreadnought Natural R$ 1.299,00 (in_stock); 98 Yamaha NTX1 Elétrico Nylon Natural R$ 3.499,00 (in_stock); 104 Yamaha APX600 Elétrico Aço Preto R$ 1.899,00 (in_stock) (+4)

**Resposta final:**

> Temos vários instrumentos da Yamaha por aqui, como o violão C40 por R$ 599,90, o F310 por R$ 699,90, além de baixos e baterias. 
> 
> Qual modelo da Yamaha você está procurando para eu te passar o preço certinho?
