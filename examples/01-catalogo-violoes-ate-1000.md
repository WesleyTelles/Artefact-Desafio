# Consulta ao catálogo

Conversa real com o modelo `gemini-3.5-flash-lite` (execução de `scripts/run_scenarios.py`). Os dados vêm da base fictícia da loja; e-mails e telefones de clientes aparecem mascarados.

## Violões até R$ 1.000


### Turno 1

**Cliente:**

> Quais violões vocês têm até R$ 1000?

**Ferramentas:**

- `search_products({"price_max": 1000, "category": "violão"})` -> found: 83 Tagima Memphis AC-39 Nylon Natural R$ 429,90 (in_stock); 85 Rozini RC-104 Nylon Estudante R$ 459,90 (in_stock); 89 Shelby SN-100 Folk Aço Preto R$ 549,00 (in_stock); 88 Giannini GF-1R Aço Folk Sunburst R$ 579,90 (in_stock); 81 Yamaha C40 Nylon Natural R$ 599,90 (in_stock); 84 Giannini GN-15 Nylon Cedr Natural R$ 689,00 (in_stock) (+8)

**Resposta final:**

> Temos várias opções de violões até R$ 1.000 em estoque, como o Tagima Memphis AC-39 por R$ 429,90, o Yamaha C40 por R$ 599,90 e o Tagima Dallas por R$ 749,00. 
> 
> Prefere algum modelo com cordas de nylon ou de aço?
