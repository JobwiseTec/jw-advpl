# plugadvpl

[![PyPI version](https://img.shields.io/pypi/v/plugadvpl.svg?logo=pypi&logoColor=white)](https://pypi.org/project/plugadvpl/)
[![Python](https://img.shields.io/pypi/pyversions/plugadvpl.svg?logo=python&logoColor=white)](https://pypi.org/project/plugadvpl/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/JoniPraia/plugadvpl/actions/workflows/ci.yml/badge.svg)](https://github.com/JoniPraia/plugadvpl/actions/workflows/ci.yml)
[![PyPI downloads](https://img.shields.io/pypi/dm/plugadvpl.svg?logo=pypi&logoColor=white)](https://pypi.org/project/plugadvpl/)
[![GitHub stars](https://img.shields.io/github/stars/JoniPraia/plugadvpl?logo=github)](https://github.com/JoniPraia/plugadvpl/stargazers)

> Plugin Claude Code + CLI Python que indexa fontes **ADVPL/TLPP** (TOTVS Protheus) em SQLite com FTS5 — para o Claude responder sobre o seu Protheus sem queimar contexto lendo `.prw` cru.

> ⚠️ **EDITANDO `.prw` cp1252?** Read/Edit do Claude são UTF-8 only — bytes acentuados viram `?` e o Edit corrompe acentos não-editados. **Use sempre `plugadvpl edit-prw stage <arq>` ANTES e `commit <arq>` DEPOIS** (v0.8.9+). Detalhes: skill `/plugadvpl:edit-prw` ou seção [Encoding](#encoding) abaixo.

---

## Por que plugadvpl

- **Economia de tokens.** Um `.prw` médio tem 1.000 a 10.000 linhas. Abrir cru custa de 5k a 50k tokens. Com plugadvpl, a mesma pergunta é respondida via metadados estruturados — **~16× menos contexto** em projetos reais.
- **Parser provado em campo.** O extrator de funções, tabelas, SQL embarcado e call graph foi portado de um parser interno do autor, validado em aproximadamente **2.000 fontes ADVPL**. Não é um experimento de fim de semana.
- **MIT, sem telemetria, 100% local.** Índice SQLite mora em `.plugadvpl/index.db` dentro do seu repo. Nenhum dado sai da máquina. Funciona offline.

---

## Demonstração

**Cenário sem plugin** — pergunta: "explique a função `FATA050`":

```
Claude → Read FATA050.prw            # arquivo inteiro
       → ~12.000 tokens consumidos
       → resposta vaga, sem call graph, sem saber quem usa
```

**Cenário com plugadvpl**:

```
Claude → /plugadvpl:arch FATA050.prw   # capabilities, tabelas, funções, includes
       → /plugadvpl:callers FATA050    # quem chama
       → Read FATA050.prw offset=234 limit=46   # range exato, só se preciso
       → ~730 tokens consumidos       (≈ 16× menor)
       → resposta com contexto: módulo, MVC, tabelas SA1/SC5, PE relacionado
```

---

## Instalação rápida (one-liner)

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/JoniPraia/plugadvpl/main/scripts/install.ps1 | iex
```

**macOS / Linux:**
```bash
curl -sSL https://raw.githubusercontent.com/JoniPraia/plugadvpl/main/scripts/install.sh | sh
```

O script:
1. Instala `uv` (gerenciador de pacotes Python da Astral) se ainda não estiver presente
2. Instala `plugadvpl` globalmente via `uv tool install`
3. Imprime próximos passos

Depois é só:
```bash
cd <pasta-do-seu-projeto-Protheus>
plugadvpl init
plugadvpl ingest
plugadvpl status
```

> Se você prefere usar o plugin via Claude Code (slash commands), instale o marketplace
> e use `/plugadvpl:setup` que faz tudo automaticamente (ver "Plugin Claude Code" abaixo).

---

## Atualizando para uma versão nova

> **CLI** (`plugadvpl`, Python) e **plugin Claude Code** (skills + agents + hook + slash commands) são **duas coisas separadas**. Atualizar uma **não toca na outra** — siga os dois fluxos quando sair release nova.

### 1. Atualizando a CLI Python (`plugadvpl ingest/compile/grep/...`)

A forma simples — funciona em qualquer plataforma — é **rodar o one-liner de
instalação de novo**. Ele detecta `uv` ausente, instala se preciso, e
reinstala `plugadvpl` apontando para a versão atual do PyPI.

**Windows (PowerShell):**
```powershell
irm https://raw.githubusercontent.com/JoniPraia/plugadvpl/main/scripts/install.ps1 | iex
```

**macOS / Linux:**
```bash
curl -sSL https://raw.githubusercontent.com/JoniPraia/plugadvpl/main/scripts/install.sh | sh
```

Se já tem `uv` e quer só forçar pull da versão nova (uv às vezes segura cache):

```powershell
uv cache clean plugadvpl
uv tool install plugadvpl --reinstall --force
plugadvpl --version
```

**Erro `os error 32` (Windows)** durante `uv tool upgrade` → algum terminal
tem `plugadvpl.exe` aberto (Defender, VSCode terminal, outro shell):

```powershell
# Feche outros terminais com plugadvpl e:
uv tool install --reinstall plugadvpl

# Se o uv ficou em estado bugado ("Nothing to upgrade" mas versão antiga):
uv tool uninstall plugadvpl
uv tool install plugadvpl
```

**Erro `os error 5` (Acesso negado)** → mesma coisa, mas Windows Defender
provavelmente está com handle no `.exe`. Mesma solução acima, ou adicione
exclusão:

```powershell
# PowerShell admin (1x na vida):
Add-MpPreference -ExclusionPath "$env:APPDATA\uv\tools"
```

### 2. Atualizando o plugin Claude Code (skills, slash commands, hooks)

#### Cenário A — quem já tem o plugin instalado

No chat do Claude Code:

```
/plugin
```

Vai abrir o painel **Manage Plugins**. Navegue:

1. Aba **Marketplaces** → seleciona `plugadvpl-marketplace`
2. **Update marketplace** (puxa o `marketplace.json` atualizado do GitHub)
3. Volta pra aba **Plugins** ou **Installed**
4. Se aparecer indicador de update no `plugadvpl` → seleciona → **Update**

No CLI puro do Claude Code (terminal `claude`), também funciona:

```
/plugin marketplace update plugadvpl-marketplace
/plugin update plugadvpl
```

Depois **reinicia o Claude Code** pra garantir que skills + hooks + slash commands recarregam.

#### Cenário B — primeira instalação (nunca instalou ainda)

No chat do Claude Code:

```
/plugin marketplace add https://github.com/JoniPraia/plugadvpl.git
/plugin install plugadvpl
```

Na extensão VSCode (que não aceita `/plugin install` direto), use `/plugin` → UI → **Marketplaces** → **Add** com a mesma URL → aba **Plugins** → **Install for you (user scope)**.

#### Cenário C — install travado em "Permission denied (publickey)"

Sintoma: ao instalar/atualizar, recebe:
```
git@github.com: Permission denied (publickey).
fatal: Could not read from remote repository.
```

**Causa:** versões `< 0.9.4` do `marketplace.json` usavam o formato `source: github` que o Claude Code v2.1.x deduz pra SSH (`git@github.com:...`) — quebra pra qualquer usuário sem chave SSH cadastrada no GitHub, mesmo o repo sendo público.

**Fix (a partir de v0.9.4 já está corrigido — siga estes passos pra puxar):**

```
/plugin
```
1. Aba **Marketplaces** → `plugadvpl-marketplace` → **Update marketplace**
   *(isso baixa o `marketplace.json` v0.9.4+ que usa `source: url` com HTTPS explícita)*
2. **Browse plugins** → `plugadvpl` → **Install for you (user scope)**

Se mesmo assim insistir em SSH (cache muito antigo do Claude Code):

```
/plugin
```
1. **Marketplaces** → `plugadvpl-marketplace` → **Remove marketplace**
2. Reinicia o Claude Code
3. Adiciona de novo: `/plugin marketplace add https://github.com/JoniPraia/plugadvpl.git`
4. Install normal

### 3. Verificar o que ficou instalado

PowerShell (mostra todos os plugins ativos):

```powershell
Get-Content "$env:USERPROFILE\.claude\plugins\installed_plugins.json"
```

No chat (slash command):

```
/plugadvpl:status
```

Se aparecer counters do índice e versão `v0.9.4+` → tudo OK.

Se algo travar (`uv` sumiu, plugin atualiza mas slash command parece velho,
cache de uvx segurando versão antiga), veja [Troubleshooting de atualização](docs/FAQ.md#troubleshooting-de-atualização) no FAQ.

---

## Quick start

```bash
# 1. Pré-requisito: uv (gerenciador Python rápido)
winget install astral-sh.uv                              # Windows
# OU: curl -LsSf https://astral.sh/uv/install.sh | sh    # Linux/macOS

# 2. Instale o plugin Claude Code — veja seção abaixo
#    (caminho varia entre CLI nativo e extensão VSCode)

# 3. Abra o seu projeto Protheus e rode:
/plugadvpl:init      # cria .plugadvpl/index.db, fragment CLAUDE.md, .gitignore
/plugadvpl:ingest    # parser paralelo, ~30–60s para 2.000 fontes
```

Pronto. A partir daqui o Claude já consulta o índice antes de abrir qualquer `.prw`. Para inspecionar você mesmo:

```bash
/plugadvpl:arch FATA050.prw         # visão arquitetural (inclui tabelas via ExecAuto)
/plugadvpl:callers MaFisRef         # quem chama essa função
/plugadvpl:tables SA1               # quem lê/grava/reclock na SA1
/plugadvpl:param MV_LOCALIZA        # onde esse parâmetro é usado
/plugadvpl:lint --severity error    # encontrar problemas críticos
/plugadvpl:impacto A1_COD           # cruza referências a um campo (Universo 2)
/plugadvpl:workflow --kind job_standalone  # jobs daemon do projeto (Universo 3)
/plugadvpl:execauto --routine MATA410 --op inc  # quem inclui Pedido de Venda
/plugadvpl:docs --show MT460FIM     # doc completa em Markdown sem abrir o fonte
```

---

## Instalando o plugin Claude Code (opcional, para slash commands)

Além da CLI, o plugadvpl também é um **plugin Claude Code** que adiciona:
- Slash commands `/plugadvpl:arch`, `/plugadvpl:find`, `/plugadvpl:callers`, etc.
- 18 knowledge skills temáticas que Claude carrega automaticamente (advpl-mvc, advpl-tlpp, advpl-pontos-entrada, etc.)
- Hook `SessionStart` que detecta projetos ADVPL e sugere `/plugadvpl:init`
- 4 subagents especializados (analyzer, impact-analyzer, code-generator, reviewer-bot)

A forma de instalar depende de onde você usa o Claude Code:

### Opção A — Claude Code CLI (terminal `claude`)

No chat do CLI:

```
/plugin marketplace add https://github.com/JoniPraia/plugadvpl.git
/plugin install plugadvpl
```

Aceite o trust dialog. Pronto.

### Opção B — Extensão VSCode do Claude Code

A extensão **não suporta** `/plugin install` direto no chat (limitação oficial do Claude Code). Use a UI:

1. No chat, digite `/plugin` (sem args) — abre o painel **Manage Plugins**
   *Alternativa*: `Ctrl+Shift+P` → "Claude Code: Manage Plugins"
2. Aba **Marketplaces** → botão **Add** → cole `https://github.com/JoniPraia/plugadvpl.git`
3. Aba **Plugins** → encontre `plugadvpl` → clique **Install for you (user scope)**
4. Aceite o trust dialog

Reinicie o Claude Code para garantir que skills, hooks e slash commands carregam corretamente.

### Verificação

Em qualquer caminho, no chat:

```
/plugadvpl:status
```

Se aparecer output com counters do índice, o plugin está instalado e funcionando.

> **Importante:** O plugin precisa da CLI Python instalada também (`uv tool install plugadvpl` ou via [Instalação rápida (one-liner)](#instalação-rápida-one-liner)). O plugin é uma camada fina sobre a CLI — sem ela, os slash commands não funcionam.

---

## Comandos disponíveis

O CLI Python expõe **~30 subcomandos** (Universo 1-4 + Fase 0 + Fase 1), espelhados em slash commands do plugin Claude Code.

### Universo 1 — Fontes (v0.1)

| Comando | Função |
|---|---|
| `/plugadvpl:init` | Cria `.plugadvpl/index.db`, fragment em `CLAUDE.md` e entrada no `.gitignore` |
| `/plugadvpl:ingest` | Escaneia e indexa todos os fontes (`--workers N`, `--incremental`, `--no-content`, `--redact-secrets`) |
| `/plugadvpl:reindex <arq>` | Re-ingest de um arquivo (após edição manual) |
| `/plugadvpl:status` | Versões, contadores, opcionalmente arquivos stale (`--check-stale`) |
| `/plugadvpl:find <termo>` | Busca composta: função → arquivo → conteúdo (FTS) |
| `/plugadvpl:callers <funcao>` | Quem chama a função (call graph reverso) |
| `/plugadvpl:callees <funcao>` | O que a função chama (call graph direto) |
| `/plugadvpl:tables <T>` | Quem usa a tabela `T` (`--mode read/write/reclock`) |
| `/plugadvpl:param <MV>` | Onde o parâmetro `MV_*` aparece |
| `/plugadvpl:arch <arq>` | **Visão arquitetural** — use SEMPRE antes de `Read`. Inclui `tabelas_via_execauto_resolvidas` (v0.4.1+) |
| `/plugadvpl:lint [arq]` | Lint findings (`--severity`, `--regra`, `--cross-file`) |
| `/plugadvpl:doctor` | Diagnósticos (encoding, órfãos, FTS sync, lookups) |
| `/plugadvpl:grep <pattern>` | Busca textual nos chunks (`--mode fts/literal/identifier`) |
| `/plugadvpl:help` | Lista comandos (atalho do CLI `--help`) |

### Universo 2 — Dicionário SX (v0.3)

| Comando | Função |
|---|---|
| `/plugadvpl:ingest-sx <pasta-csv>` | Ingere dicionário SX exportado em CSV (sx1..sxg) |
| `/plugadvpl:impacto <campo>` | **Killer feature** — cruza referências a um campo em fontes ↔ SX3 ↔ SX7 ↔ SX1 (`--depth 1..3`) |
| `/plugadvpl:gatilho <campo>` | Cadeia de gatilhos SX7 origem → destino (`--depth 1..3`) |
| `/plugadvpl:sx-status` | Counts por tabela do dicionário SX |

### Universo 3 — Rastreabilidade (v0.4)

| Comando | Função |
|---|---|
| **`/plugadvpl:workflow`** | **(v0.4.0)** Lista os 4 mecanismos de execução não-direta: `workflow`/`schedule`/`job_standalone`/`mail_send` (filtros `--kind`/`--target`/`--arquivo`) |
| **`/plugadvpl:execauto`** | **(v0.4.1)** Resolve `MsExecAuto({\|x,y,z\| MATA410(x,y,z)}, ...)` → rotina canônica + módulo + tabelas inferidas (filtros `--routine`/`--modulo`/`--op`/`--dynamic`) |
| **`/plugadvpl:docs [modulo]`** | **(v0.4.2)** Catálogo de Protheus.doc agregado por módulo/autor/tipo. Modo `--show <fn>` em Markdown estruturado, `--orphans` cruza com BP-007 |

### Universo 4 — Trace + Qualidade (v0.5/v0.6)

| Comando | Função |
|---|---|
| `/plugadvpl:trace <entidade>` | Grafo unificado cross-universo: dado um `campo`/`funcao`/`tabela`/`arquivo`/`parametro`/`pergunte`, devolve TODOS os pontos onde aparece (fontes + SX + workflow + jobs + ExecAuto + Protheus.doc) |
| `/plugadvpl:metrics [arq]` | Métricas por função: complexidade ciclomática McCabe (`cc`), LOC, nesting, fan-out, params, `has_doc` |
| `/plugadvpl:hotspots` | Top-N funções por critério (`--tipo user_func/method/calls/risk`) — onde começar refactor |
| `/plugadvpl:cobertura-doc` | % de funções com Protheus.doc por módulo ou tipo de source |

### Fase 0 / Fase 1 — Runtime ADVPL (v0.7/v0.8/v0.9)

| Comando | Função |
|---|---|
| `/plugadvpl:edit-prw {check\|open\|save\|stage\|commit}` | **(v0.7.0+)** Conversão CP1252↔UTF-8 in-place. Workflow `stage`→edita→`commit` evita corromper acentos ao editar `.prw` com Claude |
| `/plugadvpl:edit-prw clean [target]` | **(v0.8.11)** Remove `.bak` acumulado dos ciclos stage/commit. `--dry-run` lista sem deletar, `--yes` skipa confirmação |
| `/plugadvpl:compile <fonte>` | **(v0.8.0+)** Compila ADVPL via wrapper sobre binário oficial `advpls` (TOTVS). 2 modos: `appre` (local, pré-processador) ou `cli` (full via AppServer TCP) |
| `/plugadvpl:compile --doctor` | **(v0.8.4)** Pre-flight check estruturado em JSON. Auto-detecta advpls + includes + AppServer. Retorna `next_actions` ordenadas pro agente seguir |
| `/plugadvpl:compile --install-advpls` | **(v0.8.6)** Instalação gerenciada do binário em `~/.plugadvpl/advpls/`. Interativo: copia de path local OU baixa do Marketplace VSCode (~118MB) — sempre pede confirmação |
| `/plugadvpl:compile --list-servers` / `--add-server` / `--use-server <nome>` / `--import-tds-servers` | **(v0.8.7+)** Registry global de AppServers em `~/.plugadvpl/servers.json` (estilo TDS-VSCode). Cadastra uma vez, usa em qualquer projeto. Em v0.8.11, `--import-tds-servers` passou a ler `buildVersion` + `includes` corretamente |
| `/plugadvpl:compile --probe-appserver <host:port \| path>` | **(v0.8.11/0.8.12)** Descobre build do AppServer. Modo **network** (`host:port`) invoca `advpls cli action=validate` — mesmo mecanismo que o TDS-VSCode usa, retorna build + flag SSL. Modo **log** (path) parseia `protheus.log` como fallback offline |
| `/plugadvpl:compile --set-credentials <server>` / `--clear-credentials <server>` | **(v0.9.0)** Salva user+senha no **cofre nativo do OS** (Win Credential Manager / macOS Keychain / Linux Secret Service). Prompt seguro com `getpass`. Plugin nunca grava senha em arquivo |
| `/plugadvpl:compile --explain-config` | **(v0.9.0)** JSON estruturado mostrando ordem de precedência (CLI flag > runtime.toml > registry > keyring > env > auto-detect) + de onde veio cada campo + estado das credenciais (senha sempre redacted) |

**Setup zero-config recomendado (v0.9.1+)**:
```bash
# 1x na vida em cada máquina:
plugadvpl compile --install-advpls               # baixa/copia advpls (~118MB)
plugadvpl compile --import-tds-servers --yes     # se já tem TDS-VSCode
plugadvpl compile --set-credentials <nome>       # prompt seguro, salva no cofre

# Daí em diante, em qualquer projeto, qualquer shell — zero env var, zero runtime.toml:
plugadvpl compile --mode cli --use-server <nome> FONTE.PRW

# appre (sem AppServer) nem precisa de credencial desde v0.9.1:
plugadvpl compile --mode appre --use-server <nome> FONTE.PRW
```

Detalhes em [docs/compile-checklist.md](docs/compile-checklist.md) (info conversacional do que coletar) e [docs/setup-compile.md](docs/setup-compile.md) (guia técnico passo-a-passo).

Reference completa de todos os subcomandos: [docs/cli-reference.md](docs/cli-reference.md).

---

## Skills incluídas

Além dos ~30 command wrappers (1 por subcomando do CLI + `help` + `setup`), o plugin traz **18 knowledge skills** carregadas pelo Claude conforme contexto:

| Skill | Quando carrega |
|---|---|
| `plugadvpl-index-usage` | Skill-chefe — força consulta ao índice antes de qualquer `Read` em fonte ADVPL |
| `advpl-fundamentals` | Notação húngara, naming, prefixos de módulo, 195 funções restritas |
| `advpl-encoding` | cp1252 (.prw) vs utf-8 (.tlpp) — **inclui workflow seguro de Edit (stage/commit)** |
| `edit-prw` | **Workflow operacional pra editar `.prw` cp1252 com Claude sem corromper acentos** |
| `advpl-mvc` | MenuDef/ModelDef/ViewDef, hooks bCommit/bTudoOk, FWFormStruct |
| `advpl-mvc-avancado` | Eventos MVC, validações cruzadas, FWMVCRotAuto |
| `advpl-tlpp` | TLPP moderno — OO, namespaces, annotations |
| `advpl-embedded-sql` | BeginSql/EndSql, TCQuery, `%xfilial%`, `%notDel%`, `%table%` |
| `advpl-pontos-entrada` | User Function NOME(PARAMIXB), retorno via PARAMIXB[última] |
| `advpl-webservice` | REST (`WSRESTFUL`, `@Get/@Post`) e SOAP (`WSSERVICE`/`WSMETHOD`) |
| `advpl-web` | Interfaces web — Webex / HTML / WebExpress |
| `advpl-jobs-rpc` | `RpcSetEnv`, `StartJob`, `MsRunInThread`, funções proibidas em job |
| `advpl-matxfis` | Família fiscal (NF-e, SPED, ECF, REINF, integração SF2/SD2/SF3) |
| `advpl-advanced` | Threads, IPC, debug, OO em profundidade |
| `advpl-dicionario-sx` | Estrutura SX1/SX2/SX3/SX5/SX6/SX7/SIX/SXA/SXB + cookbook SQL pra criar campo (clonar bitmap `X3_USADO`, checklist, armadilhas v12.1.7+) (v0.2.0) |
| `advpl-dicionario-sx-validacoes` | Expressões ADVPL embutidas em X3_VALID/INIT/WHEN/VLDUSER, X7_REGRA, X1_VALID, X6_VALID/INIT — guia pra análise de impacto (v0.3.0) |
| `advpl-refactoring` | 6 padrões com before/after (DbSeek loop, Posicione repetido, IFs hardcoded, AxCadastro→MVC, string concat em loop, RecLock sem Begin Transaction) — usar quando o pedido for "melhorar"/"refatorar"/"está lento" (v0.3.3) |
| `advpl-debugging` | Top 30 erros comuns em produção + métodos de debug (ConOut, MemoWrite, FwLogMsg, varInfo) — usar quando o usuário cola traceback do AppServer.log (v0.3.3) |
| `advpl-code-review` | 24 regras BP/SEC/PERF/MOD — 13 single-file (v0.1) + 11 cross-file `SX-001..SX-011` (v0.3.0) |

Também incluídos: **4 agents** especializados (`advpl-analyzer`, `advpl-impact-analyzer`, `advpl-code-generator`, `advpl-reviewer-bot`) e **1 SessionStart hook** Node.js que faz onboarding cross-platform do `.plugadvpl/`.

---

## Como funciona

Visão geral do pipeline:

```
.prw / .tlpp           parser strip-first         SQLite + FTS5         slash command
(seu projeto)   ───▶   (regex sobre conteúdo  ─▶  27 tabelas físicas  ─▶ /plugadvpl:*
                       sem comentário/string)     + 2 FTS5 virtuais     (Claude consulta
                       paralelo adaptive          + 7 lookups TOTVS      ~700 tokens)
```

O plugin é dividido em **camadas independentes** — cada uma adiciona um tipo de informação ao índice SQLite e seus próprios subcomandos. Você pode usar só as que fazem sentido pro seu projeto.

### Universo 1 — Ingestão de fontes (v0.1)

**O que faz**: `plugadvpl ingest` escaneia recursivamente o `--root`, encontra arquivos `.prw`/`.prx`/`.tlpp`/`.apw`, e parseia cada um em paralelo (`ProcessPoolExecutor` com `min(8, cpu_count())` para projetos ≥200 arquivos; single-thread para projetos pequenos). De cada fonte extrai:

- **Funções** (User/Static/Main Function, Method) com `linha_inicio`/`linha_fim` e assinatura
- **Chamadas de função** (`U_NOME()`, `StaticFunc()`, `obj:Method()`) → grafo direcionado
- **Tabelas usadas** (`SA1->A1_COD`, `DbSelectArea("SA1")`, alias dinâmico) com modo `read`/`write`/`reclock`
- **SQL embarcado** (`BeginSql ... EndSql`, `TCQuery`) com macros (`%xfilial%`, `%notDel%`, `%table:SA1%`)
- **Parâmetros MV_*** (`GetMV`, `PutMV`, `SuperGetMv` — qualquer prefixo: `MV_*`, `ABC_*`, customizados)
- **Pontos de entrada** (PEs com 1º arg `PARAMIXB`)
- **REST endpoints** (`WSRESTFUL`, `@Get`/`@Post`, rotas)
- **HTTP outbound** (`HttpPost`, `HTTPSGet`, `WSDLService`)
- **Workflow / Jobs** (`StartJob`, `MsRunInThread`, `MsWorkflow`, `TWFProcess`, `Schedule`)
- **Includes** (`#include "totvs.ch"`) — resolvidos ou não
- **Encoding** (detecta CP1252 vs UTF-8 strict — vira lint ENC-001 quando `.prw` é UTF-8)
- **Capabilities** computadas: source_type (mvc/rest/cadastro/relatorio/PE/job), tem RecLock, tem REST, tem MVC, etc.
- **Lint findings** single-file (38 regras: best-practice, security, performance, modernization, webservice, encoding)

Persistência em SQLite + **2 índices FTS5**: um `unicode61` com `tokenchars '_-'` (mantém `A1_COD`/`FW-Browse` como um token só) e um **trigram** para busca substring exata (`SA1->A1_COD`, `%xfilial%`).

**Comandos**: `init`, `ingest`, `reindex`, `find`, `callers`, `callees`, `tables`, `param`, `arch`, `lint`, `grep`, `doctor`, `status`.

### Universo 2 — Dicionário SX (v0.3)

**O que faz**: `plugadvpl ingest-sx <pasta-csv>` ingere o dicionário SX exportado do Configurador (SIGACFG → Misc → Exportar Dicionário em CSV) em 11 tabelas: `tabelas` (SX2), `campos` (SX3), `gatilhos` (SX7), `parametros` (SX6), `perguntas` (SX1), `consultas` (SXB), `pastas` (SXA), `relacionamentos` (SX9), `indices` (SIX), `tabelas_genericas` (SX5), `grupos_campo` (SXG).

**Por design**: ingere apenas customizações do cliente (`X3_NIVEL > 1`). O padrão TOTVS é ignorado — o plugin **não redistribui dicionário TOTVS** (questão de licença).

**Cruzamento**: campos do SX3 são cruzados com `fonte_chunks.content` (busca substring) → quem usa o campo. SX7 (gatilhos) origem→destino vira cadeia rastreável. SX1 (perguntas) cruza com `Pergunte("XXX", .F.)` nos fontes.

**Killer feature**: `plugadvpl impacto <campo>` cruza referências do campo em **3 camadas** (fontes + SX3 trigger fontes + SX7 destino + SX1 onde aparece) com profundidade `--depth 1..3`. Em um campo central tipo `A1_COD` retorna grafo de impacto que ajuda a estimar refactors.

**Comandos**: `ingest-sx`, `impacto`, `gatilho`, `sx-status` + **11 regras cross-file** `SX-001..SX-011` (X3_VALID chama função inexistente, X7_REGRA aponta pra campo inexistente, MV_PAR* não usado em fonte, etc.).

### Universo 3 — Rastreabilidade (v0.4)

**O que faz**: indexa formas de execução **não-direta** que `callers`/`callees` não pegam (porque não há call literal):

- **Workflow / Schedule / Job standalone / Mail** (`MsWorkflow`, `TWFProcess`, `WFPrepEnv`, `Schedule`, `StartJob` daemon, `MailSendMail`)
- **ExecAuto chain**: `MsExecAuto({|x,y,z| MATA410(x,y,z)}, aHeader, aItems, nOpcAuto)` — resolve a **rotina canônica** (`MATA410` → "Pedido de Venda"), o módulo (SIGAFAT), e infere as tabelas afetadas (SC5/SC6 pra MATA410, SE1 pra MATA440, etc.) via lookup `lookups/execauto_routines.json`
- **Protheus.doc agregado**: parse de blocos `/*/{Protheus.doc} NomeFn ... /*/`  e cruzamento com `funcoes` da fonte_chunks → catálogo navegável por módulo/autor/tipo

**Comandos**: `workflow`, `execauto`, `docs` (`--show <fn>` em Markdown, `--orphans` cruza com BP-007).

### Universo 4 — Trace + Qualidade (v0.5/v0.6)

**O que faz**: 2 features distintas que fecham o ciclo de análise.

**Feature A — Trace unificado** (`plugadvpl trace <entidade>`): dado um nome (campo SX3, função ADVPL, tabela, arquivo, parâmetro MV_*, pergunte SX1), o auto-detect decide o tipo e cruza **TODOS os universos** em uma resposta única: aparece em quais fontes, quais validações SX, quais gatilhos, quais workflows, quais jobs, quais chamadas ExecAuto, qual Protheus.doc. Mata necessidade de rodar 5 comandos diferentes pra entender uma entidade.

**Feature B — Qualidade & métricas** (schema v10, tabela `fonte_metrics`):
- `plugadvpl metrics [arq]` — McCabe cyclomatic complexity, LOC, max nesting, fan-out, params_count, has_doc por função
- `plugadvpl hotspots` — top-N funções por critério (`--tipo user_func/method/calls/risk`) — onde começar refactor
- `plugadvpl cobertura-doc` — % de funções com Protheus.doc por módulo ou source_type

### Fase 0 — Quick wins (v0.7)

**Lint rules de runtime** que só faziam sentido depois do parser maduro:

- **WS-001/002/003** — WSMETHOD sem WSSERVICE, `GetContent`+`FromJson` sem `DecodeUtf8`, `SetResponse` sem `EncodeUtf8` em WSRESTFUL
- **XF-001** — `MsSeek(xFilial("XX"))` em tabela `x2_modo='E'` dentro de REST/JOB sem `RpcSetEnv` precedente (bug silencioso crítico: `cFilAnt` vazia, xFilial retorna "")
- **ENC-001** — `.prw`/`.prx` salvo em UTF-8 quebra compilador appserver legado
- **Comando `edit-prw`** — conversão CP1252↔UTF-8 com backup
- **Contract doc `U_EXEC`** + reference impl MIT (`docs/examples/uexec.prw`) pra execução headless de função ADVPL via REST (pavimenta Fase 2)

### Fase 1 — Compilação (v0.8) ← NOVO

**`plugadvpl compile <fonte>`** é um **wrapper Python sobre o binário oficial `advpls`** (TOTVS — distribuído na extensão TDS-VSCode pública). Devolve **JSON estruturado** consumível por CI, com auto-detect de includes, modo `appre` (local) ou `cli` (full via AppServer).

Veja a seção dedicada [**Compilação ADVPL**](#compilação-advpl) logo abaixo pra entender a estrutura e o que chama quando.

---

## Compilação ADVPL

Camada de runtime entregue nas versões v0.7/v0.8 — fecha o ciclo "ler/analisar → **compilar** → executar → testar".

### O que NÃO fazemos

O plugin **não reimplementa o compilador**. ADVPL é proprietário TOTVS, sem fork open-source. O `plugadvpl compile`:
- Invoca o binário oficial `advpls` (distribuído publicamente na extensão TDS-VSCode no Microsoft Marketplace) via `subprocess.Popen`
- Captura stdout/stderr + arquivos `.errprw` que o advpls gera
- Parseia output em texto livre usando regex patterns externalizados (`lookups/compile_patterns.json`)
- Devolve resultado estruturado em JSON pra agente IA / CI consumir

Crédito completo do `advpls` na seção [Créditos](#créditos).

### Arquitetura

```
┌────────────────────────────────────────────────────────────────────┐
│ plugadvpl compile <fonte.prw> --mode cli --use-server dev-local    │
└────────────────────────────┬───────────────────────────────────────┘
                             │
              ┌──────────────┴──────────────┐
              ▼                             ▼
    ┌──────────────────┐         ┌──────────────────────┐
    │ compile_doctor   │         │ compile_servers      │
    │ ────────────────│         │ ────────────────────│
    │ pre-flight check │         │ ~/.plugadvpl/        │
    │ auto-detecta:    │         │   servers.json       │
    │  • advpls        │         │ (host/port/build/    │
    │  • includes      │         │  envs/user_env/      │
    │  • AppServer TCP │         │  password_env)       │
    │  • env vars      │         └──────────┬───────────┘
    │ → next_actions   │                    │
    │   pro agente     │                    │
    └────────┬─────────┘                    │
             │                              │
             ▼                              ▼
    ┌──────────────────────────────────────────────────┐
    │ runtime_config (runtime.toml por projeto, opt-in)│
    │ + override do --use-server                       │
    └────────────────────────┬─────────────────────────┘
                             ▼
                  ┌─────────────────────┐
                  │ compile.py          │
                  │ ───────────────────│
                  │ • resolve files     │
                  │ • pick mode (appre/cli/auto)
                  │ • build args        │
                  │ • write secure .ini │ ← (modo cli, CP1252, 0o600)
                  │ • Popen subprocess  │ ─────────────────┐
                  └──┬──────────────────┘                  │
                     │                                     ▼
                     │                       ┌─────────────────────────────┐
                     │                       │ advpls (binário TOTVS)      │
                     │                       │ ────────────────────────────│
                     │                       │ ~/.plugadvpl/advpls/bin/<os>/
                     │                       │ instalado via               │
                     │                       │ --install-advpls            │
                     │                       │ (copy local OU download     │
                     │                       │  do Marketplace VSCode)     │
                     │                       └─────────────┬───────────────┘
                     │                                     │
                     │       ┌───── stdout/stderr ─────────┤
                     │       │                             │
                     │       │       ┌── .errprw files ────┘
                     │       ▼       ▼
                     │  ┌───────────────────────────┐
                     │  │ compile_parser            │
                     │  │ ─────────────────────────│
                     │  │ • regex patterns          │
                     │  │ • UTF-16 BOM / CP1252     │
                     │  │ • redact credenciais      │
                     │  │ • bucket __unmatched__    │
                     │  └─────────┬─────────────────┘
                     │            │
                     └────────────┼───→ CompileResult (JSON)
                                  │     {rows, summary, next_steps,
                                  │      exit_code}
                                  ▼
```

### Módulos da Fase 1

| Módulo | Responsabilidade |
|---|---|
| **`compile_doctor.py`** | Pre-flight check: detecta advpls (env var + `~/.plugadvpl/` + PATH + extensão TDS-VSCode), includes Protheus, AppServer TCP. Retorna JSON com `status`/`mode_supported`/`checks`/`next_actions` pro agente seguir |
| **`compile_servers.py`** | Registry global de AppServers em `~/.plugadvpl/servers.json` (estilo `~/.totvsls/servers.json` do TDS-VSCode — inclusive auto-importa de lá). Permissão `0o600`, NUNCA grava senha |
| **`compile_installer.py`** | Instalação gerenciada do advpls em `~/.plugadvpl/advpls/`. Modo copy (de path local) ou download (.vsix do Marketplace VSCode, extrai só `bin/<os>/`). Sempre mostra plano + pede confirmação |
| **`compile_parser.py`** | Parse de output do advpls com regex patterns externalizados (`lookups/compile_patterns.json`). Trata UTF-16 BOM, CP1252 fallback, redact credenciais (`lookups/redact_patterns.json`), normaliza paths via `Path.resolve()` |
| **`runtime_config.py`** | Carrega `<root>/.plugadvpl/runtime.toml` (config por projeto, opt-in). Valida tudo no load. Credenciais sempre via nome de env var, nunca valor literal |
| **`compile.py`** | Orchestrator único com side effects. Cria tempfile `.ini` em CP1252 com `os.open(O_EXCL\|0o600)`, gerencia subprocess lifecycle (timeout, KeyboardInterrupt, cleanup), agrega `CompileResult` |

### Modos de compilação

| Modo | Onde compila | Pega | Quando usar |
|---|---|---|---|
| **`appre`** | Local (sem AppServer) | Sintaxe, `#include` faltando, macros, defines | Validação rápida em CI/dev. ~60ms/fonte. **NÃO pega** erros semânticos |
| **`cli`** | AppServer TCP (RPC) | TUDO — semântica + binding + gera RPO | CI rigoroso, build final |
| **`auto`** (default) | `cli` se AppServer responde, senão `appre` | depende | Default sensato |

### Workflow zero-config para usuário novo (v0.9.1+)

```bash
# 1. Instala advpls (1x por máquina)
plugadvpl compile --install-advpls
#   interativo: copia de path local OU baixa Marketplace (~118MB, confirma antes)

# 2. Cadastra servers (1x por máquina, opcional se já usa TDS-VSCode)
plugadvpl compile --import-tds-servers --yes     # se já tem TDS-VSCode
# OU
plugadvpl compile --add-server                   # interativo: name, host, port, build, envs
# OU descobre build do AppServer remoto sem ter TDS-VSCode:
plugadvpl compile --probe-appserver 192.168.0.10:1234

# 3. Salva credencial 1x no cofre do OS — sem mais $env:PROTHEUS_USER!
plugadvpl compile --set-credentials <nome>       # prompt seguro (getpass)

# 4. Compila qualquer fonte de qualquer projeto, qualquer shell:
plugadvpl compile --use-server <nome> --mode cli FONTE.PRW

# Debug — vê de onde cada campo veio:
plugadvpl compile --explain-config --format json
```

### Workflow do agente IA (skill `/plugadvpl:compile`)

```
1. plugadvpl --format json compile --doctor    ← SEMPRE primeiro
2. Para cada item em next_actions, processar:
   • set_advpls_binary → sugerir --install-advpls
   • use_server (candidates) → mostrar lista, perguntar qual
   • import_tds_servers → sugerir --import-tds-servers
   • set_includes → confirmar candidate detectada
   • create_runtime_toml → último recurso, se sem servers
   • set_env_var (secret=true) → orientar export sem logar valor
3. Re-rodar --doctor até status=ready
4. Compilar: plugadvpl compile --use-server X --mode cli <fonte>
```

Detalhes completos em [docs/compile-checklist.md](docs/compile-checklist.md) (humano), [docs/setup-compile.md](docs/setup-compile.md) (técnico) e [skills/compile/SKILL.md](skills/compile/SKILL.md) (agente).

### Segurança

- **Credenciais NUNCA gravadas em arquivo do plugin** — só nomes de env var no `runtime.toml` e no `servers.json`. Senha vive em UM destes lugares (em ordem de precedência): env var → **cofre nativo do OS** (Win Credential Manager / macOS Keychain / Linux Secret Service, v0.9.0+, cifrado por DPAPI/Keychain/SecretService) → erro didático
- **Prompt seguro** em `--set-credentials` usa `getpass` (senha não ecoa, confirmação dupla)
- **`--explain-config` redacted** — campo `password` aparece como `<set>` / `<unset>`, nunca o valor
- **Tempfile `.ini` em CP1252 + permissão 0o600** (POSIX); tempdir 0o700 via `mkdtemp`
- **Cleanup garantido** no `finally` em todos os caminhos (success/timeout/KeyboardInterrupt)
- **Redact patterns externos** (`lookups/redact_patterns.json`) aplicados em stdout/stderr/diagnostic.raw antes de gravar — cobre `password`/`psw`/`senha`/`pwd`/`aut_file`/hex keys
- **Security warning** quando `appserver.host` não é localhost (recomenda SSH tunnel)
- **Fallback gracioso** quando keyring não disponível (Linux server sem D-Bus): retorna `keyring_available=False`, fluxo cai pra env var sem crashear

---

## Requisitos

- **Claude Code** (CLI ou IDE extension) com suporte a plugins
- **Python 3.11+** instalado via `uvx`/`uv` (não precisa criar venv manualmente)
- **Projeto Protheus** com fontes `.prw`, `.prx`, `.tlpp` ou `.apw`
- SO: Windows, Linux ou macOS (CI rodando matrix 3 OS × 3 Python)

---

## Status

**v0.9.4 — fix de install do plugin Claude Code (HTTPS explícita no marketplace.json).**

- **~35 subcomandos** incluindo `compile {<fonte>, --doctor, --install-advpls, --list-servers, --add-server, --use-server, --import-tds-servers, --probe-appserver, --set-credentials, --clear-credentials, --explain-config, --init-config}` + `edit-prw {check, open, save, stage, commit, clean}`
- **40+ skills** (knowledge + slash command wrappers), 4 agents especializados, 1 SessionStart hook
- **27 tabelas físicas** + 2 FTS5 (`fonte_chunks_fts` unicode61 + `fonte_chunks_fts_tri` trigram) + 7 lookups embarcados
- **812 testes verde** (unit + integration + bench + smoke real opcional)
- Bench em ~2.000 fontes: `ingest` <60s com `--workers 8`; `ingest-sx` do dicionário completo (~420k rows) <30s
- Schema v10 — migrations 005-007 (Universo 3) + 008 (índices polish) + 010 (Universo 4 métricas)
- **38 lint rules** (24 single-file + 13 cross-file + 1 encoding) cobrindo best-practice, security, performance, modernization, dicionário SX, webservice
- **Fase 1 compile** validada end-to-end contra `advpls` real (extensão TDS-VSCode v3.x) + includes Protheus reais

**Highlights recentes (v0.8.11 → v0.9.4):**

| Versão | Destaque |
|---|---|
| **v0.9.4** | Fix install: `marketplace.json` trocou `source: github` → `source: url` com HTTPS explícita. Resolve `Permission denied (publickey)` em usuários sem SSH key configurada no GitHub |
| **v0.9.3** | Skill `advpl-webservice` reescrita: comparação detalhada WSRESTFUL vs notation (`@Get/@Post`), ~3× speedup do notation, `@Patch` exclusivo, migration path 10 passos, REST-DOC/Swagger automático + `reference-rest.md` com CRUD completo nos 2 estilos |
| **v0.9.2** | 3 fixes HIGH: `metrics --no-content` agora calcula CC correto; hook SessionStart deixou de pinar `plugadvpl@0.3.1`; `grep --mode literal` usa índice trigram FTS (10-50× speedup) |
| **v0.9.1** | `--use-server + --mode appre` parou de exigir credencial (appre é local, não conecta no AppServer) |
| **v0.9.0** | Cofre nativo do OS pra credencial Protheus (`--set-credentials`, `--clear-credentials`, `--explain-config`) — nunca mais exportar senha em env var por sessão |
| **v0.8.12** | `--probe-appserver host:port` descobre build via `advpls cli action=validate` (mesmo mecanismo do TDS-VSCode) — funciona via SSH tunnel/VPN |
| **v0.8.11** | 4 gaps de uso real corrigidos: TDS `buildVersion`+`includes`, `[auth]` opcional, `edit-prw clean`, `--probe-appserver` log mode |

**Roadmap.**

- **v0.1** *(shipped)* — Universo 1: parser de fontes, FTS5, 13 regras lint single-file, 14 subcomandos CLI.
- **v0.2** *(shipped)* — 21k linhas de referência ADVPL/TLPP embutidas em 5 skills novas + 6 reforçadas.
- **v0.3** *(shipped)* — Universo 2 (Dicionário SX): ingest SX1..SXG, `impacto`/`gatilho`/`sx-status`, 11 cross-file `SX-001..SX-011`.
- **v0.4** *(shipped)* — Universo 3 (Rastreabilidade): `workflow`/`execauto`/`docs`.
- **v0.5/v0.6** *(shipped)* — Universo 4 (Trace + Qualidade): `trace`, `metrics`, `hotspots`, `cobertura-doc`. Schema v10.
- **v0.7** *(shipped)* — Fase 0 (Quick Wins): `WS-001/002/003`, `XF-001`, `ENC-001`, `edit-prw`, contract doc `U_EXEC` + reference MIT.
- **v0.8.0-0.8.7** *(shipped)* — Fase 1 (compile wrapper):
  - v0.8.0: base `plugadvpl compile` com modos `appre`/`cli`, schema JSON estável
  - v0.8.1: 3 bugs do smoke real (.errprw + exit_code + ok flag)
  - v0.8.2: fix `--includes` typer + filtro ruído output advpls
  - v0.8.3: onboarding (`docs/setup-compile.md` + skill workflow + hints)
  - v0.8.4: `compile --doctor` pre-flight check + skill como workflow agente
  - v0.8.5: `docs/compile-checklist.md` conversacional
  - v0.8.6: `compile --install-advpls` (copy local ou download Marketplace)
  - v0.8.7: `compile --list-servers/--add-server/--use-server/--import-tds-servers` (registry global)
- **Fases 2-5** *(planejado)* — `exec` (cliente U_EXEC), `deploy` (hot-swap RPO), `smoke`+`test`, hooks Claude Code.

Detalhes em [docs/ROADMAP.md](docs/ROADMAP.md), [CHANGELOG.md](CHANGELOG.md) e specs em `docs/universo3/`, `docs/universo4/`, `docs/fase0/`, `docs/fase1/`.

---

## Documentação

- [docs/cli-reference.md](docs/cli-reference.md) — reference completa dos 18 subcomandos com sintaxe, opções e exemplos
- [docs/compile-checklist.md](docs/compile-checklist.md) — **checklist do que coletar antes de compilar** (info conversacional pra usuário)
- [docs/setup-compile.md](docs/setup-compile.md) — guia passo-a-passo de `plugadvpl compile` (advpls + includes Protheus + AppServer + CI)
- [docs/schema.md](docs/schema.md) — schema SQLite (22 tabelas + 2 FTS5 + diagrama Mermaid + queries úteis)
- [docs/architecture.md](docs/architecture.md) — fluxo, componentes, decisões-chave e guia para contribuir com novas extrações
- [CONTRIBUTING.md](CONTRIBUTING.md) — setup local, fixtures, estilo, commits
- [CHANGELOG.md](CHANGELOG.md) — histórico de releases
- [SECURITY.md](SECURITY.md) — política de vulnerabilidades

---

## Créditos

### Análise estática (Universos 1-4 + Fase 0)

- **Parser de fontes** portado de projeto interno anterior do autor (~750 linhas, validado em aproximadamente 2.000 fontes ADVPL).
- **Lookup catalogs** (funções nativas, restritas, lint rules, SQL macros, módulos ERP, PEs) extraídos de [advpl-specialist](https://github.com/thalysjuvenal/advpl-specialist) por **Thalys Augusto** (MIT) — crédito em [NOTICE](NOTICE).

### Compilação (Fase 1)

O `plugadvpl compile` é **wrapper Python** sobre componentes oficiais da TOTVS — o plugin **NÃO** reimplementa compilador ADVPL, **NÃO** redistribui código TOTVS proprietário:

- **`advpls`** — compilador ADVPL/TLPP oficial da **TOTVS S.A.** Distribuído publicamente como parte da extensão [TDS-VSCode](https://marketplace.visualstudio.com/items?itemName=TOTVS.tds-vscode) no Microsoft Visual Studio Marketplace. Path típico após instalação: `<ext>/node_modules/@totvs/tds-ls/bin/<os>/advpls[.exe]`. Repositórios públicos relacionados: [`totvs/tds-vscode`](https://github.com/totvs/tds-vscode), [`totvs/tds-ls`](https://github.com/totvs/tds-ls).
- **`tds-ls`** (TOTVS Developer Studio Language Server) — protocolo LSP+CLI desenvolvido pela TOTVS. O modo `cli` invocado pelo `plugadvpl compile` segue o formato `.ini` documentado em [`tds-ls/TDS-CLi.md`](https://github.com/totvs/tds-ls/blob/master/TDS-CLi.md) e [`TDS-cli-script.md`](https://github.com/totvs/tds-ls/blob/master/TDS-cli-script.md).
- **`servers.json`** (`~/.totvsls/servers.json`) — formato de configuração da extensão TDS-VSCode. O `compile_servers.py` lê esse arquivo via `--import-tds-servers` sem alterá-lo, replicando estrutura compatível em `~/.plugadvpl/servers.json` (estilo dela).
- **Microsoft Visual Studio Marketplace** — hospeda o `.vsix` da extensão TDS-VSCode. O `compile --install-advpls --download` baixa do endpoint público `marketplace.visualstudio.com/_apis/public/gallery/publishers/TOTVS/vsextensions/tds-vscode/latest/vspackage` sob os [Marketplace Terms of Use](https://marketplace.visualstudio.com/terms).
- **Patterns de erro do compilador** (`lookups/compile_patterns.json`) — referenciam mensagens textuais do `advpls` documentadas publicamente em [TDN — TOTVS Developers Network](https://tdn.totvs.com/) e blogs da comunidade ([Terminal de Informação](https://terminaldeinformacao.com/), entre outros). Nenhum trecho de código binário ou fonte oficial TOTVS é distribuído neste repo.

### Comunidade

Construído pela e para a comunidade **Protheus/ADVPL brasileira**. PRs são muito bem-vindos — especialmente parser, lint rules, skills temáticas e exemplos `.prw`/`.tlpp` de produção (sanitizados).

---

## Comunidade

- **Bugs e sugestões**: [GitHub Issues](https://github.com/JoniPraia/plugadvpl/issues/new/choose)
- **Dúvidas, discussões, showcase**: [GitHub Discussions](https://github.com/JoniPraia/plugadvpl/discussions)
- **Roadmap público**: [docs/ROADMAP.md](docs/ROADMAP.md)
- **FAQ**: [docs/FAQ.md](docs/FAQ.md)

Pull requests muito bem-vindas — especialmente para parser, lint rules,
skills temáticas e exemplos `.prw/.tlpp` de produção (sanitizados).

Veja [CONTRIBUTING.md](CONTRIBUTING.md) para setup de dev.

---

## Disclaimer / Marcas registradas

**Protheus**, **ADVPL**, **TLPP** e **TOTVS** são produtos e marcas registradas
de propriedade da **TOTVS S.A.** Este plugin é um projeto independente e
**não possui vínculo** com a TOTVS, suas franquias ou representantes.

### Sobre o uso e desenvolvimento

- Este plugin **não utiliza, redistribui ou expõe nenhum código-fonte do
  produto padrão Protheus** (rotinas TOTVS internas, RPO, fontes oficiais).
- A ferramenta foi desenvolvida e validada **exclusivamente sobre fontes
  customizados** (User Functions, customizações MVC, pontos de entrada,
  WebServices, jobs e demais arquivos `.prw`/`.tlpp`/`.prx` escritos pelos
  próprios clientes em seus ambientes).
- Os catálogos embarcados (funções nativas, funções restritas, módulos ERP,
  pontos de entrada padrão) contêm apenas **nomes e metadados publicamente
  documentados** na [TDN — TOTVS Developers Network](https://tdn.totvs.com/).
  Não há código-fonte proprietário embutido.
- Os exemplos `.prw`/`.tlpp` distribuídos em `skills/<x>/exemplos/` são
  **código original do autor**, escritos para ilustrar padrões de
  customização (não derivados de fontes padrão TOTVS).
- Cabe a cada usuário garantir que possui direito de acesso e análise sobre
  os fontes que indexar com este plugin (tipicamente customizações da própria
  empresa ou de cliente sob contrato).

---

## Licença

[MIT](LICENSE) © 2026 JoniPraia.
