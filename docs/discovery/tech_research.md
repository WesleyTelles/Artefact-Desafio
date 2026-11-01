# Pesquisa tecnica (Discovery) - Emporio da Musica

Data da pesquisa: 2026-11-01. Autor: ai-solution-architect. Precos e nomes de modelo vieram das paginas oficiais listadas ao final; o que nao foi confirmado em fonte oficial esta marcado como **[nao verificado]**.

## 0. Fatos do problema que guiam as decisoes (medidos em `data/` e `docs/challenge/`)

| Fato | Valor | Implicacao |
|---|---|---|
| products.csv | 64 linhas (63 produtos + cabecalho), 22 KB | Cabe em memoria; filtro/busca em Python/pandas ou dict, sem banco vetorial |
| customers / orders / order_items / promotions / categories | 49 / 19 / 21 / 24 / 8 linhas (incl. cabecalho) | Idem; dados relacionais minusculos |
| Politicas (texto extraido) | 12,7 KB (~4 mil tokens) | Cabe inteiro no contexto de qualquer modelo atual (janelas de 1M tokens na familia Claude 5.x) |
| PDF original | 180 KB, `docs/challenge/politicas_extraido.txt` ja existe | Extracao deve ser reprodutivel no codigo (PyMuPDF/pypdf) e comparavel ao texto de referencia |

Conclusao previa: o problema e **dados estruturados pequenos + um documento curto**. Escala nao e requisito; corretude, anti-alucinacao e facilidade de execucao sao.

## (a) Abordagem

Criterios (1 = ruim, 5 = bom; para custo/complexidade operacional, 5 = barato/simples).

| Abordagem | Facilidade | Custo | Plano gratuito | Docs | Integracao Python | Function calling | Complex. operacional | Adequacao ao caso |
|---|---|---|---|---|---|---|---|---|
| Function calling nativo (ferramentas deterministicas em Python) | 5 | 5 | Depende do provedor | 5 | 5 | Nativo | 5 | **5** - atende regra 3 (operacoes deterministicas em codigo, sem SQL livre) |
| ReAct em texto (Thought/Action parseado) | 3 | 4 | Idem | 3 | 4 | Nao usa (parse fragil) | 3 | 2 - superado pelo tool use nativo; parse de texto e fonte de falhas |
| RAG vetorial (embeddings) | 2 | 3 | Parcial (embeddings tem custo/cota) | 4 | 4 | Opcional | 2 | 2 - 4 mil tokens de politica nao justificam indice; adiciona 2a chave/modelo |
| SQL-agent (LLM gera SQL) | 3 | 4 | Idem | 3 | 4 | Sim | 2 | 1 - **viola regra 3** (sem SQL arbitrario); risco de injection e vazamento entre clientes |
| Hibrido: function calling + politicas no contexto (ou BM25 opcional) | 4 | 5 | Idem | 5 | 5 | Nativo | 4 | **5** |

Decisao: **hibrido minimo** = function calling nativo para catalogo/pedidos/promocoes + politicas como ferramenta `buscar_politica` (ou bloco fixo no prompt de sistema, ver (d)). Descartados: ReAct textual (fragil), RAG vetorial (desproporcional), SQL-agent (proibido pelas regras).

## (b) Framework

| Framework | Facilidade | Custo (deps/overhead) | Docs | Integracao | Function calling | Testes offline | Complex. operacional | Adequacao |
|---|---|---|---|---|---|---|---|---|
| SDK nativo + loop proprio (~60-100 linhas) | 4 | 5 (1-2 deps leves) | 5 | 5 | Nativo | Total (MockLLM proprio) | 5 | **5** se houver interface `LLMClient` fina |
| Pydantic AI | 4 | 4 | 4 | 5 | Sim, multi-provedor | **Otimo**: `TestModel`, `FunctionModel`, `ALLOW_MODEL_REQUESTS=False`, `Agent.override` | 4 | 4 - forte alternativa; troca de provedor por string |
| LangGraph | 2 | 2 (ecossistema grande) | 4 | 4 | Via LangChain/model | Medio | 2 | 2 - pensado para fluxos duraveis/multi-agente; desnecessario aqui |
| LlamaIndex | 2 | 2 | 3 | 4 | Sim | Medio | 2 | 1 - foco em indexacao/RAG; o pacote relata foco da empresa migrando para LlamaParse; sem indice a ganhar |

Evidencias: LangGraph se descreve como "framework de orquestracao de baixo nivel" para agentes stateful de longa duracao e recomenda alternativas mais simples para necessidades simples. Pydantic AI documenta `TestModel`/`FunctionModel` e o bloqueio global de requisicoes reais em testes. LlamaIndex 0.14.25 (set/2026) e um pacote guarda-chuva (`llama-index-core` e a versao leve).

Decisao: **SDK nativo + interface `LLMClient` (Protocol)** com `MockLLM`. Plano B documentado: Pydantic AI se o custo de manter dois adaptadores se mostrar alto.

## (c) Provedor / modelo

Nomes e precos conforme paginas oficiais em 2026-11-01. "Avaliador com uma chave" = esforco para quem so tem uma chave.

| Provedor | Modelo (ID) para este projeto | Preco por 1M tokens (in/out) | Plano gratuito | Tool use / portugues | Facilidade p/ avaliador |
|---|---|---|---|---|---|
| Anthropic | `claude-haiku-5-5` (rapido; ate 100k tokens: $0.10 / $0.50); `claude-sonnet-5-5` ($2 / $10) | ver col. anterior | **Nao**: pagamento postpaid, sem creditos pre-pagos (pagina de precos) | Todos os modelos atuais suportam tool use e multilingue (pagina de modelos) | Media: exige conta com faturamento |
| OpenAI | `gpt-6-luna` ($0.10 / $0.50, "mais eficiente"); flagship `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6.1-terra` | idem | **Nenhum listado** para inferencia | Function calling "Yes" em todos | Media: exige faturamento; chave muito comum entre avaliadores **[nao verificado]** |
| Google Gemini | `gemini-3.8-flash` (pago $0.75/$3.75 ate 31/12/2026, depois $1.50/$7.50); `gemini-2.5-flash-lite` ($0.10/$0.40) | idem | **Sim** (entrada e saida gratis nos modelos Flash/Flash-Lite). Cotas exatas nao publicadas na pagina de limites; fontes de terceiros citam ~20 RPD no 3.8 Flash e ~500 RPD no Flash-Lite **[nao verificado, terceiros]** | Function calling com modos `auto/any/none/validated`, chamadas paralelas | **Alta**: chave gratis no AI Studio; risco: cota diaria baixa e dados do free tier usados para melhorar produtos Google |
| Groq | `openai/gpt-oss-120b`, `openai/gpt-oss-20b`, `qwen/qwen3.8-27b`, `llama-3.3-70b-versatile` | nao consultado | Existe plano Free (limites so no console do usuario) | "Todos os modelos hospedados suportam tool use"; GPT-OSS **sem** chamadas paralelas | Alta (chave gratis), mas qualidade em PT e confiabilidade de tools variam por modelo **[nao verificado]** |
| Local (Ollama) | `qwen3.8` 27b (tag de tools, 5,5M pulls) e outros com tag tools | $0 | Gratis, offline | Tool use via tag; qualidade em PT depende do tamanho | Baixa: exige download de varios GB e GPU/RAM; nao recomendado como caminho padrao |

Ressalvas: precos Gemini 3.x Flash dobram em 01/01/2027 (relevante se a avaliacao ocorrer depois). Nao testei qualidade em portugues empiricamente; so a documentacao oficial dos modelos Claude declara suporte multilingue. Um teste real de poucas conversas e obrigatorio na fase 6.

Custo estimado por conversa: ~6 mil tokens de entrada (politicas + historico + tools) e ~500 de saida. Com `claude-haiku-5-5`: ~US$0,001; com `gpt-6-luna`: ~US$0,001. Custo e irrelevante; **o fator decisivo e a chave do avaliador**.

Decisao: dois adaptadores reais bastam: (1) **Anthropic SDK** e (2) **cliente compativel com OpenAI** (cobre OpenAI e, por endpoint compativel, Gemini/Groq/Ollama via `base_url` **[compatibilidade a confirmar nas docs de cada um antes de prometer no README]**). Padrao sugerido: Anthropic `claude-haiku-5-5` (ou Sonnet para qualidade); Gemini como rota gratuita documentada. Tudo configuravel em `app/core/config.py` via `.env`.

## (d) PDF e retrieval

| PDF lib | Facilidade | Licenca | Instalacao | Qualidade | Adequacao |
|---|---|---|---|---|---|
| PyMuPDF | 5 | **AGPL** ou comercial (docs oficiais) | wheel, sem deps de sistema **[nao verificado]** | Mais rapida (8 s vs 101 s do PyPDF2 no benchmark oficial dos autores) | Boa, mas AGPL e risco para entrega/reuso; velocidade irrelevante para 180 KB |
| pypdf | 5 | Livre (BSD, **[nao verificado na pagina]**) | Python puro | Suficiente p/ texto simples | **Preferida**: leve, sem copyleft; validar contra `politicas_extraido.txt` |

| Retrieval | Facilidade | Custo | Deps/ops | Risco de erro | Adequacao |
|---|---|---|---|---|---|
| Contexto completo (12,7 KB) | 5 | ~4 mil tokens/chamada | Nenhuma | Minimo: nada e perdido | **5** |
| BM25 (`rank-bm25`) | 4 | 0 | Pequena, mas ultima release em 02/2022 (0.2.2), mantenedor unico | Medio: perda de contexto por chunking, PT sem stemming | 3 - so se politicas crescerem |
| Embeddings + FAISS/Chroma | 2 | Chamadas de embedding + 2a chave | Alta | Medio-alto | 1 - desproporcional |

Decisao: **pypdf + contexto completo**, segmentado por secoes (titulo/numeracao) para permitir citar a secao na resposta. Ferramenta `buscar_politica(topico)` pode devolver a secao inteira por busca lexical simples em Python (sem lib extra). O texto do PDF e tratado como dado: delimitado e marcado como nao confiavel no prompt (regra 4).

## (e) Interface

| Opcao | Facilidade p/ avaliador | Deps | Testabilidade | Adequacao |
|---|---|---|---|---|
| CLI (loop `input()`) | 5 | 0 | Alta (stdin/stdout, MockLLM) | **5** - plano de fases ja define CLI |
| Streamlit | 4 | Pesada | Baixa | 2 - bonus opcional; nao pude confirmar API de chat nas docs consultadas |
| FastAPI | 3 | Media | Alta | 1 - sem requisito de API |

Decisao: **CLI**. Streamlit so como extra se sobrar tempo, sem tocar o nucleo.

## (f) Persistencia

| Opcao | Facilidade | Ops | Valor | Adequacao |
|---|---|---|---|---|
| Memoria de sessao (lista em processo) | 5 | Nenhuma | Suficiente para conversa multi-turno | **5** |
| SQLite (historico/logs) | 3 | Arquivo local, stdlib | Auditoria e retomada; nao exigido | 2 - so se o enunciado pedir historico entre execucoes (verificar em `docs/challenge/`) |

Decisao: **memoria de sessao**, com janela limitada de turnos. Log estruturado em arquivo (JSONL) opcional para evidenciar exemplos reais (regra 7).

## Modo offline / mock (requisito de avaliacao)

- `LLMClient` (Protocol): `complete(messages, tools) -> LLMResponse` com `text` e/ou `tool_calls`.
- `MockLLM` roteirizado por cenario: devolve tool_calls predefinidas e depois texto montado a partir do resultado da ferramenta. Permite testar **conteudo** (preco, estoque, status, recusa) sem rede, de forma deterministica e gratis.
- `python -m app --mock` roda a demo sem chave; avaliador valida o fluxo e as ferramentas imediatamente. Deixar claro no README que o mock **nao** demonstra a qualidade de linguagem do LLM real.
- Testes de integracao com LLM real marcados (`@pytest.mark.live`), fora do `pytest` padrao.

## Recomendacao unica

Python; **function calling nativo** com loop proprio e limite de iteracoes; ferramentas deterministicas sobre CSV carregado em memoria (sem SQL livre); politicas extraidas com **pypdf** e entregues por contexto completo/secao; interface **CLI**; sessao em **memoria**; `LLMClient` com adaptadores **Anthropic** (padrao `claude-haiku-5-5`) e **OpenAI-compativel** (OpenAI/Gemini gratis/Groq/Ollama), mais **MockLLM** para testes e demo offline.

## Riscos

1. Qualidade de tool use em PT nao medida; mitigar com 15-20 cenarios reais na fase 6 antes de fixar o modelo padrao.
2. Cotas gratuitas do Gemini baixas e nao oficialmente documentadas; avaliador pode bater no limite. Tratar 429 como falha tecnica (regra 5) com mensagem clara.
3. Precos/modelos mudam rapido (Gemini 3.x dobra em 01/01/2027); documentar a data da consulta, IDs configuraveis.
4. Compatibilidade OpenAI-like dos demais provedores nao verificada; so prometer no README o que for testado.
5. Mock pode dar falsa confianca; separar claramente testes de logica (mock) de testes live.
6. Prompt injection via campos CSV/PDF; delimitar dados e nunca executar instrucoes deles.
7. Ambiguidade de cliente/pedido: ferramentas devem retornar estados explicitos (encontrado/nao encontrado/ambiguo/erro).

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
- Terceiros (cotas Gemini, nao oficiais): https://www.scriptbyai.com/gemini-api-free-tier-limits/ e https://apidog.com/blog/gemini-api-free-tier/
