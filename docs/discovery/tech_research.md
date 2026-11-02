# Pesquisa técnica (Discovery) - Empório da Música

> **STATUS (fase 1, pesquisa inicial; histórico preservado).** Este documento registra as alternativas pesquisadas e a recomendação feita na época. A implementação final difere em pontos importantes: o provedor implementado e validado é o **Gemini** (`gemini-3.5-flash-lite`, plano gratuito, endpoint compatível com OpenAI, um único cliente em `app/llm/openai_compat.py`); **Anthropic e OpenAI foram apenas alternativas pesquisadas e não foram implementadas**; Groq e Ollama são configuráveis pelo mesmo cliente, mas não foram testados. As políticas usam BM25 próprio sobre 29 trechos (em vez de contexto completo), a ferramenta é `search_store_policies` e o comando de demonstração é `python main.py --mock`. O log JSONL opcional, citado aqui como possibilidade, foi implementado depois: desligado por padrão (`EMPORIO_LOG_FILE`) e sem dados pessoais. Preços e cotas abaixo são da data da pesquisa e não foram reconferidos. Decisão final: README §4 e ARCHITECTURE.md.

Data da pesquisa: 2026-11-01. Autor: ai-solution-architect. Preços e nomes de modelo vieram das páginas oficiais listadas ao final; o que não foi confirmado em fonte oficial está marcado como **[não verificado]**.

## 0. Fatos do problema que guiam as decisões (medidos em `data/` e `docs/challenge/`)

| Fato | Valor | Implicação |
|---|---|---|
| products.csv | 65 produtos (registros), 22 KB | Cabe em memória; filtro/busca em Python/pandas ou dict, sem banco vetorial |
| customers / orders / order_items / promotions / categories | 50 / 20 / 22 / 25 / 9 registros | Idem; dados relacionais minúsculos |
| Políticas (texto extraido) | 12,7 KB (~4 mil tokens) | Cabe inteiro no contexto de qualquer modelo atual (janelas de 1M tokens na família Claude 5.x) |
| PDF original | 180 KB, `docs/challenge/politicas_extraido.txt` já existe | Extração deve ser reprodutível no código (PyMuPDF/pypdf) e comparável ao texto de referência |

Conclusão prévia: o problema é **dados estruturados pequenos + um documento curto**. Escala não é requisito; corretude, anti-alucinação e facilidade de execução são.

## (a) Abordagem

Critérios (1 = ruim, 5 = bom; para custo/complexidade operacional, 5 = barato/simples).

| Abordagem | Facilidade | Custo | Plano gratuito | Docs | Integração Python | Function calling | Complex. operacional | Adequação ao caso |
|---|---|---|---|---|---|---|---|---|
| Function calling nativo (ferramentas determinísticas em Python) | 5 | 5 | Depende do provedor | 5 | 5 | Nativo | 5 | **5** - atende regra 3 (operações determinísticas em código, sem SQL livre) |
| ReAct em texto (Thought/Action parseado) | 3 | 4 | Idem | 3 | 4 | Não usa (parse frágil) | 3 | 2 - superado pelo tool use nativo; parse de texto é fonte de falhas |
| RAG vetorial (embeddings) | 2 | 3 | Parcial (embeddings tem custo/cota) | 4 | 4 | Opcional | 2 | 2 - 4 mil tokens de política não justificam índice; adiciona 2ª chave/modelo |
| SQL-agent (LLM gera SQL) | 3 | 4 | Idem | 3 | 4 | Sim | 2 | 1 - **viola regra 3** (sem SQL arbitrário); risco de injection e vazamento entre clientes |
| Híbrido: function calling + políticas no contexto (ou BM25 opcional) | 4 | 5 | Idem | 5 | 5 | Nativo | 4 | **5** |

Decisão: **híbrido mínimo** = function calling nativo para catálogo/pedidos/promoções + políticas como ferramenta `buscar_politica` (ou bloco fixo no prompt de sistema, ver (d)). Descartados: ReAct textual (frágil), RAG vetorial (desproporcional), SQL-agent (proibido pelas regras).

## (b) Framework

| Framework | Facilidade | Custo (deps/overhead) | Docs | Integração | Function calling | Testes offline | Complex. operacional | Adequação |
|---|---|---|---|---|---|---|---|---|
| SDK nativo + loop próprio (~60-100 linhas) | 4 | 5 (1-2 deps leves) | 5 | 5 | Nativo | Total (MockLLM próprio) | 5 | **5** se houver interface `LLMClient` fina |
| Pydantic AI | 4 | 4 | 4 | 5 | Sim, multi-provedor | **Ótimo**: `TestModel`, `FunctionModel`, `ALLOW_MODEL_REQUESTS=False`, `Agent.override` | 4 | 4 - forte alternativa; troca de provedor por string |
| LangGraph | 2 | 2 (ecossistema grande) | 4 | 4 | Via LangChain/model | Médio | 2 | 2 - pensado para fluxos duraveis/multi-agente; desnecessário aqui |
| LlamaIndex | 2 | 2 | 3 | 4 | Sim | Médio | 2 | 1 - foco em indexação/RAG; o pacote relata foco da empresa migrando para LlamaParse; sem índice a ganhar |

Evidências: LangGraph se descreve como "framework de orquestração de baixo nível" para agentes stateful de longa duração e recomenda alternativas mais simples para necessidades simples. Pydantic AI documenta `TestModel`/`FunctionModel` e o bloqueio global de requisições reais em testes. LlamaIndex 0.14.25 (set/2026) é um pacote guarda-chuva (`llama-index-core` é a versão leve).

Decisão: **SDK nativo + interface `LLMClient` (Protocol)** com `MockLLM`. Plano B documentado: Pydantic AI se o custo de manter dois adaptadores se mostrar alto.

## (c) Provedor / modelo

Nomes e preços conforme páginas oficiais em 2026-11-01. "Avaliador com uma chave" = esforço para quem só tem uma chave.

| Provedor | Modelo (ID) para este projeto | Preço por 1M tokens (in/out) | Plano gratuito | Tool use / português | Facilidade p/ avaliador |
|---|---|---|---|---|---|
| Anthropic | `claude-haiku-5-5` (rápido; até 100k tokens: $0.10 / $0.50); `claude-sonnet-5-5` ($2 / $10) | ver col. anterior | **Não**: pagamento postpaid, sem créditos pré-pagos (página de preços) | Todos os modelos atuais suportam tool use e multilingue (página de modelos) | Média: exige conta com faturamento |
| OpenAI | `gpt-6-luna` ($0.10 / $0.50, "mais eficiente"); flagship `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6.1-terra` | idem | **Nenhum listado** para inferência | Function calling "Yes" em todos | Média: exige faturamento; chave muito comum entre avaliadores **[não verificado]** |
| Google Gemini | `gemini-3.8-flash` (pago $0.75/$3.75 até 31/12/2026, depois $1.50/$7.50); `gemini-2.5-flash-lite` ($0.10/$0.40) | idem | **Sim** (entrada e saída grátis nos modelos Flash/Flash-Lite). Cotas exatas não publicadas na página de limites; fontes de terceiros citam ~20 RPD no 3.8 Flash e ~500 RPD no Flash-Lite **[não verificado, terceiros]** | Function calling com modos `auto/any/none/validated`, chamadas paralelas | **Alta**: chave grátis no AI Studio; risco: cota diária baixa e dados do free tier usados para melhorar produtos Google |
| Groq | `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`, `llama-3.3-70b-versatile` | não consultado | Existe plano Free (limites só no console do usuário) | "Todos os modelos hospedados suportam tool use"; GPT-OSS **sem** chamadas paralelas | Alta (chave grátis), mas qualidade em PT e confiabilidade de tools variam por modelo **[não verificado]** |
| Local (Ollama) | `qwen3.8` 27b (tag de tools, 5,5M pulls) e outros com tag tools | $0 | Grátis, offline | Tool use via tag; qualidade em PT depende do tamanho | Baixa: exige download de vários GB e GPU/RAM; não recomendado como caminho padrão |

Ressalvas: preços Gemini 3.x Flash dobram em 01/01/2027 (relevante se a avaliação ocorrer depois). Nao testei qualidade em português empiricamente; só a documentação oficial dos modelos Claude declara suporte multilingue. Um teste real de poucas conversas é obrigatório na fase 6.

Custo estimado por conversa: ~6 mil tokens de entrada (políticas + histórico + tools) e ~500 de saída. Com `claude-haiku-5-5`: ~US$0,001; com `gpt-6-luna`: ~US$0,001. Custo é irrelevante; **o fator decisivo é a chave do avaliador**.

Decisão: dois adaptadores reais bastam: (1) **Anthropic SDK** e (2) **cliente compatível com OpenAI** (cobre OpenAI e, por endpoint compatível, Gemini/Groq/Ollama via `base_url` **[compatibilidade a confirmar nas docs de cada um antes de prometer no README]**). Padrão sugerido: Anthropic `claude-haiku-5-5` (ou Sonnet para qualidade); Gemini como rota gratuita documentada. Tudo configurável em `app/core/config.py` via `.env`.

## (d) PDF e retrieval

| PDF lib | Facilidade | Licença | Instalação | Qualidade | Adequação |
|---|---|---|---|---|---|
| PyMuPDF | 5 | **AGPL** ou comercial (docs oficiais) | wheel, sem deps de sistema **[não verificado]** | Mais rápida (8 s vs 101 s do PyPDF2 no benchmark oficial dos autores) | Boa, mas AGPL é risco para entrega/reuso; velocidade irrelevante para 180 KB |
| pypdf | 5 | Livre (BSD, **[não verificado na página]**) | Python puro | Suficiente p/ texto simples | **Preferida**: leve, sem copyleft; validar contra `politicas_extraido.txt` |

| Retrieval | Facilidade | Custo | Deps/ops | Risco de erro | Adequação |
|---|---|---|---|---|---|
| Contexto completo (12,7 KB) | 5 | ~4 mil tokens/chamada | Nenhuma | Mínimo: nada é perdido | **5** |
| BM25 (`rank-bm25`) | 4 | 0 | Pequena, mas última release em 02/2022 (0.2.2), mantenedor único | Médio: perda de contexto por chunking, PT sem stemming | 3 - só se políticas crescerem |
| Embeddings + FAISS/Chroma | 2 | Chamadas de embedding + 2ª chave | Alta | Médio-alto | 1 - desproporcional |

Decisão: **pypdf + contexto completo**, segmentado por seções (título/numeração) para permitir citar a seção na resposta. Ferramenta `buscar_politica(topico)` pode devolver a seção inteira por busca lexical simples em Python (sem lib extra). O texto do PDF é tratado como dado: delimitado e marcado como não confiável no prompt (regra 4).

## (e) Interface

| Opção | Facilidade p/ avaliador | Deps | Testabilidade | Adequação |
|---|---|---|---|---|
| CLI (loop `input()`) | 5 | 0 | Alta (stdin/stdout, MockLLM) | **5** - plano de fases já define CLI |
| Streamlit | 4 | Pesada | Baixa | 2 - bônus opcional; não pude confirmar API de chat nas docs consultadas |
| FastAPI | 3 | Média | Alta | 1 - sem requisito de API |

Decisão: **CLI**. Streamlit só como extra se sobrar tempo, sem tocar o núcleo.

## (f) Persistência

| Opção | Facilidade | Ops | Valor | Adequação |
|---|---|---|---|---|
| Memória de sessão (lista em processo) | 5 | Nenhuma | Suficiente para conversa multi-turno | **5** |
| SQLite (histórico/logs) | 3 | Arquivo local, stdlib | Auditoria e retomada; não exigido | 2 - só se o enunciado pedir histórico entre execuções (verificar em `docs/challenge/`) |

Decisão: **memória de sessão**, com janela limitada de turnos. Log estruturado em arquivo (JSONL) opcional para evidenciar exemplos reais (regra 7).

## Modo offline / mock (requisito de avaliação)

- `LLMClient` (Protocol): `complete(messages, tools) -> LLMResponse` com `text` e/ou `tool_calls`.
- `MockLLM` roteirizado por cenário: devolve tool_calls predefinidas e depois texto montado a partir do resultado da ferramenta. Permite testar **conteúdo** (preço, estoque, status, recusa) sem rede, de forma determinística e grátis.
- `python -m app --mock` roda a demo sem chave; avaliador valida o fluxo e as ferramentas imediatamente. Deixar claro no README que o mock **não** demonstra a qualidade de linguagem do LLM real.
- Testes de integração com LLM real marcados (`@pytest.mark.live`), fora do `pytest` padrão.

## Recomendação única

Python; **function calling nativo** com loop próprio e limite de iterações; ferramentas determinísticas sobre CSV carregado em memória (sem SQL livre); políticas extraídas com **pypdf** e entregues por contexto completo/seção; interface **CLI**; sessão em **memória**; `LLMClient` com adaptadores **Anthropic** (padrão `claude-haiku-5-5`) e **OpenAI-compatível** (OpenAI/Gemini grátis/Groq/Ollama), mais **MockLLM** para testes e demo offline.

## Riscos

1. Qualidade de tool use em PT não medida; mitigar com 15-20 cenários reais na fase 6 antes de fixar o modelo padrão.
2. Cotas gratuitas do Gemini baixas e não oficialmente documentadas; avaliador pode bater no limite. Tratar 429 como falha técnica (regra 5) com mensagem clara.
3. Preços/modelos mudam rápido (Gemini 3.x dobra em 01/01/2027); documentar a data da consulta, IDs configuráveis.
4. Compatibilidade OpenAI-like dos demais provedores não verificada; só prometer no README o que for testado.
5. Mock pode dar falsa confiança; separar claramente testes de lógica (mock) de testes live.
6. Prompt injection via campos CSV/PDF; delimitar dados e nunca executar instruções deles.
7. Ambiguidade de cliente/pedido: ferramentas devem retornar estados explícitos (encontrado/não encontrado/ambíguo/erro).

## URLs consultadas

- https://platform.claude.com/docs/en/docs/about-claude/models/overview
- https://platform.claude.com/docs/en/about-claude/pricing
- https://developers.openai.com/api/docs/pricing
- https://developers.openai.com/api/docs/models
- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/rate-limits
- https://ai.google.dev/gemini-api/docs/function-calling
- https://console.groq.com/docs/rate-limits
- https://console.groq.com/docs/tool-use/overview
- https://ollama.com/search?c=tools
- https://pydantic.dev/docs/ai/overview/
- https://pydantic.dev/docs/ai/guides/testing/
- https://docs.langchain.com/oss/python/langgraph/overview
- https://pypi.org/project/llama-index/
- https://pymupdf.readthedocs.io/en/latest/about.html
- https://pypdf.readthedocs.io/en/stable/
- https://pypi.org/project/rank-bm25/
- Terceiros (cotas Gemini, não oficiais): https://www.scriptbyai.com/gemini-api-free-tier-limits/ e https://apidog.com/blog/gemini-api-free-tier/
