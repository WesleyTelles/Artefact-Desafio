# Arquitetura

Este documento descreve o que está implementado e testado. Alternativas apenas pesquisadas aparecem separadas, na seção "Alternativas pesquisadas e não implementadas".

## Fluxo de uma mensagem

```
Cliente (CLI)
   │ texto
   ▼
sanitize_input (remove controle/invisíveis, limite 1000)
   ▼
Orquestrador ── prompt do sistema + memória (20 msgs) ──► LLMClient ──► provedor
   ▲                                                        │   (retry com backoff só em 429/5xx/timeout/conexão;
   │                                                        │    esgotado ou erro permanente → LLMError com categoria)
   │ resultado (dado)                         texto final ◄─┤ ou tool_calls
   │                                                        ▼
   │                       argumentos válidos? (JSON, tipos, campos)
   │                          │ não: erro estruturado volta ao modelo (1 correção por ferramenta,
   │                          │      depois resposta fixa "reformule")
   └────────── registry.execute ◄─── sim (máx. 6 iterações, cache de chamadas idênticas)
                  │
   ┌──────────────┼───────────────────────┐
   ▼              ▼                       ▼
CSVs (catálogo,  Manual (BM25 +        Regras numéricas
pedidos, promo)  29 trechos)           (parcelas, frete, prazo)
   │ conflitos entre campos do produto
   │ (data_conflicts, details) sinalizados ao LLM
   ▼
mascaramento de contatos na saída ──► resposta
   │
   └─► telemetria JSONL por turno (opcional, sem texto do cliente nem argumentos)

Falha de ferramenta sem nenhum dado válido no turno, falha do LLM ou limite de iterações
→ resposta fixa de indisponibilidade (o texto do LLM é descartado); a categoria técnica
vai ao log e, com dica de configuração, ao stderr do operador.
```

## Camadas

| Camada | Pasta | Responsabilidade |
|---|---|---|
| Interface | `app/interfaces` | CLI, comandos `/limpar` e `/sair`, `--debug` com dados mascarados, dica ao operador no stderr |
| Agente | `app/agent` | prompt, memória, loop de ferramentas, guardrails, validação de argumentos |
| LLM | `app/llm` | `LLMClient` (Protocol); cliente OpenAI-compatível com retry e categorias de erro; mock por intenções |
| Ferramentas | `app/tools` | funções determinísticas com schema; nunca levantam exceção |
| Conhecimento | `app/knowledge` | chunking, BM25, regras numéricas |
| Dados | `app/data` | carga, validação, normalização, auditoria de qualidade dos produtos (`quality.py`) |
| Núcleo | `app/core` | configuração central, exceções, telemetria |

## Tratamento de erros do provedor

O cliente (`app/llm/openai_compat.py`) desliga o retry do SDK e aplica o próprio. Só falhas transitórias são repetidas, até `LLM_MAX_ATTEMPTS` chamadas por pedido (padrão 3, limite 10), com espera exponencial (base 1 s, teto 8 s) e jitter de 50% a 100%. Se o provedor enviar `Retry-After` numérico, ele é respeitado com teto de 10 s.

| Categoria | Origem | Repete? | Dica ao operador (stderr) |
|---|---|---|---|
| `rate_limit` | HTTP 429 | sim | não |
| `server_error` | HTTP 5xx | sim | não |
| `timeout` | tempo esgotado, HTTP 408 | sim | não |
| `connection` | falha de rede | sim | sim, verificar rede e `LLM_BASE_URL` |
| `auth` | HTTP 401/403 | não | sim, verificar `LLM_API_KEY` |
| `not_found` | HTTP 404 | não | sim, verificar `LLM_MODEL`/`LLM_BASE_URL` |
| `bad_request` | outros 4xx | não | sim, verificar `LLM_MODEL` e o formato |
| `bad_response` | resposta sem conteúdo ou inesperada | não | não |
| `config` | chave, modelo ou endereço ausentes | não | sim |

Para o cliente, qualquer categoria vira a mesma resposta fixa de indisponibilidade, sem detalhe técnico. As mensagens de erro nunca levam chave nem corpo da resposta. Outras categorias do orquestrador, só no log: `tool_error`, `invalid_arguments`, `iteration_limit`, `empty_response`.

Argumentos de ferramenta inválidos (JSON malformado, não objeto, tipo errado, campo ausente ou extra, ferramenta inexistente) nunca são executados: voltam ao modelo como erro estruturado com um resumo do schema. Há uma correção por ferramenta no turno (`MAX_ARG_CORRECTIONS`); persistindo, o turno termina com resposta fixa pedindo para reformular.

## Matriz de decisão

Escala de 1 (ruim) a 5 (bom), como na pesquisa; "-" quando a escolha não foi pontuada (provedor e observabilidade seguem os critérios do texto). Pesquisa completa e histórica em `docs/discovery/tech_research.md`. A coluna "Status" separa o que foi implementado do que ficou como alternativa pesquisada.

| Decisão | Alternativa | Adequação | Status | Motivo |
|---|---|---|---|---|
| Abordagem | Function calling nativo | 5 | implementado | operações exatas em código; sem SQL livre |
| Abordagem | ReAct em texto | 2 | pesquisado | parse frágil; superado pelo tool use nativo |
| Abordagem | RAG vetorial | 2 | pesquisado | 4 mil tokens de manual não justificam índice e segunda chave |
| Abordagem | SQL-agent | 1 | pesquisado | risco de vazamento entre clientes |
| Framework | Loop próprio | 5 | implementado | poucas dependências, testável com LLM falso |
| Framework | LangGraph / LlamaIndex | 1-2 | pesquisado | pensados para fluxos longos ou indexação |
| Provedor/LLM | Gemini `gemini-3.5-flash-lite`, plano gratuito, endpoint compatível com OpenAI | - | implementado e avaliado | critérios: chave gratuita para qualquer avaliador, tool calling funcionando, português adequado nos testes, custo e cota. Limites: cota baixa (houve 429 em rodadas curtas, sem 429 com 15 s de pausa), endpoint em beta, dados do plano gratuito podem ser usados pelo Google (aqui só dados fictícios) |
| Provedor/LLM | Anthropic (`claude-haiku-5-5`) | - | pesquisado | sem plano gratuito; exigiria conta com faturamento do avaliador |
| Provedor/LLM | OpenAI | - | pesquisado | sem plano gratuito listado |
| Provedor/LLM | Groq, Ollama | - | configuráveis, não testados | mesmo cliente com outro `LLM_PROVIDER`; modelos padrão não verificados |
| Interface | CLI | 5 | implementado | o foco é o agente; simples de avaliar e de testar |
| Interface | Streamlit, FastAPI | 1-2 | pesquisado | sem requisito de API ou web; dependências extras |
| Persistência | Memória de sessão (RAM) | 5 | implementado | cada execução é uma conversa; sem dados pessoais em disco |
| Persistência | SQLite | 2 | pesquisado | histórico entre execuções não é requisito |
| Observabilidade | Log JSONL opcional por turno | - | implementado | diagnóstico sem PII, desligado por padrão |

## Decisões que merecem registro

- **Regras em código, não no prompt.** Parcelas, frete, prazo de arrependimento e PIX são funções testadas. O LLM recebe o resultado.
- **Tool output é dado.** Cada resultado volta marcado como dado, com nota; o prompt proíbe obedecer instruções dentro dele.
- **Verificação de pedido.** O e-mail ou telefone precisa ter sido digitado pelo cliente na conversa; a mesma resposta serve para pedido inexistente e verificação errada; 5 erros bloqueiam a sessão e 5 erros no mesmo pedido o bloqueiam pelo processo. `/limpar` zera memória e contador da sessão, mas não o bloqueio por pedido.
- **Conflitos nos dados.** Quando nome, descrição e specs de um produto divergem (por exemplo nº de cordas), as ferramentas devolvem `data_conflicts` e o agente é instruído a não afirmar o ponto e a encaminhar a um atendente. Nada é corrigido na base. Ver `docs/DATA_QUALITY.md`.
- **Lacunas do manual.** Divergências e omissões do manual (por exemplo o início da contagem dos 10 dias úteis do reembolso, I-18) chegam ao LLM como avisos junto do trecho. Ver `docs/KNOWLEDGE.md`.
- **Falha técnica sem dado válido** gera resposta fixa de indisponibilidade com contatos da loja; o texto do LLM é descartado.
- **Gemini 3** exige devolver a `thought_signature` das chamadas de ferramenta; o cliente repassa `extra_content` na próxima requisição.
- **Telemetria sem PII.** Só ids de sessão e turno, nome/status/duração das ferramentas, tentativas e latência do LLM, tokens, categoria de erro e intenção derivada da primeira ferramenta. Nunca texto do cliente nem argumentos.
- **Mock separado do LLM real.** Serve para demonstração e testes offline, não mede qualidade.

## Alternativas pesquisadas e não implementadas

Contexto completo do manual no prompt (usado só como baseline conceitual), embeddings, adaptador próprio da Anthropic, Pydantic AI como plano B de framework, interface web, SQLite. Estão em `docs/discovery/tech_research.md` e não são parte do produto.

## Pontos de extensão

- Novo provedor compatível com OpenAI: variáveis `LLM_*` no `.env` (o que não foi testado deve ser validado antes de uso).
- Nova ferramenta: função em `app/tools/` e entrada no `registry` com schema.
- Outro canal (web, WhatsApp): chamar o orquestrador no lugar da CLI.
