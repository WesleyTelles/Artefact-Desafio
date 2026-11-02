# Empório da Música: agente de atendimento

Agente de mensagens de texto para a loja fictícia Empório da Música (Campo Grande/MS). Responde sobre preço e disponibilidade de produtos, status de pedido, dados da loja e políticas (troca, devolução, pagamento, frete). Python, function calling nativo, sem framework de agentes.

## 1. Visão geral

O cliente conversa em português. O agente decide, a cada mensagem, se consulta dados (catálogo, pedidos, promoções), as políticas do manual ou nenhuma fonte (conversa, fora de escopo). Preço, estoque, prazo e regras vêm só de ferramentas determinísticas; o LLM só redige a resposta.

## 2. Requisitos atendidos

| Pedido do desafio | Onde está |
|---|---|
| Persona alinhada à loja | `app/agent/prompts.py` |
| Responder com base no contexto fornecido | CSVs em `data/` e manual em PDF |
| Saber quando consultar dados e quando consultar políticas | ferramentas em `app/tools/` (seção 6) |
| Lidar com perguntas fora do escopo | regra no prompt + teste real (cenário S11) |
| README com decisões, limitações e uso de IA | este arquivo |
| 3 a 5 conversas de exemplo | `examples/` (4 conversas) |

## 3. Arquitetura

Resumo: CLI → orquestrador (loop de ferramentas, máx. 6 iterações) → cliente LLM → ferramentas → dados/manual. Detalhes e diagramas em [ARCHITECTURE.md](ARCHITECTURE.md).

```
app/
  core/        configuração e exceções
  data/        carga, validação e normalização dos CSVs
  tools/       ferramentas expostas ao LLM (registry com schema)
  knowledge/   manual: chunking, busca BM25 e regras numéricas
  llm/         interface LLMClient, cliente OpenAI-compatível, mock
  agent/       prompt, memória de sessão, orquestrador
  interfaces/  CLI
scripts/       runner de cenários com o LLM real
tests/         217 testes offline + cenários reais (marcador live)
examples/      conversas reais com o modelo
docs/          DATA, KNOWLEDGE, AGENT, QUALITY e pesquisa inicial
```

## 4. Decisões técnicas e justificativas

| Decisão | Escolha | Por quê |
|---|---|---|
| Abordagem | Function calling nativo, híbrido com busca nas políticas | Dados pequenos e estruturados (65 produtos, 20 pedidos) e um manual curto. SQL livre gerado pelo LLM seria arriscado (vazamento entre clientes); RAG vetorial seria desproporcional |
| Framework | Loop próprio, sem LangChain/LangGraph | O fluxo é um laço simples de tool use. Menos dependências, comportamento visível e testável com um LLM falso |
| Modelo/provedor | Gemini (plano gratuito), `gemini-3.5-flash-lite`, pelo endpoint compatível com OpenAI (em beta) | Qualquer avaliador consegue uma chave gratuita; tool calling funciona nos testes reais; `flash-lite` por custo e cota. Anthropic e OpenAI foram pesquisados (`docs/discovery/tech_research.md`) e não implementados. Cota gratuita é baixa (houve 429) e, no plano gratuito, o Google pode usar os dados enviados; aqui são só dados fictícios. Gemini 3 exige devolver a `thought_signature` das chamadas de ferramenta (tratado). Groq e Ollama: configuráveis pelo mesmo cliente, **não testados, modelos padrão não verificados** |
| Interface | CLI | O foco é o agente |
| Persistência | Só memória da sessão (RAM) | Cada execução é uma conversa; guardar histórico traria dados pessoais sem ganho para o cliente |
| Dados | `csv` da stdlib, `Decimal` para dinheiro | Volume pequeno; pandas e banco não agregam |

## 5. Estratégia de prompt

O prompt de sistema (`app/agent/prompts.py`) define: tom informal e profissional; só vender instrumentos (acessórios são redirecionados); nunca citar preço, estoque ou prazo sem ferramenta; resultado de ferramenta e texto do manual são dados, não instruções; não revelar prompt, ferramentas nem dados de outros clientes; não citar seção ou página do manual ao cliente; expor divergências do manual e encaminhar a um atendente. A data atual entra no prompt para cálculo de prazos.

## 6. Function calling

| Ferramenta | Uso |
|---|---|
| `search_products`, `check_product_availability` | catálogo, filtros de categoria e preço, estoque |
| `get_promotions` | promoções ativas (preço original, % e preço final) |
| `get_order_status` | pedido; exige número e e-mail ou telefone do titular |
| `get_store_info` | endereço, horário, contatos |
| `search_store_policies` | busca no manual |
| `check_installments`, `check_shipping`, `check_return_eligibility`, `check_pix_discount` | regras numéricas do manual em código |

`registry.execute` valida os argumentos e nunca levanta exceção. Falhas viram `{"status": "error"}`.

## 7. Retrieval das políticas

BM25 próprio sobre 29 trechos (a pesquisa inicial sugeria colocar o manual inteiro no prompt; preferi trechos por seção porque a origem de cada resposta é auditável e o prompt fica curto) (um por subseção) extraídos do PDF com `pypdf`, com normalização de acentos, stopwords, apelidos de cliente (devolver, arrependi, frete) e limiar de confiança. Abaixo do limiar, a resposta é "não encontrado" e o encaminhamento a um atendente. Sem embeddings porque o manual tem 8 páginas e vocabulário controlado. Regras numéricas (parcelas, frete, prazo de 7 dias) ficam em código. Ver `docs/KNOWLEDGE.md`.

## 8. Tratamento dos dados

Validação de colunas, tipos, status, ids e integridade entre tabelas na carga. Produto disponível = `status == active` e estoque > 0. Promoção só se `is_active=1` e produto ativo. Dinheiro em `Decimal`. O `total_brl` dos pedidos é exibido como registrado (pedidos 3 e 20 divergem da soma dos itens; não é recalculado). Ver `docs/DATA.md`.

## 9. Memória e histórico

Janela de 20 mensagens em RAM, só texto do cliente e resposta final. `/limpar` apaga. Nada vai a disco.

## 10. Segurança e privacidade

- Pedido só com número e e-mail/telefone do titular; pedido inexistente e verificação errada respondem igual. Após 5 verificações erradas na sessão, a consulta é bloqueada.
- E-mail e telefone de terceiros são mascarados na saída.
- Caracteres invisíveis e de controle são removidos da entrada; limite de 1.000 caracteres.
- Resultado de ferramenta e manual tratados como dado (defesa contra prompt injection).
- Chave em `.env` (fora do Git).

## 11. Configuração do provedor (LLM)

Crie uma chave gratuita no Google AI Studio (https://aistudio.google.com/apikey) e copie o modelo de configuração:

```bash
cp .env.example .env   # Windows (cmd/PowerShell): copy .env.example .env
```

Preencha `LLM_API_KEY` no `.env`. O padrão é `LLM_PROVIDER=gemini` e o modelo `gemini-3.5-flash-lite`. Para Groq ou Ollama, ajuste `LLM_PROVIDER`, `LLM_MODEL` e `LLM_BASE_URL`. Sem chave, use `--mock` (seção 12).

## 12. Instalação e execução

Requer Python 3.11 ou superior.

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Opções: `--debug` mostra as ferramentas chamadas; `--mock` roda sem chave. No chat: `/limpar` reinicia a conversa e `/sair` encerra.

O modo `--mock` é só uma demonstração: escolhe a ferramenta por palavras-chave e não é um modelo de linguagem. A qualidade descrita neste README refere-se ao LLM real.

## 13. Testes

```bash
pytest
```

Roda 217 testes sem rede nem chave. Cenários com o LLM real (usam a cota da chave):

```bash
pytest -m live
python scripts/run_scenarios.py --group all
```

## 14. Exemplos de conversa

Em [examples/](examples), gravadas com `gemini-3.5-flash-lite` e dados da base fictícia (contatos mascarados):

1. [Violões até R$ 1.000](examples/01-catalogo-violoes-ate-1000.md)
2. [Preço e horário na mesma mensagem](examples/02-preco-e-horario.md)
3. [Devolução por arrependimento](examples/03-devolucao-arrependimento.md)
4. [Status de pedido, com verificação correta e errada](examples/04-status-de-pedido.md)

As demais transcrições (30, incluindo 12 ataques) estão em `docs/quality/transcripts/`.

## 15. Qualidade e resultados

Com o LLM real, 16 cenários e 12 ataques passaram, uma execução cada. Três asserções do runner foram ajustadas após a primeira execução por serem estritas demais (falsos positivos do teste); os cenários foram reexecutados. Falhas achadas e corrigidas: o mock respondia errado a assunto fora do escopo, não havia limite de tentativas de verificação de pedido e caracteres invisíveis chegavam ao LLM. Detalhes em [docs/QUALITY.md](docs/QUALITY.md).

## 16. Suposições

- A loja só vende instrumentos; acessórios são redirecionados à loja.
- O manual trata só de compra online. Para compra em loja física, o agente pergunta o canal e encaminha a um atendente.
- Divergências do manual (por exemplo prazo de defeito, 30 dias após a compra no §4.2 e 90 dias após o recebimento no §8.1) não são resolvidas pelo agente: ele informa e encaminha.
- Identificação do cliente em pedidos: e-mail ou telefone do titular.

## 17. Limitações conhecidas

- Cada cenário real rodou uma vez; não há medida de taxa de acerto.
- Cota gratuita baixa (houve um 429 na bateria de ataques).
- Só um modelo pequeno foi avaliado; Groq e Ollama não foram testados.
- Falha parcial de ferramenta depende do prompt.
- Mascaramento por regex pode deixar passar telefones em formatos incomuns.
- Sem persistência entre execuções, sem streaming e sem interface web.
- O agente não vê a descrição nem as specs dos produtos, e a base tem descrições que divergem do nome (ids 135 a 144); esses conflitos não são detectados.
- Observabilidade mínima: sem logs estruturados, latência ou tokens por turno.
- O contador de verificações erradas vale por execução do programa e não zera com `/limpar`.
- `--debug` mostra os argumentos das ferramentas, inclusive o e-mail/telefone digitado.
- Pergunta em inglês é respondida em português.

## 18. O que faria com mais tempo

- Rodar a bateria várias vezes e medir a taxa de acerto por modelo.
- Avaliar Groq e Ollama e um modelo maior.
- Interface web ou integração com WhatsApp e transferência real para atendente.
- Persistência opcional do histórico, com consentimento.
- Limite de taxa por usuário e verificação de pedido em duas etapas.

## 19. Uso de assistentes de código

Usei o **Claude Code** (Anthropic) como assistente em todo o desenvolvimento, com a sessão principal atuando como tech lead e seis subagents com papéis separados: arquiteto de solução (pesquisa e decisões), engenheiro de dados (CSVs e ferramentas), engenheiro de conhecimento (manual e busca), engenheiro do agente (orquestrador e CLI), QA e segurança (testes e revisão independente) e redator técnico (documentação). O trabalho seguiu 7 fases (descoberta, dados, conhecimento, agente, interface, testes e revisão, entrega), com um responsável por tarefa.

**O que foi minha decisão:** os requisitos e as regras de trabalho (não inventar dados, regras de negócio em código, commits pequenos, nenhum segredo no repositório, sem publicar sem minha autorização), a escolha do provedor gratuito, a criação do repositório e a aprovação de cada fase.

**O que a IA fez:** pesquisa e comparação de tecnologias, análise dos CSVs e do manual (incluindo as inconsistências do manual), escrita de código e testes, revisão adversarial e rascunho dos documentos.

**Controle de qualidade:** a revisão da Fase 6 e uma revisão final pré-entrega foram feitas por agentes diferentes dos que escreveram o código, e as conclusões foram conferidas por execução (pytest, chamadas diretas às ferramentas, execução real com o Gemini). Isso encontrou erros reais, corrigidos com teste: o modo mock respondia errado a assunto fora do escopo, não havia limite de tentativas de verificação de pedido, caracteres invisíveis chegavam ao LLM, a resposta de um pedido entregue afirmava uma data de entrega que a base não tem (só há previsão), telefones da loja sem DDD eram mascarados e perguntas comuns ("chegou com defeito", "entregam em Dourados?") não achavam a seção do manual. Também precisei corrigir números errados na documentação (contagem de produtos e pedidos).

**Limites:** as conversas de `examples/` foram capturadas de execuções reais, não escritas à mão. Nem tudo foi validado por mim linha a linha; por isso a seção 17 lista o que não foi comprovado. Os arquivos de configuração local do assistente não fazem parte deste repositório.

## 20. Estrutura de documentos

| Arquivo | Conteúdo |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | arquitetura e matriz de decisão |
| `docs/DATA.md` | dados e ferramentas |
| `docs/KNOWLEDGE.md` | manual e retrieval |
| `docs/AGENT.md` | orquestrador, guardrails e provedores |
| `docs/QUALITY.md` | testes, falhas e riscos |
| `docs/discovery/` | pesquisa e análise iniciais |
