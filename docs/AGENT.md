# Orquestrador conversacional e CLI

Código em `app/llm/`, `app/agent/` e `app/interfaces/cli.py`. Execução: `python main.py [--mock] [--debug]`.

## Fluxo de decisão
1. A mensagem é saneada (caracteres de controle fora, máximo de 1000 caracteres; vazia não chama o LLM).
2. O orquestrador monta: prompt do sistema (persona, regras, dados fixos, data atual) + janela da memória + mensagem.
3. Loop (máx. 6 iterações): o LLM responde com texto ou `tool_calls`. Cada chamada vai ao `execute()` do registry (valida argumentos, nunca levanta). Chamadas idênticas no mesmo turno reaproveitam o resultado. O resultado volta ao LLM como `{"tool", "data", "note"}`, marcado como dado.
4. Resposta final: saneada na saída e gravada na memória (só texto do cliente e resposta final).

## Guardrails (em código)
- Preço, estoque, pedido e regras vêm só das ferramentas; o LLM redige.
- Falha técnica de ferramenta (`data_error`, `internal_error`) sem nenhum dado válido no turno: resposta fixa de indisponibilidade com os contatos da loja; o texto do LLM é descartado.
- Falha do LLM (rede, timeout, 429, 401, 5xx, resposta inválida): `LLMError` com categoria, mesma resposta fixa. Limite de iterações: mensagem fixa de "não consegui concluir".
- `get_order_status` só executa se o e-mail/telefone de verificação foi digitado pelo cliente na conversa. Um LLM induzido por injeção não consegue usar dados chutados ou vindos de ferramenta. Após 5 verificações erradas na sessão, a consulta de pedidos é bloqueada (`locked`) e o cliente é encaminhado à loja.
- Saída: e-mail e telefone completos de terceiros são mascarados (os contatos da loja são mantidos); linhas longas do prompt do sistema na resposta são bloqueadas.
- Resultado de ferramenta e texto do manual são dados, nunca instruções (regra no prompt e nota em cada resultado). Ferramentas são somente leitura.
- Memória só em RAM, janela de 20 mensagens, sem resultado bruto de ferramenta; `/limpar` apaga tudo.

## Provedores
`LLM_PROVIDER=gemini|groq|ollama|mock`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL` (`.env.example`). Um único cliente (SDK `openai`) atende Gemini, Groq e Ollama trocando endereço, modelo e chave. Padrão gratuito: Gemini em `https://generativelanguage.googleapis.com/v1beta/openai/`, modelo `gemini-3.5-flash-lite`.

**Verificado na documentação oficial do Gemini (2026-11-01):** o endereço acima; uso com o SDK `openai`; `tools` no formato `type: function` e `tool_choice: "auto"` com o modelo `gemini-3.8-flash` (a página de exemplos); o modelo efetivamente usado e testado é `gemini-3.5-flash-lite`; o suporte às bibliotecas OpenAI é descrito como beta.

**Não verificado:** como o `tool_call_id` é devolvido nos resultados de ferramenta e se há chamadas paralelas nesse endpoint; se o endpoint aceita `type` em lista e `additionalProperties` nos schemas (por precaução o cliente os simplifica antes de enviar); cotas gratuitas atuais; compatibilidade de tool calling de Groq (`openai/gpt-oss-120b`) e Ollama (`qwen3.8`), cujos endereços e modelos padrão vêm da pesquisa de discovery. **Validação com LLM real:** feita com `gemini-3.5-flash-lite` (tool calling funcionou nos 30 cenários; ver `docs/QUALITY.md`); Groq e Ollama não foram testados. Os testes `@pytest.mark.live` rodam só com `LLM_API_KEY` e com `pytest -m live`.

## Modo `--mock`
`MockLLM` é uma demonstração: escolhe a ferramenta por palavras-chave, emite `tool_calls` reais e redige a resposta a partir do que a ferramenta devolveu. Não é um modelo de linguagem e não representa a qualidade de conversa de um LLM real.

## Limites
- O mock cobre as intenções principais (preço, listagem com teto de preço e contexto, pedido, promoções, parcelamento, frete, prazo de arrependimento, políticas, dados da loja) e erra com frases fora desse padrão.
- A verificação do pedido é por substring do que o cliente digitou; mascaramento de contato usa expressões regulares e pode deixar passar formatos incomuns de telefone.
- Sem streaming, sem persistência entre execuções, sem limite de taxa por usuário.
- Falha técnica parcial (uma ferramenta falha, outra funciona) deixa o LLM redigir; a regra de não inventar depende do prompt nesse caso.
