# Preparação para publicação do repositório

Fechamento de 2026-11-03. Os números das seções 2 a 4 foram medidos nesta data, com os comandos da seção 7, sobre o estado do repositório antes do commit que registra este documento e o `.gitignore`. A avaliação com Gemini (seção 5) é histórica: não foi repetida. Para conferir o estado no momento da publicação, rode de novo os comandos da seção 7.

## 1. Decisão sobre os materiais da Artefact

O repositório precisa ser público (exigência do enunciado). Decisão do desenvolvedor: manter no repositório, sem alteração, os materiais que a Artefact forneceu para o desafio (6 CSVs, `data/políticas_da_loja.pdf`, o enunciado em `docs/challenge/` e o texto extraído do manual). Não será pedida autorização adicional à empresa. Consequências assumidas:

- O manual traz a marca de documento interno; o README informa que ele é usado só para este desafio.
- Trechos do manual aparecem também em documentos derivados (`docs/KNOWLEDGE.md`, transcrições e exemplos).
- Não será criado outro repositório, nem reescrita de histórico, nem squash, nem dados sintéticos no lugar dos originais.

## 2. Situação atual

| Item | Estado medido |
|---|---|
| Branch | `main` |
| Commits locais | 63 (todos de Wesley Telles, nenhum com `Co-Authored-By`) |
| Commits em `origin/main` | 46 |
| Pendentes de envio | 17, nenhum enviado (0 atrás, 17 à frente de `origin/main`) |
| Remoto | `origin` = `https://github.com/WesleyTelles/Artefact-Desafio.git`, **privado** |
| Árvore de trabalho | `.gitignore` e este documento modificados, preparados e sem commit; sem arquivos não rastreados |
| Arquivos rastreados | 251 (antes do commit desta etapa) |
| Dados originais | `git diff` contra o commit que os adicionou: vazio (CSVs e PDF intactos) |

## 3. Auditorias

| Verificação | Resultado |
|---|---|
| Chaves de API em todas as revisões (`AIza`, `sk-`, `gsk_`, `LLM_API_KEY=` com valor) | 0 ocorrências; `.env` nunca foi rastreado |
| `.claude/` e `CLAUDE.md` rastreados em alguma revisão | nenhum; agora também ignorados pelo `.gitignore` (regras em `.gitignore`, verificadas com `git check-ignore` e em um clone novo), além de `.git/info/exclude` |
| Menções a Claude/Anthropic na árvore | seção de uso de IA do README, comparação de provedores em README/ARCHITECTURE, pesquisa em `docs/discovery/` e este processo de publicação |
| Autoria e e-mail | autor e committer únicos em 63 commits; o e-mail é pessoal (Gmail) e ficará público em todos eles. Só há `user.email` global (sem valor local), então commits novos usariam o mesmo Gmail até a configuração mudar (ver seção 6) |
| Dados pessoais | os clientes que aparecem são os fictícios da base; `examples/` e `docs/evaluation/` não têm e-mail ou telefone de cliente sem máscara |
| Telemetria e `--debug` | sem texto do cliente nem contatos completos (cobertos por testes) |
| `scripts/check_release.py --history` | OK, nenhuma pendência (rodado em 2026-11-03) |
| `scripts/audit_products.py --check` | saída 0 (rodado em 2026-11-03) |
| Chaves (`AIza`, `sk-`, `gsk_`) em todas as revisões | 0 ocorrências; nenhum `.env` rastreado (2026-11-03) |

Cruzamento feito nos 99 e-mails e telefones de `customers.csv` contra todos os arquivos rastreados fora de `data/`: só aparecem em fixtures de teste e documentação, por serem dados fictícios do desafio.

## 4. Testes e validação em ambiente limpo

- Suíte padrão (rodada em 2026-11-03, depois da correção de busca global): 506 passam, 0 falham (eram 477; +29); 46 testes `live` (Gemini real) ficam fora por padrão para não gastar cota.
- Ambiente limpo (repetido em 2026-11-03): `git archive HEAD` em pasta nova, venv novo, `pip install -r requirements.txt` conforme o README, sem `.env`: instalação sem erro, 477 testes passam e `main.py --mock` responde preço, horário, política, início de consulta de pedido (pede número e e-mail ou telefone), fora de escopo e a pergunta de seguimento ("qual deles é o mais barato?"). Em validação anterior, `main.py` sem chave e sem `--mock` falhava com mensagem clara; isso não foi repetido agora.
- Gemini real: duas execuções manuais curtas nesta etapa. Uma respondeu o preço do Takamine GD20 corretamente; na outra, o provedor ficou lento e o orçamento de 60 s do turno devolveu a mensagem de tempo esgotado em vez de travar (comportamento esperado). Observação: o timeout do SDK é por fase, então uma chamada lenta pode ultrapassar um pouco o orçamento antes de a interrupção ser registrada.

## 5. Avaliação com Gemini

Correção de busca global (2026-11-03): `search_products` ganhou `all_categories` e o campo `scope`; ver README (seção 6) e EVALUATION.md (cenários G01-G06, uma execução cada, fora dos números abaixo). Os números das seções 2 a 4 acima foram medidos antes dessa correção, exceto a contagem de testes.

Os números vigentes estão em [EVALUATION.md](EVALUATION.md) e foram recalculados por um revisor independente a partir de `docs/evaluation/runs.jsonl`: 120 execuções (40 cenários × 3), 119/120 bruto e 118/120 ajustado, latência mediana 3,8 s, p95 15,4 s (nearest-rank), 6.335 tokens por execução em média. Não houve nova rodada nesta etapa porque as mudanças (orçamento de tempo, resposta vazia) não alteram o conteúdo das respostas. Três execuções por cenário não são evidência estatística, e o EVALUATION.md lista critérios permissivos e produtos sem cenário real (136, 139, 140, 144).

## 6. Pendências

**Bloqueadores:** nenhum.

**Dependem de decisão do desenvolvedor:**
1. Autorizar o `git push` dos 17 commits pendentes (mais o commit desta etapa, se for feito).
2. Autorizar a mudança de visibilidade para público.
3. Usar ou não o e-mail noreply do GitHub nos commits futuros (os 63 existentes não serão alterados). Procedimento, sem executar: no GitHub, em Settings > Emails, ativar "Keep my email addresses private" e copiar o endereço `ID+usuario@users.noreply.github.com`; depois, no repositório, `git config user.email "<endereço noreply>"` (só neste repositório) ou `git config --global user.email ...`. Isso vale apenas para commits criados depois; os antigos continuam com o Gmail, e removê-lo exigiria reescrever o histórico, o que foi descartado.

Resolvido nesta etapa: `.claude/` e `CLAUDE.md` agora estão no `.gitignore`.

**Melhorias recomendadas:** cenários reais para 136, 139, 140, 144 e para a contagem do prazo de devolução; endurecer os critérios permissivos de `tests/live/scenarios.py`; fixtures sintéticas para cerca de 185 testes que dependem dos dados reais.

## 7. Checklist e comandos

Conferência do estado (somente leitura):

```bash
git status --short
git rev-list --count HEAD
git rev-list --count origin/main
git rev-list --left-right --count origin/main...HEAD
python scripts/check_release.py --history
```

Checklist de publicação:

- [x] README revisado (instalação no início, orçamento por turno, mock)
- [x] Arquitetura documentada e conferida com o código
- [x] Testes aprovados (506)
- [x] Avaliação revisada por revisor independente
- [x] Exemplos de conversas reais (`examples/`, saídas capturadas do Gemini)
- [x] Dados e políticas originais preservados
- [x] Nenhuma credencial na árvore nem no histórico auditado
- [x] Arquivos internos do Claude Code fora do Git (`.gitignore` e `.git/info/exclude`)
- [x] E-mail de autoria auditado (pessoal, ficará público)
- [x] Histórico preservado, sem reescrita
- [x] Instruções de execução testadas em ambiente limpo
- [ ] Commit do `.gitignore` e deste documento (preparados, sem commit)
- [ ] Push dos commits pendentes: **exige autorização**
- [ ] Visibilidade pública: **exige autorização**

Comandos de publicação (NÃO executados; só rodar com autorização expressa):

```bash
git push origin main
```

```bash
gh repo edit WesleyTelles/Artefact-Desafio --visibility public --accept-visibility-change-consequences
```

Depois de tornar público e antes do prazo de entrega, abrir o link em janela anônima para conferir. Pelo enunciado, nada deve ser alterado no repositório após a data e o horário de entrega.
