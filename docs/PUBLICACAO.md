# Preparação para publicação do repositório

Auditoria de 2026-11-02 (estado local: branch `main`, 53 commits; `origin/main` tem 46, o local está 7 à frente).
Nada aqui foi executado contra o remoto. Todo comando marcado **exige aprovação** deve ser rodado só pelo dono do repositório.
Verificador: `python scripts/check_release.py [--history] [--public [--allow-csv]]` (somente leitura, exit 1 se houver pendência).

## 1. Resultado da auditoria

| Item | Resultado |
|---|---|
| Segredos na árvore e no histórico | Nenhum. Padrões `AIza`, `sk-`, `gsk_`, `Bearer`, `ghp_`: 0 ocorrências na árvore e em 53 revisões. O valor da chave do `.env` (comparado em memória, não impresso): 0 arquivos, 0 revisões, `git log -S` = 0. |
| `.env` | Existe localmente, ignorado pelo `.gitignore`, nunca rastreado. `.env.example` só tem nomes de variáveis. |
| `.claude/` e `CLAUDE.md` | Em `.git/info/exclude` (não no `.gitignore`, portanto não viajam com o clone). Nenhum caminho com `claude` ou `.env` em nenhuma revisão. |
| Autoria | 53 commits, todos de um único autor/committer (Wesley Telles, e-mail pessoal). Nenhum trailer `Co-Authored-By`/`Signed-off-by`. O e-mail do autor ficará público no histórico. |
| PII fora de `data/` | Nenhum cliente real. Aparecem só dados da base fictícia: `docs/discovery/data_profile.md` (1 e-mail e 3 nomes de clientes da base), 7 arquivos de `tests/` com e-mails/telefones de clientes do `customers.csv` (usados como fixtures: 5 telefones e vários e-mails). Transcripts e examples não contêm nome, e-mail nem telefone de cliente. Telefones/e-mail da loja (`contato@emporiodamusica.com.br`, (67) 3341-4444) vêm do manual e são dados públicos da loja fictícia. |
| Menções internas | `README.md` (seção 19) cita Claude Code, "tech lead" e subagents (divulgação honesta de uso de IA, intencional). `docs/discovery/*` cita "Tech Lead", nomes de agentes (`ai-solution-architect`, `rag-knowledge-engineer`) e o PDF "Uso restrito". `app/knowledge/loader.py:174` tem o termo "documento interno" só como alias de busca. Opcional: neutralizar `docs/discovery/` (ver 4). |
| Telemetria `app/core/telemetry.py` | Por leitura: grava só session_id, turn_id, nome/status/duração das ferramentas, tentativas, latência, tokens, categoria de erro, intenção. Não grava texto do cliente nem argumentos. Desligada por padrão (`EMPORIO_LOG_FILE`); `logs/` está no `.gitignore`. Falha de escrita não derruba o atendimento. |
| Teste offline `--mock --debug --log` | Entrada com e-mail `lucas.mendes@jmail.com`, telefone `(67) 99812-3456` e nome. Saída `--debug` mostrou `"verification": "l***@jmail.com"` (mascarado). JSONL com 3 linhas: 0 ocorrências de e-mail, telefone ou nome (grep). Sem chamada de LLM. |
| `.gitignore` | Cobre `.env`, `.venv/`, caches, IDE, `logs/`. Sem lacunas encontradas. Não cobre `.claude/` e `CLAUDE.md` (cobertos só localmente em `.git/info/exclude`). Sugestão opcional: adicionar ambos ao `.gitignore` para blindar outros clones. |

### Achados

**Crítico (decisão antes de tornar público)**
1. Três arquivos restritos versionados, também presentes no histórico: `data/políticas_da_loja.pdf` ("Documento interno - Uso restrito"), `docs/challenge/politicas_extraido.txt` (mesmo conteúdo) e `docs/challenge/desafio_tecnico_ai_eng_artefact.pdf` (enunciado). Sem autorização da Artefact, tornar o repositório público redistribui esses arquivos.
2. O conteúdo do manual também aparece derivado em arquivos "publicáveis": `app/knowledge/loader.py` (marcadores e trechos de seção), `docs/KNOWLEDGE.md`, `docs/discovery/policy_analysis.md`, transcripts e `examples/` (citam regras e valores do manual). Remover apenas o PDF/TXT não elimina isso; se a Artefact negar a redistribuição do manual, esses textos também precisam de revisão.

**Importante**
3. O repositório não funciona sem os arquivos restritos. (Atualização: o README agora traz a subseção "Dados necessários", na seção 12, com nomes exatos, `data/` e `EMPORIO_DATA_DIR`; ver 3 e 5.)
4. Divergência de contagem: o pedido citava 48 commits; o real é 53 local / 46 remoto. Reescrever histórico remoto afetaria 46 commits já enviados.
5. O e-mail pessoal do autor ficará exposto em todos os commits (aceitável se for intencional; reescrita só se desejado).

**Opcional**
6. Neutralizar referências internas em `docs/discovery/` (nomes de agentes, "Tech Lead"); decidir se `docs/discovery/` e `docs/quality/transcripts/` devem ir ao repositório público.
7. Adicionar `.claude/` e `CLAUDE.md` ao `.gitignore`.
8. `data_profile.md` cita um e-mail e nomes da base fictícia; se os CSVs não forem publicados, redigir como "cliente A/B".

## 2. Classificação dos 122 arquivos rastreados

### Publicáveis (sem restrição identificada)
| Grupo | Justificativa | Caminhos |
|---|---|---|
| Código do app (33) | Código próprio, sem segredos, telemetria sem PII | `app/**` (inclui `app/knowledge/loader.py`, ver ressalva abaixo), `main.py` |
| Configuração (4) | Sem valores secretos | `.env.example`, `.gitignore`, `pytest.ini`, `requirements.txt` |
| Documentação própria | Texto autoral | `README.md`, `ARCHITECTURE.md`, `docs/AGENT.md`, `docs/DATA.md`, `docs/DATA_QUALITY.md`, `docs/QUALITY.md`, `docs/PUBLICACAO.md` |
| Scripts (2) | Código próprio | `scripts/audit_products.py`, `scripts/run_scenarios.py`, `scripts/check_release.py` |
| Testes (29) | Código próprio; usam dados da base como fixtures (ver 3) | `tests/**` |

### Dependem de autorização da Artefact
| Grupo | Justificativa | Caminhos |
|---|---|---|
| CSVs fornecidos (6) | Base do desafio (fictícia), redistribuição não autorizada explicitamente | `data/desafio_tecnico_ai_eng - {categories,customers,order_items,orders,products,promotions}.csv` |
| Docs que citam o manual | Reproduzem regras/valores do manual restrito | `docs/KNOWLEDGE.md`, `docs/discovery/policy_analysis.md`, `docs/quality/transcripts/*.md` (30), `examples/*.md` (4), `app/knowledge/loader.py` (marcadores de seção) |
| Documentos de pesquisa interna | Citam papéis/agentes internos e o status "Uso restrito" | `docs/discovery/data_profile.md`, `docs/discovery/tech_research.md`, `docs/discovery/policy_analysis.md` |

### Não publicáveis sem autorização expressa
| Grupo | Justificativa | Caminhos |
|---|---|---|
| Manual interno | Marcado "Documento interno - Uso restrito" | `data/políticas_da_loja.pdf`, `docs/challenge/politicas_extraido.txt` |
| Enunciado | Material do processo seletivo | `docs/challenge/desafio_tecnico_ai_eng_artefact.pdf` |

Fora do Git (nunca devem entrar): `.env`, `.claude/`, `CLAUDE.md`, `.venv/`, `logs/`, caches.

## 3. Dependência de `data/` e do PDF (medido)

Método: `git archive HEAD` em diretórios temporários, remoção seletiva dos arquivos, `pytest --ignore=tests/live` com `LLM_PROVIDER=mock`, sem chave. Linha de base: **429 passam**, 30 testes `live` desmarcados (precisam de LLM real).

| Cenário | Falhas + erros | Observação |
|---|---|---|
| Sem o PDF (fica o `.txt`) | 3 falhas (`test_carrega_do_pdf_com_oito_paginas`, `test_pdf_original_existe`, `test_dados_originais_nao_mudam_apos_auditoria_e_ferramentas`) | O loader cai no `.txt` com aviso; o app funciona. |
| Sem PDF e sem `.txt` | 53 falhas (`test_retriever` 29, `test_mock_llm` 10, `test_knowledge_loader` 9, `test_policy_tools` 4, `test_quality` 1) | CSVs presentes, tudo de produto/pedido passa. |
| Sem CSVs (PDF presente) | 64 falhas + 69 erros (133, 31%) | |
| Sem nada (CSVs, PDF e `.txt`) | 116 falhas + 69 erros (185, 43%); 244 passam | Os 244 são lógica pura (llm client, resiliência, telemetria, CLI parcial). |
| `EMPORIO_DATA_DIR` = pasta vazia | 58 falhas + 69 erros (127) | Medido na data da auditoria, quando a variável só movia os CSVs. **Atualização:** o commit posterior "lê o manual da pasta de dados configurada" faz o PDF também vir de `EMPORIO_DATA_DIR`; esta linha não foi remedida. |
| `EMPORIO_DATA_DIR` = pasta só com CSVs | 429 passam | |

Arquivos de teste que dependem dos CSVs: `test_loader`, `test_orders`, `test_products`, `test_promotions`, `test_quality`, `test_registry`, `test_adversarial`, `test_agent_flows`, `test_agent_guardrails`, `test_cli`, `test_mock_llm`, `test_scenario_checks`. Do manual: `test_knowledge_loader`, `test_retriever`, `test_policy_tools`, `test_mock_llm`, `test_quality`.

**Mensagens quando faltam arquivos**
- CSVs ausentes: `main.py` encerra com `Erro ao carregar os dados da loja: Arquivo não encontrado: <caminho completo do primeiro CSV>`. Clara quanto ao arquivo, mas não diz onde obtê-lo nem lista os demais.
- Manual ausente (PDF e TXT): o app inicia normalmente (carga preguiçosa); só a primeira pergunta de política falha, e o cliente recebe "Não consegui consultar isso agora... fale com a loja pelo (67) 3341-4444". O erro técnico vai só para o log (`Manual indisponível: ...`). Para o avaliador isso parece falha intermitente, sem pista de configuração. **Sugestão (fora do escopo desta tarefa, não alterado): verificação de arquivos na partida com mensagem "coloque X em data/".**
- (Estado na data da auditoria; o README foi atualizado depois e agora documenta nomes exatos e `EMPORIO_DATA_DIR` na seção 12, subseção "Dados necessários".)

## 4. Opções de distribuição

**A. Publicar tudo como está (somente com autorização por escrito da Artefact).**
Prós: nenhuma alteração, reproduzível ao clonar, histórico preservado. Contras: risco jurídico/contratual se não houver autorização; expõe enunciado e manual interno.

**B. Código e docs públicos; restritos fora do repositório público.** Documentar onde o avaliador coloca os arquivos.
Prós: remove o risco principal; mantém o trabalho visível. Contras: o avaliador precisa dos arquivos que a Artefact já tem; testes quebram sem eles (ver 3); o conteúdo derivado do manual em docs/transcripts ainda precisa de decisão; se feito com `git rm --cached` no mesmo repositório, **os arquivos continuam no histórico dos 53 commits** (qualquer um pode recuperá-los com `git log`/`git show`), portanto não resolve a redistribuição.
Variantes:
- B1. `git rm --cached` + `.gitignore` no repositório atual: simples, mas não remove do histórico. Só serve se o repo permanecer privado ou se a exposição histórica for aceita. Inadequado para tornar público.
- B2. **Repositório novo a partir do estado atual sem os restritos (recomendado dentro de B)**: histórico novo de 1 commit (ou da árvore limpa), o privado atual vira arquivo. Prós: zero risco de vazamento histórico, sem reescrita do remoto. Contras: perde os commits pequenos (o desafio pode valorizar histórico; mitigável anexando o privado ao avaliador sob pedido). Alternativa B2': `git checkout --orphan` na mesma cópia local, mas o remoto existente mantém o histórico antigo (visibilidade pública do repo expõe tudo), então exigiria apagar/recriar o repo remoto.
- B3. Reescrever o histórico (`git filter-repo --invert-paths --path ...`) e force-push: preserva commits, mas altera os 53 hashes, exige force-push (proibido sem autorização no CLAUDE.md), invalida clones/forks e o 46 já enviado; o GitHub pode manter objetos em cache/PRs. Risco alto; só com aprovação expressa e backup.

**C. Fixtures sintéticas para testes públicos.** Criar `tests/fixtures/` com mini-CSVs e um mini-manual fictício e apontar os testes para eles.
Esforço estimado: 12 arquivos de teste dependem dos CSVs e 5 do manual (cerca de 185 de 429 testes, 43%). Muitos asserts usam IDs/valores/nomes reais (ex.: pedidos, e-mails de clientes). Estimativa: 1 a 2 dias para fixtures + reescrita de asserts e retestar; inclui mini-manual com a mesma estrutura de seções que `loader.py` espera (8 páginas, marcadores). Prós: testes rodam em qualquer clone; independe de autorização. Contras: não valida os dados reais; trabalho substancial e risco de regressão; o app em si continua precisando dos dados reais para uso.

### Recomendação
1. Perguntar à Artefact (ou conferir o enunciado) se a publicação dos CSVs, do manual e do enunciado é permitida. Se sim por escrito: **A**.
2. Se não houver resposta a tempo: **B2** (novo repositório sem PDF, `.txt` e enunciado; CSVs só se autorizados), manter o privado como arquivo, README com a seção "Dados necessários", e reduzir os trechos do manual em docs/transcripts conforme decisão. **C** como melhoria se sobrar tempo.
3. Antes de qualquer opção, rodar `python scripts/check_release.py --history`.

## 5. O que o avaliador faz após clonar (opção B)

```text
git clone <repo-publico> emporio && cd emporio
python -m venv .venv && .venv\Scripts\activate      # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```
Coloque na pasta `data/` (nomes exatos, com espaços e acentos):
- `desafio_tecnico_ai_eng - categories.csv`, `- customers.csv`, `- order_items.csv`, `- orders.csv`, `- products.csv`, `- promotions.csv`
- `políticas_da_loja.pdf`
Opcional: `docs/challenge/politicas_extraido.txt` (fallback do PDF). Os CSVs podem ficar em outra pasta com `EMPORIO_DATA_DIR=<pasta>`, mas, na data da auditoria, o PDF devia estar em `data/` (hoje `EMPORIO_DATA_DIR` também vale para o PDF).
```text
python main.py --mock               # demonstração sem chave
copy .env.example .env  (preencher LLM_API_KEY)   # para LLM real
python main.py --debug
python -m pytest -q --ignore=tests/live
```
Sem os dados reais, o resultado esperado é 429 testes passando apenas quando todos os arquivos acima existirem (ver tabela da seção 3). O README já traz esta lista na seção 12, subseção "Dados necessários".

## 6. Comandos de publicação (NÃO executados)

Verificação prévia (somente leitura, pode rodar a qualquer momento):
```text
python scripts/check_release.py --history
python scripts/check_release.py --public --allow-csv     # espera falha enquanto o PDF/txt/enunciado estiverem rastreados
```

**Opção A (tudo como está)**
```text
git push origin main                                  # exige aprovação (envia os 7 commits locais)
gh repo edit WesleyTelles/Artefact-Desafio --visibility public --accept-visibility-change-consequences   # exige aprovação
```

**Opção B2 (repositório novo limpo, privado atual preservado como arquivo)**
```text
git clone --mirror . ../Artefact-Desafio-privado.git         # backup local, sem rede
gh repo rename Artefact-Desafio-privado --repo WesleyTelles/Artefact-Desafio   # exige aprovação (renomeia o privado atual)
cd .. && mkdir emporio-publico && cd emporio-publico
git -C "<repo atual>" archive HEAD | tar -x                  # copia só arquivos rastreados
git rm --cached -r data/políticas_da_loja.pdf docs/challenge 2>/dev/null; rm data/políticas_da_loja.pdf   # só na cópia; conferir cada caminho
git init -b main && git add -A && git commit -m "feat: agente de atendimento Empório da Música"
python scripts/check_release.py --public --allow-csv         # deve sair com 0
gh repo create WesleyTelles/Artefact-Desafio --public --source . --push   # exige aprovação
```

**Opção B1 (mesmo repo, não remove do histórico)**
```text
git rm --cached "data/políticas_da_loja.pdf" docs/challenge/politicas_extraido.txt docs/challenge/desafio_tecnico_ai_eng_artefact.pdf   # exige aprovação (altera índice)
printf 'data/políticas_da_loja.pdf\ndocs/challenge/\n' >> .gitignore
git commit -m "chore: remove materiais restritos do rastreamento"                 # exige aprovação
```
Aviso: após isso, o histórico ainda contém os arquivos. Não torne público.

**Opção B3 (reescrita de histórico; alto risco)**
```text
git clone --mirror <repo> backup.git                                   # backup
git filter-repo --invert-paths --path "data/políticas_da_loja.pdf" --path docs/challenge/   # exige aprovação
git push --force origin main                                           # exige aprovação explícita (proibido no CLAUDE.md sem autorização)
```

## 7. Depende da decisão do usuário
- Autorização (ou não) da Artefact para publicar manual, enunciado e CSVs.
- Opção A, B2 ou B3; preservar os 53 commits ou aceitar histórico novo.
- Manter ou não o e-mail pessoal nos commits.
- Manter `docs/discovery/` e `docs/quality/transcripts/` públicos (citam o manual e papéis internos).
- Aprovar mudanças de código/README (aviso de arquivos faltando na partida, seção "Dados necessários"), que esta auditoria não fez.
