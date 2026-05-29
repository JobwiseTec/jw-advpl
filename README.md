# plugadvpl

[![PyPI version](https://img.shields.io/pypi/v/plugadvpl.svg?logo=pypi&logoColor=white)](https://pypi.org/project/plugadvpl/)
[![Python](https://img.shields.io/pypi/pyversions/plugadvpl.svg?logo=python&logoColor=white)](https://pypi.org/project/plugadvpl/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/JoniPraia/plugadvpl/actions/workflows/ci.yml/badge.svg)](https://github.com/JoniPraia/plugadvpl/actions/workflows/ci.yml)
[![PyPI downloads](https://img.shields.io/pypi/dm/plugadvpl.svg?logo=pypi&logoColor=white)](https://pypi.org/project/plugadvpl/)
[![GitHub stars](https://img.shields.io/github/stars/JoniPraia/plugadvpl?logo=github)](https://github.com/JoniPraia/plugadvpl/stargazers)

> Plugin Claude Code + CLI Python que indexa fontes **ADVPL/TLPP** (TOTVS Protheus) em SQLite com FTS5 — para o Claude responder sobre o seu Protheus sem queimar contexto lendo `.prw` cru.

> ⚠️ **EDITANDO `.prw` cp1252?** Read/Edit do Claude são UTF-8 only — bytes acentuados viram `?` e o Edit corrompe acentos não-editados. **Use sempre `plugadvpl edit-prw stage <arq>` ANTES e `commit <arq>` DEPOIS**. Detalhes: skill `/plugadvpl:edit-prw` ou seção [Encoding](#encoding) abaixo.

---

## Por que plugadvpl

- **Economia de tokens.** Um `.prw` médio tem 1.000 a 10.000 linhas. Abrir cru custa de 5k a 50k tokens. Com plugadvpl, a mesma pergunta é respondida via metadados estruturados — **~16× menos contexto** em projetos reais.
- **Parser provado em campo.** O extrator de funções, tabelas, SQL embarcado e call graph foi portado de um parser interno do autor, validado em aproximadamente **2.000 fontes ADVPL**. Não é um experimento de fim de semana.
- **MIT, sem telemetria, 100% local.** Índice SQLite mora em `.plugadvpl/index.db` dentro do seu repo. Nenhum dado sai da máquina. Funciona offline.
- **Interop Sonar TOTVS oficial.** Cada finding de `lint` carrega o ID Sonar oficial (`BG1000`, `CA1004`, …) quando há equivalência no catálogo `sonar-rules.engpro.totvs.com.br`. Quem já roda Sonar no CI reconhece o finding pelo ID oficial; quem não roda continua com o `regra_id` interno. Ver [Interop com Sonar TOTVS](#interop-com-sonar-totvs).

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

O CLI Python expõe **30 subcomandos**, todos espelhados em slash commands do plugin Claude Code. Histórico de qual versão entregou cada comando está em [Evolução por versão](#evolução-por-versão).

### Fontes

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
| `/plugadvpl:arch <arq>` | **Visão arquitetural** — use SEMPRE antes de `Read`. Inclui `tabelas_via_execauto_resolvidas` |
| `/plugadvpl:lint [arq]` | Lint findings (`--severity`, `--regra`, `--cross-file`) |
| `/plugadvpl:doctor` | Diagnósticos (encoding, órfãos, FTS sync, lookups) |
| `/plugadvpl:grep <pattern>` | Busca textual nos chunks (`--mode fts/literal/identifier`) |
| `/plugadvpl:help` | Lista comandos (atalho do CLI `--help`) |

### Dicionário SX

| Comando | Função |
|---|---|
| `/plugadvpl:ingest-sx <pasta-csv>` | Ingere dicionário SX exportado em CSV (sx1..sxg) |
| `/plugadvpl:impacto <campo>` | **Killer feature** — cruza referências a um campo em fontes ↔ SX3 ↔ SX7 ↔ SX1 (`--depth 1..3`) |
| `/plugadvpl:gatilho <campo>` | Cadeia de gatilhos SX7 origem → destino (`--depth 1..3`) |
| `/plugadvpl:sx-status` | Counts por tabela do dicionário SX |

### Rastreabilidade

| Comando | Função |
|---|---|
| `/plugadvpl:workflow` | Lista os 4 mecanismos de execução não-direta: `workflow`/`schedule`/`job_standalone`/`mail_send` (filtros `--kind`/`--target`/`--arquivo`) |
| `/plugadvpl:execauto` | Resolve `MsExecAuto({\|x,y,z\| MATA410(x,y,z)}, ...)` → rotina canônica + módulo + tabelas inferidas (filtros `--routine`/`--modulo`/`--op`/`--dynamic`) |
| `/plugadvpl:docs [modulo]` | Catálogo de Protheus.doc agregado por módulo/autor/tipo. Modo `--show <fn>` em Markdown estruturado, `--orphans` cruza com BP-007 |

### Trace + Qualidade

| Comando | Função |
|---|---|
| `/plugadvpl:trace <entidade>` | Grafo unificado cross-universo: dado um `campo`/`funcao`/`tabela`/`arquivo`/`parametro`/`pergunte`, devolve TODOS os pontos onde aparece (fontes + SX + workflow + jobs + ExecAuto + Protheus.doc) |
| `/plugadvpl:metrics [arq]` | Métricas por função: complexidade ciclomática McCabe (`cc`), LOC, nesting, fan-out, params, `has_doc` |
| `/plugadvpl:hotspots` | Top-N funções por critério (`--tipo user_func/method/calls/risk`) — onde começar refactor |
| `/plugadvpl:cobertura-doc` | % de funções com Protheus.doc por módulo ou tipo de source |

### Runtime ADVPL — edit + compile

| Comando | Função |
|---|---|
| `/plugadvpl:edit-prw {check\|open\|save\|stage\|commit}` | Conversão CP1252↔UTF-8 in-place. Workflow `stage`→edita→`commit` evita corromper acentos ao editar `.prw` com Claude |
| `/plugadvpl:edit-prw clean [target]` | Remove `.bak` acumulado dos ciclos stage/commit. `--dry-run` lista sem deletar, `--yes` skipa confirmação |
| `/plugadvpl:compile <fonte>` | Compila ADVPL via wrapper sobre binário oficial `advpls` (TOTVS). 2 modos: `appre` (local, pré-processador) ou `cli` (full via AppServer TCP) |
| `/plugadvpl:compile --doctor` | Pre-flight check estruturado em JSON. Auto-detecta advpls + includes + AppServer. Retorna `next_actions` ordenadas pro agente seguir |
| `/plugadvpl:compile --install-advpls` | Instalação gerenciada do binário em `~/.plugadvpl/advpls/`. Interativo: copia de path local OU baixa do Marketplace VSCode (~118MB) — sempre pede confirmação |
| `/plugadvpl:compile --list-servers` / `--add-server` / `--use-server <nome>` / `--import-tds-servers` | Registry global de AppServers em `~/.plugadvpl/servers.json` (estilo TDS-VSCode). Cadastra uma vez, usa em qualquer projeto |
| `/plugadvpl:compile --all-envs` | Compila pra **todos** os environments do `--use-server` (RPO sync entre envs — ex: `protheus` + `protheus_rest`) |
| `/plugadvpl:compile --set-restart-cmd <server> --cmd "<cmd>"` | Configura o `restart_cmd` do server no registry global (consumido pelo `tq`) |
| `/plugadvpl:tq --use-server <nome>` | Restart do AppServer + healthcheck HTTP (Troca Quente MVP local). Encadeia bem com `compile --all-envs` |
| `/plugadvpl:compile --probe-appserver <host:port \| path>` | Descobre build do AppServer. Modo **network** (`host:port`) invoca `advpls cli action=validate`, retorna build + flag SSL. Modo **log** (path) parseia `protheus.log` como fallback offline |
| `/plugadvpl:compile --set-credentials <server>` / `--clear-credentials <server>` | Salva user+senha no **cofre nativo do OS** (Win Credential Manager / macOS Keychain / Linux Secret Service). Prompt seguro com `getpass`. Plugin nunca grava senha em arquivo |
| `/plugadvpl:compile --explain-config` | JSON estruturado mostrando ordem de precedência (CLI flag > runtime.toml > registry > keyring > env > auto-detect) + de onde veio cada campo + estado das credenciais (senha sempre redacted) |

**Setup zero-config recomendado**:
```bash
# 1x na vida em cada máquina:
plugadvpl compile --install-advpls               # baixa/copia advpls (~118MB)
plugadvpl compile --import-tds-servers --yes     # se já tem TDS-VSCode
plugadvpl compile --set-credentials <nome>       # prompt seguro, salva no cofre

# Daí em diante, em qualquer projeto, qualquer shell — zero env var, zero runtime.toml:
plugadvpl compile --mode cli --use-server <nome> FONTE.PRW

# appre (sem AppServer) nem precisa de credencial:
plugadvpl compile --mode appre --use-server <nome> FONTE.PRW
```

Detalhes em [docs/compile-checklist.md](docs/compile-checklist.md) (info conversacional do que coletar) e [docs/setup-compile.md](docs/setup-compile.md) (guia técnico passo-a-passo).

### Auditoria de ambiente Protheus

| Comando | Função |
|---|---|
| `/plugadvpl:ini-audit [paths]` | Audita `appserver.ini`/`dbaccess.ini`/`smartclient.ini`/`tss.ini`/`broker.ini` contra **487 regras TDN-oficiais** filtradas por tipo+role (14 roles: `broker_http`/`slave_rest`/`dbaccess_master`/...). Auto-discover via glob, cache hash+mtime, `--severity critical/warning/info`, `--show-ok-with-note` pra justificativas documentadas |
| `/plugadvpl:log-diagnose [paths]` | Diagnostica `console.log`/`error.log`/`profile.log`/`compila.log` contra **19 alert rules** + **93 correction tips** com URL TDN. Pipeline 2 estágios (tokenize → match reverso); janela `--since 24h` relativa ao último timestamp do log; `--category database/thread_error/rpo/...`, captura `ORA-xxx`/username/host quando aparece |

### Ingestão ao vivo via REST

| Comando | Função |
|---|---|
| `/plugadvpl:ingest-protheus --endpoint <url>` | Consome `COLETADB.tlpp` no AppServer Protheus via REST. Bundle pattern: `/coletadb/run` retorna manifest com 21 CSVs (paths + sizes + hash), `/coletadb/file` baixa cada CSV em chunks de 4MB com verificação de integridade. Auth via HTTP Basic (mesmo cofre do `compile`). Modo `enxuto` (≥ threshold rows) ou `completo` |
| Cobertura completa do dicionário | Plugin consome **todas** as 21 tabelas do bundle COLETADB: 11 SX padrão (SX1..SXG+SIX) + 3 SX adicional (XXA/XAM/XAL) + 6 menu (`mpmenu_*`) + SCHEDULES (XX0/XX1/XX2 com recorrência decodificada) + JOBS (parse de `appserver*.ini`) + RECORD_COUNTS (inventário de rows físicas → `tabelas.num_rows`) |
| Hash dinâmico | Manifest emite `hash`+`hash_algo`+`hash_partial` (algumas builds Protheus não têm `Sha2_256`). Cliente escolhe `hashlib.new(algo)` (sha256/sha1/md5) e respeita partial-hash pra arquivos > 64KB onde `MemoRead` trunca. Mantém compat com campo `sha256` legado |

Reference impl do servidor: [`docs/reference-impl/coletadb.tlpp`](docs/reference-impl/coletadb.tlpp) (MIT, ~1900 linhas). Reference completa dos subcomandos: [docs/cli-reference.md](docs/cli-reference.md).

---

## Interop com Sonar TOTVS

Se você ou seu cliente já roda **SonarQube** com o catálogo oficial TOTVS publicado em [`sonar-rules.engpro.totvs.com.br`](https://sonar-rules.engpro.totvs.com.br) (referenciado pelas skills do repositório oficial [`totvs/engpro-advpl-tlpp-skills`](https://github.com/totvs/engpro-advpl-tlpp-skills)), nosso `lint` fala a mesma língua: cada finding traz o **ID Sonar oficial** junto com nosso `regra_id` interno.

**Convenção:**

- ID puro (ex: `BG1000`) — **equivalência forte**, mesma regra/descrição que o Sonar oficial.
- Prefixo `~` (ex: `~CA1004`) — **adjacente/parcial**, nossa regra cobre um subconjunto ou variação da Sonar.
- Lista vazia `[]` — **regra exclusiva nossa**, sem equivalente Sonar oficial (a maioria, e é argumento de venda: cobrimos coisas que nem o Sonar TOTVS cobre).

**Mapeamentos fortes hoje:**

| Nossa regra | Sonar oficial | O que detecta |
|---|---|---|
| `SEC-001` | `BG1000` | `RpcSetEnv`/`RpcSetType` dentro de WSRESTFUL |
| `SEC-004` | `CA2052` | Credenciais hardcoded no fonte |
| `MOD-001` | `CA1004` | `ConOut`/`OutErr`/`?` em vez de `FwLogMsg` |

**Adjacentes (`~`):** `BP-008`, `SEC-003`, `SEC-005`, `MOD-004`, `PERF-001`, `SX-007`, `ENC-001` — cobrem famílias parciais (`CA2017`-`CA2025`, `CS1000`, `CA0000`, `BG1100`, etc).

**Como aparece no output:**

```bash
plugadvpl lint --regra SEC-001 -f json
# [
#   {
#     "arquivo": "WSReg.tlpp",
#     "regra_id": "SEC-001",
#     "severidade": "critical",
#     "sonar_rules": ["BG1000"]
#   }
# ]
```

Sem mapeamento, `sonar_rules` vem como `[]` — não quebra parsers downstream. O catálogo completo de mapeamentos vive em [`cli/plugadvpl/lookups/lint_rules.json`](cli/plugadvpl/lookups/lint_rules.json) (chave `sonar_rules` em cada regra).

> 100% offline, **sem dependência** do Sonar instalado. O mapeamento é só uma ponte de nomenclatura — você roda nosso `lint` sozinho ou em conjunto com o Sonar TOTVS sem nenhum conflito.

---

## Skills incluídas

Além dos 30 command wrappers (1 por subcomando do CLI + `help` + `setup`), o plugin traz **19 knowledge skills** carregadas pelo Claude conforme contexto:

| Skill | Quando carrega |
|---|---|
| `plugadvpl-index-usage` | Skill-chefe — força consulta ao índice antes de qualquer `Read` em fonte ADVPL |
| `advpl-fundamentals` | Notação húngara, naming, prefixos de módulo, 195 funções restritas |
| `advpl-encoding` | cp1252 (.prw) vs utf-8 (.tlpp) — **inclui workflow seguro de Edit (stage/commit)** |
| `edit-prw` | **Workflow operacional pra editar `.prw` cp1252 com Claude sem corromper acentos** |
| `advpl-mvc` | MenuDef/ModelDef/ViewDef, hooks bCommit/bTudoOk, FWFormStruct |
| `advpl-mvc-avancado` | Eventos MVC, validações cruzadas, FWMVCRotAuto |
| `advpl-tlpp` | TLPP moderno — OO, namespaces, annotations, tipagem opcional + defaults |
| `advpl-tlpp-named-params` | Parâmetros nomeados na chamada via operador `=` (AppServer 20.3.2.0+ funções/métodos, 24.3.1.0+ construtores) |
| `advpl-embedded-sql` | BeginSql/EndSql, TCQuery, `%xfilial%`, `%notDel%`, `%table%` |
| `advpl-pontos-entrada` | User Function NOME(PARAMIXB), retorno via PARAMIXB[última] |
| `advpl-webservice` | REST (`WSRESTFUL`, `@Get/@Post`) e SOAP — inclui gotcha `SetKeyHeaderResponse` em build 7.00.240223P + `@Post` só com `User Function` (não Static/Method) |
| `advpl-web` | Interfaces web — Webex / HTML / WebExpress |
| `advpl-jobs-rpc` | `RpcSetEnv`, `StartJob`, `MsRunInThread`, funções proibidas em job |
| `advpl-matxfis` | Família fiscal (NF-e, SPED, ECF, REINF, integração SF2/SD2/SF3) |
| `advpl-advanced` | Threads, IPC, debug, OO em profundidade |
| `advpl-dicionario-sx` | Estrutura SX1/SX2/SX3/SX5/SX6/SX7/SIX/SXA/SXB + cookbook SQL pra criar campo (clonar bitmap `X3_USADO`, checklist, armadilhas v12.1.7+) |
| `advpl-dicionario-sx-validacoes` | Expressões ADVPL embutidas em X3_VALID/INIT/WHEN/VLDUSER, X7_REGRA, X1_VALID, X6_VALID/INIT — guia pra análise de impacto |
| `advpl-refactoring` | 6 padrões com before/after (DbSeek loop, Posicione repetido, IFs hardcoded, AxCadastro→MVC, string concat em loop, RecLock sem Begin Transaction) — usar quando o pedido for "melhorar"/"refatorar"/"está lento" |
| `advpl-debugging` | Top 30 erros comuns em produção + métodos de debug — inclui seção `Begin Sequence / Recover` precisa de `ErrorBlock({\|e\| Break(e)})` pra capturar exceptions nativas (TOPCONN, REST, native) |
| `advpl-code-review` | 40 regras BP/SEC/PERF/MOD/SX (28 single-file + 11 cross-file `SX-001..SX-011` + 1 encoding) |
| `ingest-protheus` | Workflow do `ingest-protheus` (REST ao vivo via COLETADB) |

Também incluídos: **5 agents** especializados (`advpl-analyzer`, `advpl-impact-analyzer`, `advpl-code-generator`, `advpl-reviewer-bot`, `advpl-log-investigator`), **1 SessionStart hook** Node.js que faz onboarding cross-platform do `.plugadvpl/` e **2 auditores** (`advpl-ini-auditor`, `advpl-log-investigator`) que envelopam `ini-audit`/`log-diagnose` com correction tips TDN.

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

### Universo 1 — Ingestão de fontes

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

### Universo 2 — Dicionário SX

**O que faz**: `plugadvpl ingest-sx <pasta-csv>` ingere o dicionário SX exportado do Configurador (SIGACFG → Misc → Exportar Dicionário em CSV) em 11 tabelas: `tabelas` (SX2), `campos` (SX3), `gatilhos` (SX7), `parametros` (SX6), `perguntas` (SX1), `consultas` (SXB), `pastas` (SXA), `relacionamentos` (SX9), `indices` (SIX), `tabelas_genericas` (SX5), `grupos_campo` (SXG).

**Por design**: ingere apenas customizações do cliente (`X3_NIVEL > 1`). O padrão TOTVS é ignorado — o plugin **não redistribui dicionário TOTVS** (questão de licença).

**Cruzamento**: campos do SX3 são cruzados com `fonte_chunks.content` (busca substring) → quem usa o campo. SX7 (gatilhos) origem→destino vira cadeia rastreável. SX1 (perguntas) cruza com `Pergunte("XXX", .F.)` nos fontes.

**Killer feature**: `plugadvpl impacto <campo>` cruza referências do campo em **3 camadas** (fontes + SX3 trigger fontes + SX7 destino + SX1 onde aparece) com profundidade `--depth 1..3`. Em um campo central tipo `A1_COD` retorna grafo de impacto que ajuda a estimar refactors.

**Comandos**: `ingest-sx`, `impacto`, `gatilho`, `sx-status` + **11 regras cross-file** `SX-001..SX-011` (X3_VALID chama função inexistente, X7_REGRA aponta pra campo inexistente, MV_PAR* não usado em fonte, etc.).

### Universo 3 — Rastreabilidade

**O que faz**: indexa formas de execução **não-direta** que `callers`/`callees` não pegam (porque não há call literal):

- **Workflow / Schedule / Job standalone / Mail** (`MsWorkflow`, `TWFProcess`, `WFPrepEnv`, `Schedule`, `StartJob` daemon, `MailSendMail`)
- **ExecAuto chain**: `MsExecAuto({|x,y,z| MATA410(x,y,z)}, aHeader, aItems, nOpcAuto)` — resolve a **rotina canônica** (`MATA410` → "Pedido de Venda"), o módulo (SIGAFAT), e infere as tabelas afetadas (SC5/SC6 pra MATA410, SE1 pra MATA440, etc.) via lookup `lookups/execauto_routines.json`
- **Protheus.doc agregado**: parse de blocos `/*/{Protheus.doc} NomeFn ... /*/`  e cruzamento com `funcoes` da fonte_chunks → catálogo navegável por módulo/autor/tipo

**Comandos**: `workflow`, `execauto`, `docs` (`--show <fn>` em Markdown, `--orphans` cruza com BP-007).

### Universo 4 — Trace + Qualidade

**O que faz**: 2 features distintas que fecham o ciclo de análise.

**Feature A — Trace unificado** (`plugadvpl trace <entidade>`): dado um nome (campo SX3, função ADVPL, tabela, arquivo, parâmetro MV_*, pergunte SX1), o auto-detect decide o tipo e cruza **TODOS os universos** em uma resposta única: aparece em quais fontes, quais validações SX, quais gatilhos, quais workflows, quais jobs, quais chamadas ExecAuto, qual Protheus.doc. Mata necessidade de rodar 5 comandos diferentes pra entender uma entidade.

**Feature B — Qualidade & métricas** (schema v10, tabela `fonte_metrics`):
- `plugadvpl metrics [arq]` — McCabe cyclomatic complexity, LOC, max nesting, fan-out, params_count, has_doc por função
- `plugadvpl hotspots` — top-N funções por critério (`--tipo user_func/method/calls/risk`) — onde começar refactor
- `plugadvpl cobertura-doc` — % de funções com Protheus.doc por módulo ou source_type

### Fase 0 — Quick wins

**Lint rules de runtime** que só faziam sentido depois do parser maduro:

- **WS-001/002/003** — WSMETHOD sem WSSERVICE, `GetContent`+`FromJson` sem `DecodeUtf8`, `SetResponse` sem `EncodeUtf8` em WSRESTFUL
- **XF-001** — `MsSeek(xFilial("XX"))` em tabela `x2_modo='E'` dentro de REST/JOB sem `RpcSetEnv` precedente (bug silencioso crítico: `cFilAnt` vazia, xFilial retorna "")
- **ENC-001** — `.prw`/`.prx` salvo em UTF-8 quebra compilador appserver legado
- **Comando `edit-prw`** — conversão CP1252↔UTF-8 com backup
- **Contract doc `U_EXEC`** + reference impl MIT (`docs/examples/uexec.prw`) pra execução headless de função ADVPL via REST (pavimenta Fase 2)

### Fase 1 — Compilação

**`plugadvpl compile <fonte>`** é um **wrapper Python sobre o binário oficial `advpls`** (TOTVS — distribuído na extensão TDS-VSCode pública). Devolve **JSON estruturado** consumível por CI, com auto-detect de includes, modo `appre` (local) ou `cli` (full via AppServer).

Veja a seção dedicada [**Compilação ADVPL**](#compilação-advpl) logo abaixo pra entender a estrutura e o que chama quando.

---

## Compilação ADVPL

Camada de runtime que fecha o ciclo "ler/analisar → **compilar** → executar → testar".

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

### Workflow zero-config para usuário novo

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

- **Credenciais NUNCA gravadas em arquivo do plugin** — só nomes de env var no `runtime.toml` e no `servers.json`. Senha vive em UM destes lugares (em ordem de precedência): env var → **cofre nativo do OS** (Win Credential Manager / macOS Keychain / Linux Secret Service, cifrado por DPAPI/Keychain/SecretService) → erro didático
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

Estado atual do projeto. Histórico detalhado em [Evolução por versão](#evolução-por-versão) mais abaixo.

- **30 subcomandos** cobrindo parser de fontes, dicionário SX, rastreabilidade, trace + qualidade, edit-prw cp1252, compile via `advpls`, ingestão REST do Protheus ao vivo e auditoria de INI + log
- **50 skills** (19 knowledge + 31 slash command wrappers), 5 agents especializados (`advpl-analyzer`, `advpl-code-generator`, `advpl-reviewer-bot`, `advpl-impact-analyzer`, `advpl-log-investigator`), 1 SessionStart hook
- **Schema SQLite v15** — 15 migrations cobrindo todos os universos (incluindo `dominios`/`classificacoes_lgpd`/`schedules`/`jobs`/6 tabelas `mpmenu_*`)
- **40 lint rules** (28 single-file + 11 cross-file + 1 encoding) cobrindo best-practice, security, performance, modernization, dicionário SX, webservice
- **1051 testes verde** (unit + integration + bench + smoke real opcional) — ~57s suite full
- Reference impl MIT do servidor REST `coletadb.tlpp` v1.0.3 — bundle pattern com 21 CSVs em chunks de 4MB e hash dinâmico sha256/sha1/md5

### Próximas entregas

- **`apply-patch`** — aplicar `.PTM` via advpls, idempotente com backup. Issue [#4](https://github.com/JoniPraia/plugadvpl/issues/4)
- **`sx-drift`** — compara dicionário SX local vs estado atual do AppServer via REST, mostra drift por tabela/campo

---

## Evolução por versão

Histórico detalhado do que cada release entregou. Newest first. CHANGELOG completo em [CHANGELOG.md](CHANGELOG.md).

### v0.15.0 — Guarda contra restart acidental em PROD

- **`plugadvpl tq --confirm-prod`** — server marcado como produção (via `plugadvpl compile --mark-prod <nome>`) exige a flag explícita; `--no-prod` desfaz. `--dry-run` continua dispensando a guarda (preview não causa side-effect)
- **Campo `is_prod`** no `Server` dataclass — default `False`, backwards-compat com registry existente. `compile --list-servers` mostra marcador `PROD` ao lado do nome
- 7 testes integration novos
- Issue [#5](https://github.com/JoniPraia/plugadvpl/issues/5) fechada — escopo MVP local entregue; itens PROD-grade restantes (`.ini` editing, RPO versionado, rollback automático, sub-plugin `plugadvpl-ops`) descartados ([análise](https://github.com/JoniPraia/plugadvpl/issues/5#issuecomment-4553802738))

### v0.14.1 — Hints acionáveis no `tq` + skill `/plugadvpl:deploy`

- **Hints estruturados quando `tq` falha** — antes só mostrava `healthcheck timeout após N tentativas`; agora lista `console.log` do AppServer, valida `--port` vs porta REST configurada, sugere bump de `--timeout`. Mesmo padrão pra `restart_cmd` exit non-zero
- **Skill `/plugadvpl:deploy`** — orquestrador `compile → tq → smoke` num passo só. Pre-flight, encadeamento `&&` (compile com erro aborta antes do restart), tabela de troubleshoot pós-deploy

### v0.14.0 — Troca Quente MVP local + compile multi-env

- **`plugadvpl tq`** — restart do AppServer (via `restart_cmd` configurado no server) + healthcheck HTTP esperando 200/401/404 (5xx não conta como up). Flags `--use-server`, `--port` (override só pro healthcheck quando REST roda em porta diferente do TCP), `--timeout` (default 60s), `--no-healthcheck`, `--dry-run`. Resolve o passo manual de `restart-totvs.bat` + curl loop pós-`compile`
- **`plugadvpl compile --set-restart-cmd <server> --cmd "<cmd>"`** — configura o `restart_cmd` no registry global. Valida que `--cmd` veio junto, erra com hint pra `--list-servers` se o server não existe
- **`plugadvpl compile --all-envs`** — compila pra todos os environments do `--use-server` em sequência, anota linha com coluna `env`, exit code é o pior dos envs. Caso de uso: server com `protheus` + `protheus_rest` precisa de RPO sync entre os 2; antes era cópia manual `apo/custom.rpo` → `apo_rest/custom.rpo`
- **Skill `/plugadvpl:tq`** — wrapper slash command pro subcomando
- 16 testes novos (8 unit em `tq.py` + 5 integration do subcomando + 3 do `--set-restart-cmd`). Issue [#5](https://github.com/JoniPraia/plugadvpl/issues/5) — escopo cortado pra MVP local

### v0.13.1 — Hash dinâmico no cliente REST + docs sync

- Cliente Python (`coletadb_client.py`) aceita campos `hash` + `hash_algo` + `hash_partial` do manifest v1.0.3+ do servidor. Escolhe `hashlib.new(algo)` dinamicamente (sha256/sha1/md5); quando `hash_partial=True` hasheia só os primeiros 65535 bytes pra casar com `MemoRead` truncado do server. Fallback pro campo legado `sha256` (servers v1.0.x). 6 testes unitários novos
- Reference impl `coletadb.tlpp` v1.0.3 — 3 fixes da issue #9: `HashSha256Arquivo` → `HashArquivo` com fallback Sha1/MD5 (build 7.00.240223P não tem Sha2_256), `DiretorioBundle` OS-aware via `IsSrvUnix()`, `InventarioCarregar` distingue Nil (falha real) de `{}` (threshold filtrou tudo)
- Skill nova `advpl-tlpp-named-params` — named arguments TLPP via operador `=` (não `:=` nem `:`); AppServer 20.3.2.0+ pra funções/métodos, 24.3.1.0+ pra `Classe():New()`
- 4 gotchas reais do smoke incorporados nas skills:
  - `advpl-webservice`: `SetHeaderResponse` → `SetKeyHeaderResponse` (build 7.00+ rejeita 2-args na variante sem `Key`); `@Post`/`@Get` só funciona com `User Function` (não `Static Function` nem `Method`)
  - `advpl-debugging`: nova seção sobre `Begin Sequence / Recover` precisar de `ErrorBlock({|e| Break(e)})` antes pra capturar exceptions nativas (TOPCONN, REST, native)
  - `advpl-tlpp`: gotcha `function` lowercase rejeitada em build 7.00.x mesmo com `tlpp-core.th`
- Docs sync: `skills/ingest-protheus/SKILL.md` reflete cobertura 21/21; `docs/reference-impl/README.md` ganha seção "Hash do bundle (v1.0.3+)"

### v0.13.0 — Cobertura 100% do bundle COLETADB

- **Universo 6 (Workflow)**: ingestão de `schedules` (XX0/XX1/XX2 com recorrência decodificada pelo COLETADB — `tipo_recorrencia`, `detalhe_recorrencia`, `recorrencia_raw` pra debug) e `jobs` (parse recursivo de `appserver*.ini` com PK `(arquivo, sessao)` e índice em `rotina_main`). Migration 014
- **Universo 8 (Menus)**: 6 tabelas relacionais — `mpmenu_menu` (raiz, SIGAFAT/SIGAEST/...), `mpmenu_function` (funções ADVPL referenciadas), `mpmenu_item` (hierarquia com FK menu + self-FK pai), `mpmenu_i18n` (descrições traduzidas PT/ES/EN), `mpmenu_key_words`, `mpmenu_rw`. Migration 015
- Plugin agora ingere **TODOS** os 21 CSVs do bundle COLETADB: 11 SX padrão + 3 SX adicional (XXA/XAM/XAL) + 6 menu + SCHEDULES + JOBS + RECORD_COUNTS
- CSVs MPMENU usam `R_E_C_D_E_L_="1"` em vez de `D_E_L_E_T_="*"` das SX — helper `_row_is_deleted_recnod()` cobre os dois
- Reference impl `coletadb.tlpp` v1.0.1: `SetHeaderResponse` → `SetKeyHeaderResponse` (19 ocorrências) + BEGIN SEQUENCE individual por extração pra falha parcial em base sem schema completo
- Smoke validado contra Protheus 7.00.240223P: 461.956 SX rows + 5.181 LGPD/dominios + 66.098 menu rows

### v0.12.0 — Universo 2 estendido + RECORD_COUNTS

- Ingestão de XXA/XAL/XAM (3 SX adicional do bundle COLETADB) — tabelas que o MVP do v0.11 não cobria
- `RECORD_COUNTS.csv` post-processado pra popular `tabelas.num_rows` com inventário de rows físicas via DBMS query (em vez de COUNT(*) por tabela). Permite ordenar/filtrar tabelas por tamanho real
- Cobertura subiu de 11/21 → 15/21 CSVs do bundle

### v0.11.0 — Universo 5b: ingest ao vivo via REST

- **`plugadvpl ingest-protheus --endpoint <url>`**: consome `COLETADB.tlpp` no AppServer Protheus via REST. Bundle pattern:
  1. `POST /coletadb/run` → servidor gera CSVs locais em `\temp\<ts>_<uuid>\` + retorna manifest JSON com paths/sizes/hashes
  2. `POST /coletadb/file` → cliente baixa cada CSV em chunks de 4MB com verificação de integridade
  3. `ingest_sx(tmp_dir)` → reusa machinery existente do CSV path
- Auth via HTTP Basic (`AppServer Security=1`) reutilizando o cofre nativo do `compile`
- Modo `enxuto` (≥ threshold rows, default 10) ou `completo` (todas as SX inclusive vazias)
- Paridade funcional com `ingest-sx`: mesmo dataset baixado via REST produz o mesmo DB que o CSV path produziria
- Reference impl `coletadb.tlpp` v1.0.0 entregue em `docs/reference-impl/` (MIT, ~1800 linhas)

### v0.10 — Universo 5: auditoria de ambiente Protheus

- **`/plugadvpl:ini-audit`** — audita `appserver.ini`/`dbaccess.ini`/`smartclient.ini`/`tss.ini`/`broker.ini` contra **487 regras TDN-oficiais** filtradas por tipo+role. 14 roles cobertas (`broker_http`, `slave_rest`, `dbaccess_master`, `tss_emissor`, etc). Auto-discover via glob, cache por hash+mtime, severidades `critical`/`warning`/`info`, `--show-ok-with-note` pra justificar exceções
- **`/plugadvpl:log-diagnose`** — diagnostica `console.log`/`error.log`/`profile.log`/`compila.log` contra **19 alert rules** + **93 correction tips** com URL TDN pra cada. Pipeline 2 estágios (tokenize → match reverso); janela `--since 24h` relativa ao último timestamp do log; `--category database/thread_error/rpo/`...; captura `ORA-xxx`/username/host quando aparece
- 2 agents novos: `advpl-ini-auditor`, `advpl-log-investigator`

### v0.9 — Cofre nativo do OS + zero-config

- **`compile --set-credentials <server>`** / `--clear-credentials <server>` — user+senha no Win Credential Manager / macOS Keychain / Linux Secret Service. Prompt seguro com `getpass`, plugin nunca grava senha em arquivo
- **`compile --explain-config`** — JSON estruturado mostrando ordem de precedência (CLI flag > runtime.toml > registry > keyring > env > auto-detect) + de onde veio cada campo (senha sempre redacted)
- `--use-server + --mode appre` deixou de exigir credenciais (appre é pré-processador local)
- v0.9.3 reescreve skill `advpl-webservice`: comparação WSRESTFUL × notation (`@Get/@Post`), ~3× speedup do notation, `@Patch` exclusivo, REST-DOC/Swagger automático
- v0.9.4 fix install: `marketplace.json` trocou `source: github` → `source: url` com HTTPS explícita (resolve `Permission denied (publickey)` em users sem SSH key)

### v0.8 — Fase 1: compile wrapper sobre `advpls`

- **`plugadvpl compile <fonte>`** — wrapper sobre binário oficial `advpls` (TOTVS) em 2 modos: `appre` (local, pré-processador) ou `cli` (full via AppServer TCP)
- `compile --doctor` — pre-flight check estruturado em JSON. Auto-detecta advpls + includes + AppServer. Retorna `next_actions` ordenadas
- `compile --install-advpls` — instalação gerenciada do binário em `~/.plugadvpl/advpls/`. Interativo: copia de path local OU baixa do Marketplace VSCode (~118MB), sempre pede confirmação
- `compile --list-servers` / `--add-server` / `--use-server <nome>` / `--import-tds-servers` — registry global de AppServers em `~/.plugadvpl/servers.json` estilo TDS-VSCode
- `compile --probe-appserver <host:port | path>` — descobre build do AppServer. Modo network invoca `advpls cli action=validate`; modo log parseia `protheus.log` offline

### v0.7 — Fase 0: Quick Wins

- **`/plugadvpl:edit-prw {check|open|save|stage|commit}`** — conversão CP1252↔UTF-8 in-place. Workflow `stage`→edita→`commit` evita corromper acentos ao editar `.prw` com Claude
- 5 regras de lint novas: `WS-001`/`WS-002`/`WS-003` (webservice), `XF-001` (xFilial), `ENC-001` (encoding)
- Contract doc `U_EXEC` + reference impl MIT (precursor do COLETADB)

### v0.5/v0.6 — Universo 4: Trace + Qualidade

- **`/plugadvpl:trace <entidade>`** — grafo unificado cross-universo: dado um `campo`/`funcao`/`tabela`/`arquivo`/`parametro`/`pergunte`, devolve TODOS os pontos onde aparece (fontes + SX + workflow + jobs + ExecAuto + Protheus.doc)
- **`/plugadvpl:metrics [arq]`** — complexidade ciclomática McCabe, LOC, nesting, fan-out, params, `has_doc` por função
- **`/plugadvpl:hotspots`** — Top-N funções por critério (`--tipo user_func/method/calls/risk`) pra priorizar refactor
- **`/plugadvpl:cobertura-doc`** — % de funções com Protheus.doc por módulo

### v0.4 — Universo 3: Rastreabilidade

- **`/plugadvpl:workflow`** — lista os 4 mecanismos de execução não-direta: `workflow`/`schedule`/`job_standalone`/`mail_send`
- **`/plugadvpl:execauto`** — resolve `MsExecAuto({|x,y,z| MATA410(x,y,z)}, ...)` → rotina canônica + módulo + tabelas inferidas
- **`/plugadvpl:docs [modulo]`** — catálogo de Protheus.doc agregado por módulo/autor/tipo. Modo `--show <fn>` em Markdown estruturado, `--orphans` cruza com BP-007

### v0.3 — Universo 2: Dicionário SX

- **`/plugadvpl:ingest-sx <pasta-csv>`** — ingere dicionário SX exportado em CSV (sx1..sxg)
- **`/plugadvpl:impacto <campo>`** (killer feature) — cruza referências a um campo em fontes ↔ SX3 ↔ SX7 ↔ SX1 com `--depth 1..3`
- **`/plugadvpl:gatilho <campo>`** — cadeia de gatilhos SX7 origem → destino
- **`/plugadvpl:sx-status`** — counts por tabela do dicionário SX
- 11 regras cross-file novas `SX-001..SX-011` (consistência fontes ↔ dicionário)
- 2 skills novas: `advpl-dicionario-sx`, `advpl-dicionario-sx-validacoes`
- v0.3.3: skills `advpl-refactoring` (6 padrões before/after) e `advpl-debugging` (top 30 erros)

### v0.2 — Knowledge base ADVPL/TLPP

- 21k linhas de referência embarcadas em 5 skills novas (`advpl-mvc`, `advpl-mvc-avancado`, `advpl-tlpp`, `advpl-embedded-sql`, `advpl-pontos-entrada`) + 6 reforçadas
- Sem código novo do CLI — pura adição de conhecimento operacional pro Claude

### v0.1 — Universo 1: parser de fontes

- Parser regex strip-first sobre `.prw`/`.prx`/`.tlpp`/`.apw` com extração paralela em `ProcessPoolExecutor`
- SQLite + FTS5 unicode61 + FTS5 trigram (pra grep literal 10-50× mais rápido que regex)
- 14 subcomandos iniciais (`init`/`ingest`/`reindex`/`status`/`find`/`callers`/`callees`/`tables`/`param`/`arch`/`lint`/`doctor`/`grep`/`help`)
- 13 regras de lint single-file (best-practice, security, performance, modernization)
- 1 SessionStart hook Node.js cross-platform pra onboarding do `.plugadvpl/`

Specs detalhadas em `docs/universo*/`, `docs/fase*/`.

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
