# Arquitetura

## Fluxo de uma mensagem

```
Cliente (CLI)
   │ texto
   ▼
sanitize_input (remove controle/invisíveis, limite 1000)
   ▼
Orquestrador ── prompt do sistema + memória (20 msgs) ──► LLMClient
   ▲                                                        │
   │ resultado (dado)                         texto final ◄─┤ ou tool_calls
   │                                                        ▼
   └──────────────── registry.execute ◄──────── (máx. 6 iterações)
                          │
        ┌─────────────────┼──────────────────────┐
        ▼                 ▼                      ▼
   CSVs (catálogo,   Manual (BM25 +         Regras numéricas
   pedidos, promo)   29 trechos)            (parcelas, frete, prazo)
   ▼
mascaramento de contatos na saída ──► resposta
```

## Camadas

| Camada | Pasta | Responsabilidade |
|---|---|---|
| Interface | `app/interfaces` | CLI e comandos `/limpar`, `/sair` |
| Agente | `app/agent` | prompt, memória, loop de ferramentas, guardrails |
| LLM | `app/llm` | `LLMClient` (Protocol); cliente OpenAI-compatível; mock |
| Ferramentas | `app/tools` | funções determinísticas com schema; nunca levantam exceção |
| Conhecimento | `app/knowledge` | chunking, BM25, regras numéricas |
| Dados | `app/data` | carga, validação, normalização |

## Matriz de decisão

Escala de 1 (ruim) a 5 (bom). Pesquisa completa em `docs/discovery/tech_research.md`.

| Alternativa | Adequação | Motivo |
|---|---|---|
| Function calling nativo | 5 | operações exatas em código; sem SQL livre |
| ReAct em texto | 2 | parse frágil; superado pelo tool use nativo |
| RAG vetorial | 2 | 4 mil tokens de manual não justificam índice e segunda chave |
| SQL-agent | 1 | risco de vazamento entre clientes |
| Loop próprio | 5 | poucas dependências, testável com mock |
| LangGraph / LlamaIndex | 1-2 | pensados para fluxos longos ou indexação |

## Decisões que merecem registro

- **Regras em código, não no prompt.** Parcelas, frete, prazo de arrependimento e PIX são funções testadas. O LLM recebe o resultado.
- **Tool output é dado.** Cada resultado volta marcado como dado, com nota; o prompt proíbe obedecer instruções dentro dele.
- **Verificação de pedido.** O e-mail ou telefone precisa ter sido digitado pelo cliente na conversa; a mesma resposta serve para pedido inexistente e verificação errada; 5 erros bloqueiam a sessão.
- **Falha técnica sem dado válido** gera resposta fixa de indisponibilidade com contatos da loja; o texto do LLM é descartado.
- **Gemini 3** exige devolver a `thought_signature` das chamadas de ferramenta; o cliente repassa `extra_content` na próxima requisição.
- **Memória só em RAM.** Escolha deliberada (privacidade e simplicidade).
- **Mock separado do LLM real.** Serve para demonstração e testes offline, não mede qualidade.

## Pontos de extensão

- Novo provedor compatível com OpenAI: variáveis `LLM_*` no `.env`.
- Nova ferramenta: função em `app/tools/` e entrada no `registry` com schema.
- Outro canal (web, WhatsApp): chamar o orquestrador no lugar da CLI.
