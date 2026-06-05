# plugadvpl CLI — Referência completa

Esta página documenta cada subcomando da CLI `plugadvpl` (atualizada para v0.20.0). A CLI é construída com [Typer](https://typer.tiangolo.com/) e expõe **35 subcomandos** (mais os sub-apps `edit-prw` e `migrate-tlpp`) e um callback global com opções compartilhadas.

Use `plugadvpl --help` para ver a lista completa em runtime e `plugadvpl <subcomando> --help` para ver opções específicas.

## Sumário

- [Opções globais](#opcoes-globais)
- [Universo 1 — Fontes (v0.1)](#universo-1)
  - **write-path**: [`init`](#init), [`ingest`](#ingest), [`reindex`](#reindex)
  - **read-only**: [`status`](#status), [`find`](#find), [`family`](#family), [`callers`](#callers), [`callees`](#callees), [`tables`](#tables), [`catalog`](#catalog), [`param`](#param), [`arch`](#arch), [`lint`](#lint), [`check-build`](#check-build), [`doctor`](#doctor), [`grep`](#grep)
  - **utilitários**: [`version`](#version), [`help`](#help), [`edit-prw`](#edit-prw), [`compile`](#compile)
- [Universo 2 — Dicionário SX (v0.3)](#universo-2)
  - [`ingest-sx`](#ingest-sx), [`impacto`](#impacto), [`gatilho`](#gatilho), [`sx-status`](#sx-status), [`semantica`](#semantica)
- [Universo 3 — Rastreabilidade (v0.4)](#universo-3)
  - [`workflow`](#workflow), [`execauto`](#execauto), [`docs`](#docs)
- [Universo 4 — Rastreabilidade & qualidade (v0.4)](#universo-4)
  - [`trace`](#trace), [`metrics`](#metrics), [`hotspots`](#hotspots), [`cobertura-doc`](#cobertura-doc), [`doc-writer`](#doc-writer)
- [Universo 5 — Ingestão REST (v0.5)](#universo-5)
  - [`ingest-protheus`](#ingest-protheus)
- [Universo 6 — Migração ADVPL→TLPP (v0.6)](#universo-6)
  - [`migrate-tlpp`](#migrate-tlpp)
- [Universo 7 — Ops / Troca Quente (v0.7)](#universo-7)
  - [`tq`](#tq)
- [Auditoria — INI & Logs (v0.11+)](#auditoria)
  - [`ini-audit`](#ini-audit), [`log-diagnose`](#log-diagnose)
- [PO UI — Frontend Angular TOTVS (v0.22+)](#poui)
  - [`ingest-poui`](#ingest-poui)
  - [`poui-bridge`](#poui-bridge)
  - [`poui-componentes`](#poui-componentes)
  - [`poui-lint`](#poui-lint)
- [Exit codes](#exit-codes)

---

## <a id="opcoes-globais"></a>Opções globais

Todas as opções abaixo aparecem ANTES do nome do subcomando: `plugadvpl --root D:/projeto --format json arch FATA050.prw`.

| Opção | Alias | Default | Descrição |
|---|---|---|---|
| `--root <path>` | `-r` | `.` (cwd) | Raiz do projeto cliente. Caminhos relativos são resolvidos a partir daqui. |
| `--format <fmt>` | `-f` | `table` | Formato de saída: `table` (rich), `json` (estruturado, machine-readable), `md` (markdown para colar no Claude). |
| `--quiet` | `-q` | `false` | Suprime títulos decorativos. JSON fica "puro" (sem títulos). |
| `--db <path>` | — | `<root>/.plugadvpl/index.db` | Caminho explícito do DB. Útil para testes ou múltiplos índices. |
| `--limit <N>` | — | `20` | Máximo de linhas no output. `0` = sem limite. |
| `--offset <N>` | — | `0` | Pular N linhas antes do limit. Paginação manual. |
| `--compact` | — | `false` | Output compacto: JSON sem indentação, tabelas sem bordas. |
| `--no-next-steps` | — | `false` | Desliga as sugestões de próximo comando (úteis para humano, ruído para Claude). |

**Read-only**: todos os subcomandos exceto `init`, `ingest` e `reindex` abrem o DB em modo `mode=ro` (URI SQLite). Não há risco de hot-write durante queries.

---

## <a id="universo-1"></a>Universo 1 — Fontes (v0.1)

Comandos clássicos pra indexar/consultar fontes ADVPL/TLPP do projeto.

### Subcomandos write-path

### <a id="init"></a>`init`

Cria o índice vazio em `<root>/.plugadvpl/index.db`, escreve o fragment plugadvpl em `CLAUDE.md` (idempotente, com marcadores `BEGIN/END plugadvpl`) e adiciona `.plugadvpl/` ao `.gitignore` se já existir.

```
plugadvpl init
```

**Faz:**

1. Aplica migration 001 (cria 22 tabelas + 2 FTS5 + indices).
2. Popula `meta` (project_root, cli_version, schema_version).
3. Carrega os 6 JSONs de `lookups/` (279+194+24+5+8+15 = 525 rows).
4. Escreve fragment em `CLAUDE.md` (cria se não existe).
5. Adiciona `.plugadvpl/` a `.gitignore` se o arquivo existir.

**Idempotente** — pode rodar várias vezes sem corromper estado.

---

### <a id="ingest"></a>`ingest`

Indexa todos os fontes `.prw`/`.prx`/`.tlpp`/`.apw` em `--root`.

```
plugadvpl ingest [--workers N] [--incremental/--no-incremental]
                 [--no-content] [--redact-secrets]
```

**Opções:**

| Opção | Default | Descrição |
|---|---|---|
| `--workers <N>` / `-w` | `None` (adaptive) | Workers paralelos. `0`=single-thread; `None`=auto (<200 arquivos single, >=200 ProcessPool com `min(8, cpu_count())`). |
| `--incremental` / `--no-incremental` | `true` | Pula arquivos cujo `mtime` no DB é >= ao do filesystem. `--no-incremental` força reindex completo. |
| `--no-content` | `false` | Não persiste o corpo dos chunks — apenas metadata (funções, tabelas, calls). Reduz DB em ~80% e elimina risco de credenciais literais. |
| `--redact-secrets` | `false` | Mascara URLs com credenciais (`http://user:pwd@...`) e tokens hex longos (≥32 chars) antes de gravar `content`. |

**Pipeline interno**: scan → strip comentários/strings (preserve linhas) → parse (parser.py) → lint single-file (lint.py) → write em transação por arquivo → rebuild FTS5 ao final.

**Output (table)**:

```
                     Ingest summary
┌──────────────┬─────┬─────────┬────────┬────────┬───────────┬───────────────┬─────────────┐
│ arquivos_total│ ok  │ skipped │ failed │ chunks │ chamadas  │ lint_findings │ duration_ms │
├──────────────┼─────┼─────────┼────────┼────────┼───────────┼───────────────┼─────────────┤
│ 2000         │1997 │ 0       │ 3      │ 11243  │ 47892     │ 412           │ 38214       │
└──────────────┴─────┴─────────┴────────┴────────┴───────────┴───────────────┴─────────────┘
```

**Output (json --compact):**

```json
[{"arquivos_total":2000,"ok":1997,"skipped":0,"failed":3,"chunks":11243,"chamadas":47892,"lint_findings":412,"duration_ms":38214}]
```

---

### <a id="reindex"></a>`reindex <arq>`

Re-indexa UM arquivo após edição. Resolve `<arq>` por basename case-insensitive ou caminho relativo.

```
plugadvpl reindex FATA050.prw
plugadvpl reindex src/custom/MEUMOD.tlpp
```

Força `incremental=False` para esse arquivo, atualiza `parser_version` e dá rebuild nos dois índices FTS5.

---

## <a id="subcomandos-read-only"></a>Subcomandos read-only

### <a id="status"></a>`status`

Resumo do índice. Mostra contadores e metadata.

```
plugadvpl status [--check-stale]
```

**Output:**

```
              Status do índice
┌──────────────────┬──────────────────────────┐
│ chave            │ valor                    │
├──────────────────┼──────────────────────────┤
│ schema_version   │ 001                      │
│ cli_version      │ 0.1.0                    │
│ parser_version   │ p1.0.0                   │
│ fontes           │ 1987                     │
│ chunks           │ 11243                    │
│ chamadas         │ 47892                    │
│ lint_findings    │ 412                      │
│ project_root     │ /caminho/do/projeto      │
└──────────────────┴──────────────────────────┘
```

`--check-stale` adiciona uma segunda tabela com arquivos cujo mtime de filesystem é mais recente que o DB (precisa de `ingest --incremental`).

---

### <a id="find"></a>`find <termo>`

Busca composta: tenta resolver `<termo>` primeiro como nome de função (case-insensitive contra `fonte_chunks.funcao_norm`), depois como fragmento de arquivo (LIKE em `fontes.arquivo`), por último como conteúdo via FTS5.

```
plugadvpl find FATA050
plugadvpl find MaCntSA1
plugadvpl find "RECLOCK SA1"
plugadvpl find "MOD12*"          # glob: ancorado no início (MOD12...)
plugadvpl find "*FAT*"           # glob: substring
```

Retorna até `--limit` resultados, ordenados por categoria (função > arquivo > FTS).

**Glob (#62):** quando `<termo>` contém `*` ou `?`, o match de arquivo vira padrão (`*`→qualquer, `?`→um char) em vez de substring. Para a visão estruturada de uma família inteira, use [`family`](#family).

---

### <a id="family"></a>`family <prefixo>`

Descobre a **família** de fontes cujo basename começa com `<prefixo>` — numa tabela com `source_type`, LoC, `capabilities` e a **descrição do header doc** ([#63](#arch)). Evita `find` repetido ao mapear um processo customizado (convenção Protheus de prefixo: `MOD120`, `MOD121`...).

```
plugadvpl --format md family MOD12
plugadvpl family "FAT*"           # aceita glob
```

| Coluna | Descrição |
|---|---|
| `arquivo` | Basename do fonte |
| `source_type` | `mvc` / `user_function` / `pe` / `rpc` / ... |
| `lines_of_code` | Linhas |
| `capabilities` | MVC, DIALOG, PE, ... (lista) |
| `descricao` | Descrição do header doc (vazia se o fonte não tem header) |

**`--include-tables` (#72):** acrescenta `tables_read` (top-N por relevância — custom `Z*`/`SZ*` antes das comuns) e `tables_write` (todas, com tag `(mvc)`/`(execauto)` da detecção do #61). Panorama do processo inteiro numa tela — quem grava (mantenedor) vs quem só lê. Flags `--max-tables N` (default 3) e `--custom-only` (só `Z*`/`SZ*`).

```
plugadvpl --format md family MOD12 --include-tables
plugadvpl family MOD12 --include-tables --custom-only --max-tables 5
```

---

### <a id="callers"></a>`callers <funcao>`

Lista quem chama `<funcao>` consultando `chamadas_funcao.destino_norm` (uppercase, sem prefixo `U_`).

```
plugadvpl callers MaCntSA1
plugadvpl callers FATA050
```

**Output (json):**

```json
[
  {"arquivo_origem":"FATA060.prw","funcao_origem":"FATA060","linha_origem":234,"tipo":"U_"},
  {"arquivo_origem":"CTBA100.prw","funcao_origem":"GeraConta","linha_origem":89,"tipo":"static"}
]
```

---

### <a id="callees"></a>`callees <funcao>`

Lista quem `<funcao>` chama (espelho de `callers`).

```
plugadvpl callees FATA050
```

---

### <a id="tables"></a>`tables <T>`

Lista quem usa a tabela ADVPL `<T>` (ex: SA1, SC5, ZA1). Consulta `fonte_tabela` (tabela normalizada).

```
plugadvpl tables SA1
plugadvpl tables ZA1 --mode write
plugadvpl tables SC5 --mode reclock
```

**Opção:** `--mode {read|write|reclock|write_mvc|write_execauto}` filtra por tipo de uso. Sem filtro retorna todos.

**`write` é abrangente (#61):** inclui gravação clássica (`RecLock`/`Replace`) **+ MVC** (`write_mvc` — o fonte que define o `ModelDef`, tabela master via `FWFormStruct(1,'X')`) **+ ExecAuto** (`write_execauto` — tabelas resolvidas do `MsExecAuto`). Isso evita o falso "tabela só-leitura" quando o mantenedor é um cadastro MVC ou um ExecAuto (que a detecção clássica não vê). Use `--mode write_mvc` / `write_execauto` para filtrar só esses.

**`--catalog` (#64):** em vez do *uso*, mostra o **catálogo de campos** da tabela (do dicionário SX3) — tipo (`C(1)`, `N(14,2)`), título e o **X3_CBOX decodificado** (`1=Item, 2=Cabeçalho`), marcando os **discriminadores** (`C(1)`/`C(2)` com cbox). Responde "que valores `XX_TIPO` aceita?" sem ir ao banco. Requer dicionário indexado (`ingest-sx`).

**Alerta de mantenedor invisível (#65):** se `--mode write` vier vazio mas a tabela é lida em ≥ 3 fontes, um aviso em **stderr** sinaliza que pode haver mantenedor não detectado (stdout/JSON intactos). `--no-hints` silencia.

```
plugadvpl --format md tables SZT --catalog
```

---

### <a id="ingest-tsv"></a>`ingest-tsv <arquivo> --as <alias>`

Importa um **dump TSV/CSV** de uma tabela-catálogo (Z*/X*) pro índice — o `tables --catalog` (#64) dá o *schema*; este traz o **conteúdo** (as N regras catalogadas). Encoding (cp1252/utf-8/utf-8-bom) e delimiter (tab/csv) **auto-detectados**; override com `--encoding`/`--delimiter`. Se o nome do arquivo bate com uma tabela SX (`SZT.tsv`→`SZT`), cruza pra habilitar `--decode-cbox`. Re-ingest do mesmo alias sobrescreve.

```
plugadvpl ingest-tsv dumps/SZT.tsv --as catalogo_regras
```

### <a id="catalog"></a>`catalog <alias>`

Consulta o conteúdo de um catálogo importado. Determinístico, sem ir ao banco.

```
plugadvpl catalog catalogo_regras --limit 20
plugadvpl catalog catalogo_regras --filter "ZT_MSBLQL='2' AND ZT_FILIAL='01'"
plugadvpl --format md catalog catalogo_regras --group-by ZT_TIPO --count --decode-cbox
plugadvpl catalog catalogo_regras --funcao-field ZT_FUNCAO --resolve-callers
```

| Opção | Efeito |
|---|---|
| `--filter "COL OP 'VAL'"` | Filtro **seguro** (OP: `= != > < >= <= LIKE`, unidos por `AND`/`OR`) — aplicado em Python, à prova de SQL injection |
| `--group-by COL[,COL] --count` | Distribuição (contagem por grupo) |
| `--decode-cbox` | Decoda valores via X3_CBOX da tabela SX correlata (`1=Fiscal`) |
| `--funcao-field COL --resolve-callers` | Cruza o campo `*_FUNCAO` do dump com os fontes indexados (`U_MODxxx`→`MODxxx.prw`) |

`plugadvpl status` lista os catálogos importados (alias + nº de linhas).

---

### <a id="param"></a>`param <MV_*>`

Lista quem usa o parâmetro `<MV_*>` (GetMV/SuperGetMV/PutMV).

```
plugadvpl param MV_LOCALIZA
plugadvpl param MV_PAR01
```

---

### <a id="arch"></a>`arch <arquivo>`

**O comando mais importante.** Resumo arquitetural de UM fonte. Use ANTES de `Read` no Claude — economiza ~10× tokens.

```
plugadvpl arch FATA050.prw
plugadvpl arch FATA050 --format md
```

**Retorna em uma única "row" estruturada:**

- `arquivo`, `modulo`, `tipo`, `encoding`, `lines_of_code`
- `capabilities` (list: mvc, rest, job, pe, sx_dict, ...)
- `funcoes` + `user_funcs` + `pontos_entrada`
- `tabelas_ref` (read) + `write_tables` + `reclock_tables`
- `includes` (.ch usados)
- `calls_u` (chamadas a U_ funcs)
- Counters: número de chunks, chamadas, SQL embedados, lint findings

**Saída em md** é o formato preferido para enviar ao Claude — pronto para colar em contexto.

**`--include-header`** (#63): anexa `header_doc` — o bloco declarativo do topo do
fonte (`Programa/Autor/Data/Descrição/Doc.Origem/Solicitante/Uso/Obs`), quando
presente. Distinto do Protheus.doc; extraído por `parsing/header.py`.

```
plugadvpl --format json arch FATA050.prw --include-header
```

---

### <a id="lint"></a>`lint [arquivo]`

Lista findings (filtros opcionais).

```
plugadvpl lint                              # todos
plugadvpl lint FATA050.prw                  # apenas um arquivo
plugadvpl lint --severity critical          # filtra severidade
plugadvpl lint --regra BP-001               # filtra regra
plugadvpl lint --target-build 24.3.0.5      # + BUILD-001 (método ausente na build)
```

**Regras catalogadas (`lint_rules`)** com categorias: `BP-*` (best practice), `SEC-*` (security), `PERF-*` (performance), `MOD-*` (modernization), `SX-*`, `WS-*`, `ENC-*`, `SQL-*`. Com `--target-build`, inclui também findings `BUILD-001` (uso de método `FW*`/`Ms*` ausente na build alvo) via catálogo `apis_por_build` — vide `check-build`.

---

### <a id="check-build"></a>`check-build <fonte> --target-build <build>`

Sinaliza uso de método `FW*`/`MsDialog`/`FWBrowse` ausente na build Protheus alvo, antes de compilar. Resolve `oVar := Classe():New()` por função e só reporta quando a classe é confirmada no catálogo `apis_por_build` (zero falso-positivo). Não precisa de índice.

```
plugadvpl check-build PAINEL01.prw --target-build 24.3.0.5
```

---

### <a id="doctor"></a>`doctor`

Diagnósticos do índice. Cada check retorna `status ∈ {ok, warn, error}`.

```
plugadvpl doctor
```

Checks rodados:

- `encoding`: fontes sem encoding detectado
- `orphans`: chunks sem fonte (ou vice-versa)
- `fts_sync`: contagem FTS vs `fonte_chunks`
- `lookups`: as 6 lookup tables estão populadas?
- `migrations`: 001 aplicada?

Saída sugere próxima ação (`plugadvpl ingest --no-incremental`) se houver `error`/`warn`.

---

### <a id="grep"></a>`grep <pattern> [--mode]`

Busca textual sobre `fonte_chunks.content`.

```
plugadvpl grep "RECLOCK SA1"
plugadvpl grep "SA1->A1_COD" --mode literal
plugadvpl grep "MaCnt" --mode identifier
```

**Modos:**

| Modo | Engine | Para que serve |
|---|---|---|
| `fts` (default) | `fonte_chunks_fts` (unicode61 + tokenchars `_-`) | Busca por palavras/identifiers. `MaCnt*` casa com `MaCntSA1`. |
| `literal` | `fonte_chunks_fts_tri` (trigram) | Substring exata, inclusive pontuação ADVPL como `SA1->A1_COD`, `::New`, `%xfilial%`. |
| `identifier` | LIKE com `\b` em SQLite | Match por identifier exato (case-insensitive). |

---

## <a id="utilitarios"></a>Utilitários

### <a id="version"></a>`version`

Imprime a versão da CLI. Útil em scripts de validação e em `doctor`.

```
$ plugadvpl version
plugadvpl 0.4.3
```

### <a id="help"></a>`help`

Atalho equivalente a `plugadvpl --help`. Lista todos os subcomandos.

### <a id="edit-prw"></a>`edit-prw {check,open,save} <file>` (v0.7.0)

Conversão CP1252 ↔ UTF-8 in-place para fontes ADVPL/TLPP. Resolve
divergências reportadas por **ENC-001**.

```
plugadvpl edit-prw check <file>                  # reporta encoding vs extensão (exit 1 se mismatch)
plugadvpl edit-prw open  <file>                  # imprime conteúdo em UTF-8 puro (stdout)
plugadvpl edit-prw save  <file> [--from CP] [--to CP] [--no-backup]
```

Default por extensão: `.prw`/`.prx` → cp1252 · `.tlpp`/`.ch` → utf-8.
`save` cria backup `<file>.bak` por padrão. Estratégia de detecção:
BOM → ASCII → UTF-8 strict → CP1252 fallback (determinística).

Exit codes:
- `0` — sucesso (ou check passou)
- `1` — check mismatch ou erro de conversão (`--from` inválido)
- `2` — arquivo não encontrado

### <a id="compile"></a>`compile <fonte...>` (v0.8.0+)

Compila fontes ADVPL via wrapper sobre o binário `advpls` (TOTVS). Dois modos:
`appre` (pré-processador local, sem AppServer) ou `cli` (full compile via
AppServer TCP, requer `runtime.toml`).

```
plugadvpl compile [--mode auto|appre|cli]
                  [--changed-since <git-ref>]
                  [--no-warnings] [--timeout <seg>]
                  [--no-security-warning]
                  [--includes <path> [--includes <path>...]]
                  <fontes...>
plugadvpl compile --init-config [--force]
```

> ⚠️ **Ordem dos args importa**: flags `--xxx` **antes** dos `<fontes>` positional.
> Caso contrário, o typer/Click consome `--mode appre --includes X` como nomes de
> arquivo. Convenção UNIX: `[OPTIONS] ARGS...`.

**Pré-requisitos do modo `appre`**:
- Binário `advpls` (vem com extensão [tds-vscode](https://marketplace.visualstudio.com/items?itemName=TOTVS.tds-vscode), pasta `node_modules/@totvs/tds-ls/bin/<os>/advpls`)
- Includes Protheus reais (`PRTOPDEF.CH`, `protheus.ch`, `topconn.ch` etc.). Não vem com tds-vscode — precisa instalação SDK Protheus/AppServer. Tipicamente em `<protheus-root>/Include/` (~1100 arquivos `.ch`)
- Passar `--includes <pasta>` apontando pra esse diretório, OU configurar `[compile].includes` no `runtime.toml`

📘 **[Setup completo passo-a-passo em docs/setup-compile.md](setup-compile.md)** — cobre Windows + Linux + macOS + CI + troubleshooting dos erros comuns.

**Setup uma vez por projeto:**
```bash
plugadvpl compile --init-config     # gera .plugadvpl/runtime.toml comentado
# Edita o TOML preenchendo binary, host, port, environment, build, env vars
export PROTHEUS_USER=admin
export PROTHEUS_PASS='<senha>'
```

**Uso:**
```bash
plugadvpl compile foo.prw bar.prw           # full compile via AppServer
plugadvpl compile foo.prw --mode appre      # só pré-processador local
plugadvpl compile --changed-since HEAD~1    # tudo que mudou no commit
plugadvpl compile foo.prw --format json     # output estruturado p/ CI
```

**Exit codes:**
- `0` — sucesso (zero errors)
- `1` — compile encontrou error
- `2` — config/setup inválido (runtime.toml ausente em --mode cli, env var
  faltando, binary não encontrado, etc.)
- `130` — `KeyboardInterrupt` (POSIX 128+SIGINT)

**Schema JSON** (`--format json`):
```json
{"rows":[{"arquivo","ok","mode","duration_ms","exit_code",
 "counts":{"error","warning","info","unknown"},"diagnostics":[...]}]}
```

Cada `diagnostic` tem 7 campos: `severidade`, `arquivo`, `linha`, `coluna`,
`mensagem`, `codigo`, `raw`. Bucket `__unmatched__` para diagnostics com
arquivo fora dos requested.

**Security warning**: em `--mode cli` com host remoto, imprime warning no
stderr recomendando SSH tunnel local. Suprime com `--no-security-warning`.

Spec completa: [`docs/fase1/compile-design.md`](fase1/compile-design.md).

---

## <a id="universo-2"></a>Universo 2 — Dicionário SX (v0.3)

Comandos pra indexar e consultar o dicionário SX exportado do Configurador
(SIGACFG → Misc → Exportar Dicionário em CSV).

### <a id="ingest-sx"></a>`ingest-sx <pasta-csv>`

Ingere os arquivos `sx1.csv`, `sx2.csv`, …, `sxg.csv` (formato exportação TOTVS)
em 11 tabelas: `tabelas` (SX2), `campos` (SX3), `gatilhos` (SX7),
`parametros` (SX6), `perguntas` (SX1), `consultas` (SXB), `pastas` (SXA),
`relacionamentos` (SX9), `indices` (SIX), `tabelas_genericas` (SX5),
`grupos_campo` (SXG).

```
plugadvpl ingest-sx <pasta-csv> [--no-incremental]
```

Apenas customizações do cliente — campos/parâmetros padrão TOTVS são
ignorados por design.

### <a id="impacto"></a>`impacto <campo>` — killer feature

Cruza referências a um campo SX3 em fontes ↔ SX3 ↔ SX7 (gatilhos) ↔ SX1
(perguntas/parâmetros). Resposta inclui chain expandido até `--depth 3`.

```
plugadvpl impacto A1_COD [--depth 1..3] [--format json]
```

Use quando precisar avaliar impacto de mudança em campo (rename, mudança
de tipo, deprecation).

### <a id="gatilho"></a>`gatilho <campo>`

Cadeia de gatilhos SX7 origem → destino, com `--depth 1..3` pra atravessar
gatilhos transitivos (campo X dispara gatilho que mexe em Y, que dispara
gatilho que mexe em Z).

### <a id="sx-status"></a>`sx-status`

Counts por tabela do dicionário SX ingerido. Sanity check de cobertura.

---

### <a id="semantica"></a>`semantica <campo>`

Semântica contextual de um campo SX cujo significado muda conforme um discriminador (TIPO/PODER3/STATUS) — não óbvia pelo nome nem pelo `X3_DESCRIC`. Lê o catálogo `campos_semantica` (só semântica padrão Protheus). Não precisa de índice.

```
plugadvpl semantica D2_NFORI   # mesma coluna, semântica oposta por D2_TIPO
```

---

## <a id="universo-3"></a>Universo 3 — Rastreabilidade (v0.4)

Comandos pra indexar mecanismos de execução não-direta (workflow/schedule/
job/mail), chamadas indiretas via `MsExecAuto`, e documentação inline
Protheus.doc.

### <a id="workflow"></a>`workflow` (v0.4.0)

Lista os 4 mecanismos canônicos TOTVS de execução não-direta indexados:

```
plugadvpl workflow [--kind <kind>] [--target <nome>] [--arquivo <basename>]
```

| `--kind` | Detecção |
|---|---|
| `workflow` | `TWFProcess():New(...)`, `MsWorkflow(`, `WFPrepEnv(`, `:bReturn :=` |
| `schedule` | `Static Function SchedDef()` retornando `{cTipo,cPergunte,cAlias,aOrdem,cTitulo}` |
| `job_standalone` | `Main Function` + `RpcSetEnv` + `Sleep` loop (daemon ONSTART) |
| `mail_send` | `MailAuto(`, `SEND MAIL` UDC, `TMailManager`/`TMailMessage` |

Metadados específicos por `kind` (process_id, sched_type/pergunte/alias,
main_name/empresa/filial/modulo/sleep_seconds, variant/has_attachment/
uses_mv_rel) ficam em `metadata` no `--format json`.

### <a id="execauto"></a>`execauto` (v0.4.1)

Resolve a indireção do `MsExecAuto({|x,y,z| MATA410(x,y,z)}, ...)` cruzando
com catálogo TOTVS (31 rotinas em `lookups/execauto_routines.json`) pra
inferir tabelas tocadas indiretamente, módulo, e operação (3/4/5 →
inclusão/alteração/exclusão).

```
plugadvpl execauto [--routine <nome>] [--modulo <SIGAFAT>]
                   [--arquivo <basename>] [--op inc|alt|exc]
                   [--dynamic|--no-dynamic]
```

Enrichment do `arch`: campo `tabelas_via_execauto_resolvidas: list[str]`
agrega tabelas inferidas (campo bool antigo `tabelas_via_execauto` continua,
não-breaking).

Calls não-resolvíveis (`&(cVar)`, codeblock vazio, variável armazenada)
ficam com `routine=null, dynamic_call=true` — use `--dynamic` pra revisão.

### <a id="docs"></a>`docs [modulo]` (v0.4.2)

Catálogo de Protheus.doc agregado por módulo/autor/tipo/deprecação.

```
plugadvpl docs [<modulo>] [--author <nome>] [--funcao <nome>]
               [--arquivo <basename>] [--deprecated|--no-deprecated]
               [--tipo <type>] [--show <funcao>] [--orphans]
```

Modos:

- **Lista**: `docs SIGAFAT` ou `docs --author "Fernando" --deprecated`
- **Show formatado**: `docs --show MT460FIM` → Markdown estruturado completo
  (cabeçalho + tabela params + sections retorno/exemplos/histórico).
  Aceita `--arquivo` pra desambiguar homônimos (v0.4.3).
- **Orphans**: `docs --orphans` → cross-ref BP-007 do lint (funções sem header)

16 tags canônicas TOTVS extraídas estruturadamente: `@type`, `@author`,
`@since`, `@version`, `@description`, `@language`, `@deprecated`, `@param`,
`@return`, `@example`, `@history`, `@see`, `@table`, `@todo`, `@obs`,
`@link`. Tags fora do whitelist vão pro `raw_tags` catch-all (zero perda).

Inferência de módulo dual: path-based (`SIGA\w{3,4}` no path) +
routine-prefix (reaproveita catálogo do `execauto`).

---

## <a id="universo-4"></a>Universo 4 — Rastreabilidade & qualidade (v0.4)

### <a id="trace"></a>`trace <entidade>`

Trace agregado cross-universo de uma entidade (função, arquivo ou campo): junta `arch` + `docs` + `execauto` + gatilhos numa visão única.

```
plugadvpl trace FATA050.prw
plugadvpl trace A1_COD
```

---

### <a id="metrics"></a>`metrics [arquivo]`

Métricas por função. Sem `arquivo`, agrega o projeto.

```
plugadvpl metrics FATA050.prw
```

---

### <a id="hotspots"></a>`hotspots`

Top-N funções mais chamadas no projeto (candidatas a cuidado/teste/refactor). `--limit` é a opção global.

```
plugadvpl --limit 20 hotspots
```

---

### <a id="cobertura-doc"></a>`cobertura-doc`

Cobertura de `Protheus.doc` agregada — quanto do código tem header documentado.

```
plugadvpl cobertura-doc
```

---

### <a id="doc-writer"></a>`doc-writer <funcao>`

Gera o bloco `/*/{Protheus.doc} ... /*/` (com `@type`/`@param`/`@return`) para uma função ADVPL/TLPP indexada — pra colar no fonte.

```
plugadvpl doc-writer MaCntSA1
```

---

## <a id="universo-5"></a>Universo 5 — Ingestão via REST (v0.5)

### <a id="ingest-protheus"></a>`ingest-protheus`

Indexa o Dicionário SX ao vivo via REST API do COLETADB (em vez de CSVs exportados) — útil quando não se tem os SXs em arquivo.

```
plugadvpl ingest-protheus
```

---

## <a id="universo-6"></a>Universo 6 — Migração ADVPL→TLPP (v0.6)

### <a id="migrate-tlpp"></a>`migrate-tlpp <subcomando>`

Pipeline ts-migrate-style pra migrar `.prw` → `.tlpp`. Sub-app com `init`/`rename`/`recipes`/`todos` e 11 recipes (6 SAFE default + 5 IDIOMS via `--idioms`), cada uma isolada e testável.

```
plugadvpl migrate-tlpp init
plugadvpl migrate-tlpp recipes MEUMOD.prw
plugadvpl migrate-tlpp todos
```

---

## <a id="universo-7"></a>Universo 7 — Ops / Troca Quente (v0.7)

### <a id="tq"></a>`tq`

Restart do AppServer + healthcheck (Troca Quente MVP local) — recarrega o ambiente após deploy de RPO.

```
plugadvpl tq
```

---

## <a id="auditoria"></a>Auditoria — INI & Logs (v0.11+)

### <a id="ini-audit"></a>`ini-audit [paths...]`

Audita arquivos INI Protheus (`appserver.ini`, `dbaccess.ini`, `tss.ini`, broker) contra 487 regras TDN-oficiais, com score 0–100 + selo de conformidade (`compliant`/`partial`/`non_compliant`). Com `--format html` gera um relatório self-contained.

```
plugadvpl ini-audit appserver.ini
plugadvpl --format html ini-audit AppServer_TSS.ini > relatorio.html
```

---

### <a id="log-diagnose"></a>`log-diagnose [paths...]`

Diagnostica logs Protheus (`console.log`/`error.log`/`profile.log`/`compila.log`): classifica findings por severidade + categoria e correlaciona com correction tips da KB TDN. Com `--format html` gera relatório.

```
plugadvpl log-diagnose console.log
```

---

## <a id="poui"></a>PO UI — Frontend Angular TOTVS (v0.22+)

Detecta projetos PO UI: família `@po-ui/*`, versão, Angular exigido e flag de incompatibilidade. Extrai chamadas HttpClient dos `.ts` e cruza com rotas TLPP.

### <a id="ingest-poui"></a>`ingest-poui <dir>`

Descobre todos os `package.json` abaixo de `<dir>` (ignora `node_modules`, `dist`, `.angular`), extrai dependências `@po-ui/*` e Angular, persiste na tabela `poui_projetos`, e exibe resumo tabelar. A partir da Fase 2, também varre os `.ts` do projeto extraindo chamadas `HttpClient` para a tabela `poui_datasources`.

```
plugadvpl ingest-poui <dir>
```

**Argumento:**

| Nome | Obrigatório | Descrição |
|---|---|---|
| `<dir>` | sim | Diretório raiz do projeto PO UI (ou monorepo) |

**Saída:**

| Coluna | Descrição |
|---|---|
| `arquivo` | Path absoluto do `package.json` |
| `poui` | Versão `@po-ui/ng-components` (ou primeiro pacote) |
| `angular` | Major do Angular exigido |
| `compativel` | `sim` / `NAO` — `NAO` quando `poui_major != angular_major` |
| `pacotes` | Lista de pacotes `@po-ui/*` encontrados |

**Exemplos:**

```bash
plugadvpl ingest-poui ./frontend
plugadvpl --format json ingest-poui /path/to/monorepo
```

**Notas:**

- Bootstrapa o DB sozinho (não exige `init` prévio).
- Cache por hash+mtime — re-rodar em projeto sem mudanças zera ingestão (skipped=N).
- Compatibilidade: `poui_major == angular_major` (alinhamento TOTVS de versão >= 12).
- Fase 2 (v0.22+): extrai chamadas `this.http.get/post/...` dos `.ts` → `poui_datasources`.

---

### <a id="poui-bridge"></a>`poui-bridge`

Cruza os datasources REST do frontend Angular (tabela `poui_datasources`) com as rotas
REST do Protheus (tabela `rest_endpoints`, populada pelo `ingest`). Exibe os matches
front↔back por verbo+path.

```
plugadvpl poui-bridge
```

**Pré-requisito:** executar `ingest-poui <dir>` (extrai datasources) e `ingest` (indexa TLPP).

**Saída:**

| Coluna | Descrição |
|---|---|
| `verbo` | Verbo HTTP do match (GET, POST, …) |
| `path` | Path REST casado (ex: `/pedidos`) |
| `front` | Arquivo TypeScript + linha da chamada Angular |
| `back` | Fonte TLPP + função que implementa a rota |

**Exemplos:**

```bash
plugadvpl poui-bridge
plugadvpl --format json poui-bridge
```

### <a id="poui-componentes"></a>`poui-componentes [componente]`

Consulta o catálogo de bindings `p-*` (inputs e outputs) de componentes PO UI.
O catálogo embarcado (`poui_componentes.json`) contém 948 entradas extraídas do
código-fonte do `po-angular` — não inventa atributos. Não precisa de índice de
projeto (bootstraps o DB local automaticamente).

**Argumento:**

| Argumento | Tipo | Descrição |
|---|---|---|
| `componente` | TEXT (opcional) | Nome do componente Angular (ex: `po-table`). Omita para listar todos. |

**Colunas de saída:**

| Coluna | Descrição |
|---|---|
| `componente` | Nome do componente (ex: `po-table`) |
| `kind` | `input` (atributo de entrada) ou `output` (evento emitido) |
| `binding` | Atributo HTML `p-*` (ex: `p-columns`) |
| `propriedade` | Nome TypeScript da propriedade (ex: `columns`) |

**Exemplos:**

```bash
plugadvpl poui-componentes po-table
plugadvpl --format md poui-componentes po-input
plugadvpl --limit 0 poui-componentes  # todos os 948 bindings
```

### <a id="poui-lint"></a>`poui-lint`

Lint de templates PO UI: detecta bindings `p-*` usados em `<po-*>` que **não
existem no catálogo** `poui_componentes` (regra `POUI-PROP` — anti-alucinação).

**Pré-requisito:** `plugadvpl ingest-poui <dir>` para popular `poui_componentes_uso`.

**Saída:**

| Coluna | Descrição |
|---|---|
| `arquivo` | Template HTML com o binding suspeito |
| `linha` | Linha do componente no arquivo |
| `componente` | Componente Angular (`po-button`, `po-table`, …) |
| `binding` | Binding `p-*` não encontrado no catálogo |

**Exemplos:**

```bash
plugadvpl poui-lint
plugadvpl --format md poui-lint
plugadvpl --format json poui-lint
```

---

## <a id="exit-codes"></a>Exit codes

| Code | Significado |
|---|---|
| `0` | OK |
| `1` | Resultado vazio mas semanticamente esperado (ex: `arch` em arquivo não indexado) |
| `2` | Erro de pré-requisito (DB não existe, arquivo não encontrado, root inválido) |
| `>2` | Typer-level (opções inválidas, abort) |

Em scripts shell, `0` significa "comando rodou" — ausência de resultados ainda é `0` na maioria dos casos (callers/callees/lint/etc retornam linha vazia, não erro).
