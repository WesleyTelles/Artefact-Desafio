# Orquestrador conversacional e CLI

Código em `app/llm/`, `app/agent/` e `app/interfaces/cli.py`. Execução: `python main.py [--mock] [--debug]`.

## Fluxo de decisão
1. A mensagem é saneada (caracteres de controle fora, máximo de 1000 caracteres; vazia não chama o LLM).
2. O orquestrador monta: prompt do sistema (persona, regras, dados fixos, data atual) + janela da memória + mensagem.
3. Loop (máx. 6 iterações): o LLM responde com texto ou `tool_calls`. Antes de executar, o orquestrador valida a chamada (ferramenta existe, JSON é um objeto, tipos e campos conferem com o schema). Chamada válida vai ao `execute()` do registry (nunca levanta); chamadas idênticas no mesmo turno reaproveitam o resultado. O resultado volta ao LLM como `{"tool", "data", "note"}`, marcado como dado.
4. Argumentos inválidos (JSON malformado ou truncado, não objeto, tipo errado, campo ausente ou extra, ferramenta inexistente) não são executados: voltam ao modelo como erro estruturado (`invalid_arguments` ou `unknown_tool`, com resumo do schema). Há uma correção por ferramenta no turno (`MAX_ARG_CORRECTIONS`); se persistir, o turno termina com resposta fixa pedindo para reformular (`error_category=invalid_arguments`).
5. Resposta final: saneada na saída e gravada na memória (só texto do cliente e resposta final). Cada turno pode gerar uma linha de telemetria (ver abaixo).

## Guardrails (em código)
- Preço, estoque, pedido e regras vêm só das ferramentas; o LLM redige.
- Falha técnica de ferramenta (`data_error`, `internal_error`) sem nenhum dado válido no turno: resposta fixa de indisponibilidade com os contatos da loja; o texto do LLM é descartado.
- Falha do LLM: `LLMError` com categoria (`bad_request`, `auth`, `not_found`, `rate_limit`, `server_error`, `timeout`, `connection`, `bad_response`, `config`, `budget`) e a mesma resposta fixa de indisponibilidade, sem detalhe técnico para o cliente. Limite de iterações: mensagem fixa de "não consegui concluir".
- Orçamento de tempo por turno: `TURN_TIMEOUT_SECONDS` (padrão 60 s). Cada chamada ao LLM recebe só o tempo restante; retry que estouraria o prazo é abandonado; ao esgotar, mensagem própria ao cliente e `turn_timeout` no log. Resposta vazia do provedor ganha uma nova chamada; estrutura inválida não é repetida.
- Retry no cliente (`app/llm/openai_compat.py`): só para `rate_limit`, `server_error`, `timeout` e `connection`; até `LLM_MAX_ATTEMPTS` chamadas por pedido (padrão 3, de 1 a 10), espera exponencial (base 1 s, teto 8 s) com jitter de 50% a 100%, e `Retry-After` numérico respeitado até 10 s. `auth`, `not_found`, `bad_request`, `bad_response` e `config` não são repetidos. Mensagens de erro nunca levam chave nem corpo da resposta.
- Dica ao operador (stderr, nunca ao cliente): para `auth`, `not_found`, `bad_request`, `config` e `connection` a CLI imprime `[operador] <categoria>: <dica>` (por exemplo verificar `LLM_API_KEY`); com `--debug`, a categoria técnica de qualquer falha aparece como `[operador] falha técnica: <categoria>`.
- `get_order_status` só executa se o e-mail/telefone de verificação foi digitado pelo cliente na conversa. Um LLM induzido por injeção não consegue usar dados chutados ou vindos de ferramenta. Após 5 verificações erradas na sessão, ou 5 no mesmo pedido, a consulta é bloqueada (`locked`) e o cliente é encaminhado à loja. `/limpar` zera a memória e o contador da sessão, mas o bloqueio por pedido vale pelo processo (reiniciar a conversa não dá novas tentativas de adivinhar a verificação de um pedido).
- Saída: e-mail e telefone completos de terceiros são mascarados (os contatos da loja são mantidos); linhas longas do prompt do sistema na resposta são bloqueadas.
- Resultado de ferramenta e texto do manual são dados, nunca instruções (regra no prompt e nota em cada resultado). Ferramentas são somente leitura.
- Memória só em RAM, janela de 20 mensagens, sem resultado bruto de ferramenta; `/limpar` apaga a memória (e zera o contador da sessão, ver acima).
- Conflitos de dados: `search_products` e `check_product_availability` devolvem `data_conflicts` e, com um único produto, `details`; o prompt manda não afirmar o ponto em conflito e encaminhar a um atendente (ver `docs/DATA_QUALITY.md`).

## Telemetria (log JSONL) e `--debug`
- `EMPORIO_LOG_FILE=<caminho>` (ambiente ou `.env`) liga um log com uma linha por turno: `ts`, `session_id`, `turn_id`, `tools` (nome, status, `cached`, `duration_ms`), `llm_calls`, `llm_attempts`, `latency_ms`, `tokens` (null se o provedor não informa), `failed`, `error_category` e `intent` (derivada da primeira ferramenta; omitida sem ferramenta). Nunca grava texto do cliente, e-mail, telefone nem argumentos. Desligado por padrão; falha ao gravar não derruba o atendimento. Código: `app/core/telemetry.py`.
- `--debug` mostra as ferramentas chamadas com os argumentos mascarados (e-mails e telefones; o campo `verification` é mascarado por inteiro) e a categoria técnica das falhas.

## Provedores
`LLM_PROVIDER=gemini|groq|ollama|mock`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL` (`.env.example`). Um único cliente (SDK `openai`) atende Gemini, Groq e Ollama trocando endereço, modelo e chave. Padrão gratuito: Gemini em `https://generativelanguage.googleapis.com/v1beta/openai/`, modelo `gemini-3.5-flash-lite`.

**Verificado na documentação oficial do Gemini (2026-11-01):** o endereço acima; uso com o SDK `openai`; `tools` no formato `type: function` e `tool_choice: "auto"` com o modelo `gemini-3.8-flash` (a página de exemplos); o modelo efetivamente usado e testado é `gemini-3.5-flash-lite`; o suporte às bibliotecas OpenAI é descrito como beta.

**Não verificado:** como o `tool_call_id` é devolvido nos resultados de ferramenta e se há chamadas paralelas nesse endpoint; se o endpoint aceita `type` em lista e `additionalProperties` nos schemas (por precaução o cliente os simplifica antes de enviar); cotas gratuitas atuais; compatibilidade de tool calling de Groq (`openai/gpt-oss-120b`) e Ollama (`qwen3.8`), cujos endereços e modelos padrão vêm da pesquisa de discovery. **Validação com LLM real:** feita com `gemini-3.5-flash-lite` (120 execuções em 40 cenários, ver `docs/EVALUATION.md`; a rodada anterior, de 30 cenários, está em `docs/QUALITY.md`); Groq e Ollama não foram testados. Os testes `@pytest.mark.live` rodam só com `LLM_API_KEY` e com `pytest -m live`.

## Modo `--mock`
`MockLLM` é uma demonstração por intenções: normaliza o texto, divide perguntas compostas, classifica cada trecho por listas de sinônimos e regras, extrai parâmetros (categoria, teto e piso de preço, número do pedido, e-mail ou telefone, valor, data), emite `tool_calls` reais e redige a resposta só a partir do que as ferramentas devolveram (not_found, ambiguous, error, locked e verification_failed são refletidos como tal). Quando não entende, pede para reformular. Não é um modelo de linguagem e não representa a qualidade de conversa de um LLM real.

## Limites
- O mock cobre as intenções principais (preço, listagem com teto de preço e contexto, pedido, promoções, parcelamento, frete, prazo de arrependimento, políticas, dados da loja) e erra com frases fora desse padrão. Limitações listadas em `app/llm/mock.py`: sinônimos fora das listas caem em "pode reformular?"; só reaproveita a categoria e o pedido/e-mail do histórico ("e o preço dele?" não é resolvido); em pergunta composta cada trecho vira no máximo uma ferramenta; política mostra só o primeiro resultado do manual.
- A verificação do pedido é por substring do que o cliente digitou; mascaramento de contato usa expressões regulares e pode deixar passar formatos incomuns de telefone.
- Sem streaming, sem persistência de conversa entre execuções, sem limite de taxa por usuário. O bloqueio por pedido vale por processo.
- Só o Gemini foi testado; a cota gratuita é baixa e o retry reduz, mas não elimina, a indisponibilidade.
- Falha técnica parcial (uma ferramenta falha, outra funciona) deixa o LLM redigir; a regra de não inventar depende do prompt nesse caso.
