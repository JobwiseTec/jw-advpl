# Plugadvpl — Design Spec

| Item | Valor |
|---|---|
| **Data** | 2026-05-11 |
| **Revisão crítica** | aplicada em 2026-05-11 (P0/P1/P2 do `2026-05-11-plugadvpl-design-pontos-atencao.md`) |
| **Status** | Aprovado para implementação |
| **Tipo** | Plugin Claude Code + CLI Python |
| **Licença** | MIT |
| **Repositório-alvo** | github.com/<owner>/plugadvpl |
| **Inspirações** | `advpl-specialist-main` (Thalys Augusto) + `Protheus` (SaaS interna do autor) |

## 1. Propósito

Criar um **plugin Claude Code open-source para a comunidade ADVPL/TLPP** que permite ao Claude analisar customizações Protheus (TOTVS) **sem desperdiçar tokens lendo fontes inteiros**. O plugin combina:

1. Um **plugin Claude Code** com commands, skills, agents e hook (markdown).
2. Uma **CLI Python** (`plugadvpl`, distribuída via PyPI/uvx) que faz ingestão dos fontes do cliente para um banco SQLite local (`./.plugadvpl/index.db`) com FTS5.

O fluxo de uso típico: dev clona/baixa fontes do cliente → instala o plugin no Claude Code → roda `/plugadvpl:ingest` → o Claude passa a consultar o índice antes de chamar `Read` em qualquer `.prw`/`.tlpp`.

**Métrica de sucesso:** em projetos típicos (~2.000 fontes), Claude responde perguntas como "explique a função FATA050" gastando **≤1.300 tokens** (vs. ~16.000 sem o plugin), redução média de **10–15×**. *(O critério de aceitação na Seção 14 usa um teto mais generoso de ≤2.000 tokens para acomodar variação entre cenários — métrica de sucesso reflete a média esperada; aceitação reflete o pior caso aceitável.)*

## 2. Decisões fundamentais

| Decisão | Escolha | Justificativa |
|---|---|---|
| Runtime do indexador | **Python 3.11+** | Reaproveita 100% do parser interno anterior do autor (~750 linhas), já validado em aproximadamente 2.000 fontes ADVPL |
| Tipo de busca | **SQLite + FTS5 (lexical)** | Zero dependência de embeddings/API key. Offline. ~90% dos casos de análise resolvidos por metadados estruturados; "semântica" vem do parser inteligente, não de embeddings |
| Workflow de ingestão | **Slash commands manuais** | Sem hooks auto-indexando a cada edit. Previsível, sem surpresas, dev tem controle |
| Distribuição da CLI | **uvx (uv) — zero install** | Comandos chamam `uvx plugadvpl ...`. uv resolve e cacheia automaticamente. Funciona igual em Win/Mac/Linux, isolado, sem poluir Python global |
| Organização do repo | **Mono-repo, dois "produtos"** | Plugin Claude Code (markdown) + CLI Python convivem no mesmo repo. Uma única release coerente cobre comandos + skill + parser. Comunidade contribui num só lugar |
| Escopo do MVP | **Universo 1 (Fontes) apenas; tabelas de 2/3/auxiliares só em v0.2+** | Cria **22 tabelas físicas no MVP** (8 do Universo Fontes + 5 extrações nível 2 + 1 lint + 6 lookups + 2 internas). As 17 tabelas de Universo 2/3/auxiliares são criadas via **migration** em v0.2+ quando a feature entrar — evita congelar contrato de colunas que talvez precisem mudar. Comandos que dependem dessas features retornam mensagem clara apontando para v0.2 |
| Slash commands & skills | **`skills/` (não `commands/`)** | Documentação oficial Claude Code: "Custom commands have been merged into skills. Use `skills/` for new plugins." Cada `skills/<nome>/SKILL.md` em plugin gera `/plugadvpl:<nome>` automaticamente. Mantém `commands/` apenas se necessário para wrappers especialmente finos |
| Pin de versão CLI | **`uvx plugadvpl@<v>` nos wrappers** | Sem pin, plugin v0.1 pode chamar CLI v0.2 com schema/flags incompatíveis. Wrapper inclui versão exata; upgrade é coordenado. Sintaxe `pkg@v` é mais curta que `--from pkg==v` quando nome do pacote == nome do executável. **Devs que rodam muito devem usar `uv tool install plugadvpl@<v>`** (PATH global, sem cold start de `uvx`) — documentado no README |
| Política de encoding | **`preserve-by-default`** | Spec não impõe cp1252 como dogma. Detecta encoding por arquivo, preserva em edição. Bloqueia escrita se detection ambígua. Cliente decide via `--encoding-policy {cp1252\|preserve\|utf8-warn}`. Default conservador para projetos legado (preserve com hint de cp1252) |
| Licença | **MIT** | Mesma do `advpl-specialist`. Padrão de fato do ecossistema Protheus open-source. Permite uso comercial sem fricção (consultorias) |
| Atribuição | Créditos explícitos no `NOTICE` | Parser portado de projeto interno anterior do autor + lookup tables (funções nativas, restritas, lint rules, SQL macros, módulos ERP, PEs catalogados) extraídas do `advpl-specialist` com crédito ao Thalys Augusto |

## 3. Arquitetura geral

```
┌─ Máquina do dev ─────────────────────────────────────────┐
│                                                           │
│   ┌─ Projeto Protheus do cliente ─────────────────────┐  │
│   │   src/                                             │  │
│   │     FATA050.prw                                    │  │
│   │     MATA461.prw  (etc — todos .prw/.tlpp/.prx)     │  │
│   │   .plugadvpl/                ← criado pelo ingest │  │
│   │     index.db                 ← SQLite + FTS5      │  │
│   │     manifest.json            ← versão, mtime      │  │
│   │   CLAUDE.md                  ← inclui fragmento   │  │
│   └────────────────────────────────────────────────────┘  │
│                  ▲                          ▲              │
│                  │ lê/escreve               │ lê (queries) │
│                  │                          │              │
│   ┌──────────────┴──────────┐   ┌──────────┴───────────┐  │
│   │ uvx plugadvpl ingest    │   │ Claude Code           │  │
│   │ uvx plugadvpl find ...  │   │  + plugin plugadvpl   │  │
│   │ (CLI Python via uvx)    │   │  → slash commands     │  │
│   └─────────────────────────┘   │  → skills, agents     │  │
│                                  │  → CLAUDE.md fragment │  │
│                                  └───────────────────────┘  │
└────────────────────────────────────────────────────────────┘
```

**Princípios:**

1. Plugin Claude Code **não tem código de parsing** — só markdown que orquestra chamadas `Bash("uvx plugadvpl ...")`.
2. CLI Python é **stand-alone** — funciona sem Claude Code. Pode ser usada em CI, scripts, terminal direto.
3. Índice fica **no projeto do cliente** (`./.plugadvpl/index.db`), não no plugin. Cada projeto tem seu próprio índice. Adicionado ao `.gitignore` por padrão (mas opcionalmente versionável).
4. Hook `session-start` detecta projeto ADVPL e **sugere** comandos — nunca indexa sozinho.
5. CLAUDE.md fragment é **idempotente** (regrava só região delimitada).

### 3.1 Layout do mono-repo

```
plugadvpl/
├── .claude-plugin/
│   ├── plugin.json                  # name: "plugadvpl" → namespacing automático
│   └── marketplace.json
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   ├── pull_request_template.md
│   └── workflows/
│       ├── ci.yml
│       ├── release.yml
│       └── lint-plugin.yml
├── skills/                          # 23 skills (slash commands + conhecimento)
│   ├── # ── Skills de comando (geram /plugadvpl:<nome>, executam CLI) ──
│   ├── init/SKILL.md
│   ├── ingest/SKILL.md
│   ├── reindex/SKILL.md
│   ├── status/SKILL.md
│   ├── find/SKILL.md
│   ├── callers/SKILL.md
│   ├── callees/SKILL.md
│   ├── tables/SKILL.md
│   ├── param/SKILL.md
│   ├── arch/SKILL.md
│   ├── lint/SKILL.md
│   ├── doctor/SKILL.md
│   ├── help/SKILL.md
│   ├── # ── Skills de conhecimento (consulta inline + slash opcional) ──
│   ├── plugadvpl-index-usage/SKILL.md  # skill-chefe (Claude carrega sempre)
│   ├── advpl-encoding/SKILL.md
│   ├── advpl-fundamentals/SKILL.md
│   ├── advpl-mvc/SKILL.md
│   ├── advpl-embedded-sql/SKILL.md
│   ├── advpl-matxfis/SKILL.md
│   ├── advpl-pontos-entrada/SKILL.md
│   ├── advpl-webservice/SKILL.md
│   ├── advpl-jobs-rpc/SKILL.md
│   └── advpl-code-review/SKILL.md
├── agents/                          # 4 subagents (workflows multi-step)
├── hooks/
│   ├── hooks.json                   # SessionStart hook config
│   └── session-start                # bash/ps1 script
├── cli/                             # código Python (PyPI: plugadvpl)
│   ├── pyproject.toml
│   ├── plugadvpl/
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── cli.py
│   │   ├── parser.py
│   │   ├── parser_lint.py
│   │   ├── db.py
│   │   ├── ingest.py
│   │   ├── query.py
│   │   ├── output.py
│   │   ├── migrations/
│   │   │   └── 001_initial.sql
│   │   └── lookups/
│   │       ├── funcoes_nativas.json
│   │       ├── funcoes_restritas.json
│   │       ├── lint_rules.json
│   │       ├── sql_macros.json
│   │       ├── modulos_erp.json
│   │       └── pontos_entrada_padrao.json
│   └── tests/
│       ├── conftest.py
│       ├── fixtures/
│       │   ├── synthetic/           # ~20 .prw curados, versionados
│       │   └── expected/            # snapshots JSON do parsing
│       ├── unit/
│       ├── integration/
│       ├── bench/
│       └── e2e_local/
├── docs/
│   ├── schema.md
│   ├── cli-reference.md
│   └── superpowers/specs/
├── scripts/
│   ├── validate_plugin.py
│   ├── bump_marketplace_version.py
│   └── regenerate_expected.py
├── CHANGELOG.md
├── CODE_OF_CONDUCT.md               # Contributor Covenant 2.1
├── CONTRIBUTING.md
├── LICENSE                          # MIT
├── NOTICE                           # créditos parser/lookups
├── SECURITY.md
└── README.md
```

## 4. Schema do índice (SQLite)

Localização: `<projeto-cliente>/.plugadvpl/index.db`.

**Princípio:** basear o schema em projeto interno anterior do autor (validado em aproximadamente 2.000 fontes ADVPL), e adicionar deltas mínimos para uso como plugin local. **MVP cria apenas as 22 tabelas necessárias.** As 17 tabelas de Universo 2/3/auxiliares são criadas via migrations em v0.2+ quando a feature entrar (evita congelar contrato).

### 4.1 PRAGMAs

**Aplicados pelo `init` (uma vez, na criação do DB vazio):**

```sql
PRAGMA page_size = 8192;            -- SÓ tem efeito em DB vazio; deve vir antes de qualquer CREATE TABLE
PRAGMA journal_mode = WAL;          -- persistido no DB header
PRAGMA journal_size_limit = 67108864;  -- 64 MB — previne WAL crescer sem limite
```

**Detecção de network share (CRÍTICO):** WAL **não funciona em SMB/CIFS/UNC**. Ver
[sqlite.org/wal.html](https://sqlite.org/wal.html): *"WAL does not work over a network
filesystem"*. Em consultorias Protheus é comum repo cliente em share corporativo. `init`
detecta via análise do path (UNC `\\server\share`, mapped drive em Win) e:
- Se share detectado: usa `PRAGMA journal_mode = DELETE` (modo rollback, mais lento mas safe)
- Avisa o usuário com motivo: *"Detectado network share; usando DELETE journal. Para
  performance ótima, mova o projeto para disco local."*

**Aplicados pelo `ingest` (em toda sessão, antes do Pass 1):**

```sql
PRAGMA synchronous = NORMAL;        -- mantém durante toda operação (FULL é exagero com WAL)
PRAGMA foreign_keys = ON;
PRAGMA temp_store = MEMORY;
PRAGMA mmap_size = 268435456;       -- 256 MB
PRAGMA cache_size = -20000;         -- ~20 MB
PRAGMA busy_timeout = 5000;         -- 5s para retry em caso de SQLITE_BUSY
-- locking_mode REMOVIDO: WAL já garante 1 writer + N readers nativo.
-- EXCLUSIVE mata o benefício (Claude perde leitura concorrente durante ingest).
```

**Ao final do `ingest` (não restaura synchronous=FULL — NORMAL é seguro):**

```sql
PRAGMA wal_checkpoint(TRUNCATE);    -- força WAL → DB principal, trunca .db-wal
PRAGMA optimize;                    -- recomendação oficial >=3.46 antes de close()
-- synchronous permanece NORMAL (durabilidade só perde em power loss físico,
--   ver sqlite.org/wal.html: "transactions committed with synchronous=NORMAL
--   are durable across application crashes")
```

### 4.2 Tabelas populadas no MVP (22)

**Universo 1 — Fontes (8 tabelas portadas do Protheus):**

```sql
CREATE TABLE IF NOT EXISTS fontes (
    arquivo            TEXT PRIMARY KEY,           -- basename (paridade Protheus)
    caminho            TEXT,                       -- caminho original do FS
    caminho_relativo   TEXT NOT NULL,              -- normalizado: lowercase, forward slashes, relativo ao project_root
    tipo               TEXT,                       -- 'custom'|'padrao'
    modulo             TEXT,
    funcoes            TEXT,                       -- JSON list
    user_funcs         TEXT,                       -- JSON list
    pontos_entrada     TEXT,                       -- JSON list
    tabelas_ref        TEXT,                       -- JSON list (read)
    write_tables       TEXT,                       -- JSON list
    includes           TEXT,                       -- JSON list
    calls_u            TEXT DEFAULT '',            -- JSON list
    calls_execblock    TEXT DEFAULT '',            -- JSON list
    fields_ref         TEXT DEFAULT '',            -- JSON list
    lines_of_code      INTEGER DEFAULT 0,
    hash               TEXT,
    source_type        TEXT DEFAULT '',
    capabilities       TEXT DEFAULT '[]',          -- JSON
    ws_structures      TEXT DEFAULT '{}',
    encoding           TEXT DEFAULT '',
    reclock_tables     TEXT DEFAULT '[]',
    -- deltas do plugin
    mtime_ns           INTEGER NOT NULL DEFAULT 0,
    size_bytes         INTEGER NOT NULL DEFAULT 0,
    indexed_at         TEXT DEFAULT (datetime('now')),
    namespace          TEXT DEFAULT '',            -- TLPP
    tipo_arquivo       TEXT DEFAULT '',            -- 'prw'|'tlpp'|'prx'|'apw'
    parser_version     TEXT DEFAULT '',            -- versão do parser usada na ingestão deste fonte
    UNIQUE (caminho_relativo)                      -- previne colisão se houver subpastas com nomes duplicados
);
CREATE INDEX idx_fontes_modulo       ON fontes(modulo);
CREATE INDEX idx_fontes_source_type  ON fontes(source_type);
CREATE INDEX idx_fontes_caminho_rel  ON fontes(caminho_relativo);

CREATE TABLE IF NOT EXISTS fonte_chunks (
    id              TEXT PRIMARY KEY,           -- '<arquivo>::<funcao>'
    arquivo         TEXT REFERENCES fontes(arquivo) ON DELETE CASCADE,
    funcao          TEXT,
    funcao_norm     TEXT,                       -- uppercase + trim (case-insensitive lookup)
    tipo_simbolo    TEXT DEFAULT 'function',    -- function|static_function|user_function|main_function|method|ws_method|mvc_hook|class|header
    classe          TEXT DEFAULT '',            -- preenchido se METHOD ... CLASS X
    linha_inicio    INTEGER NOT NULL DEFAULT 0,
    linha_fim       INTEGER NOT NULL DEFAULT 0,
    assinatura      TEXT DEFAULT '',            -- linha do header (mesma info de funcao_docs.assinatura, mas aqui pra evitar join)
    content         TEXT,
    modulo          TEXT
);
CREATE INDEX idx_chunks_arquivo     ON fonte_chunks(arquivo);
CREATE INDEX idx_chunks_funcao      ON fonte_chunks(funcao COLLATE NOCASE);
CREATE INDEX idx_chunks_funcao_norm ON fonte_chunks(funcao_norm);
CREATE INDEX idx_chunks_tipo        ON fonte_chunks(tipo_simbolo);

CREATE TABLE IF NOT EXISTS chamadas_funcao (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo_origem  TEXT NOT NULL,
    funcao_origem   TEXT NOT NULL,
    linha_origem    INTEGER DEFAULT 0,
    tipo            TEXT NOT NULL,
    destino         TEXT NOT NULL,
    destino_norm    TEXT NOT NULL,              -- uppercase + sem prefixo U_ (lookup case-insensitive)
    arquivo_destino TEXT DEFAULT NULL,
    funcao_destino  TEXT DEFAULT NULL,
    contexto        TEXT DEFAULT ''
);
CREATE INDEX idx_cf_origem       ON chamadas_funcao(arquivo_origem, funcao_origem COLLATE NOCASE);
CREATE INDEX idx_cf_destino      ON chamadas_funcao(destino COLLATE NOCASE);
CREATE INDEX idx_cf_destino_norm ON chamadas_funcao(destino_norm);

CREATE TABLE IF NOT EXISTS parametros_uso (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo         TEXT NOT NULL,
    parametro       TEXT NOT NULL,
    modo            TEXT DEFAULT 'read',        -- read|write|read_write
    default_decl    TEXT DEFAULT ''
);
CREATE INDEX idx_pu_param   ON parametros_uso(parametro);
CREATE INDEX idx_pu_arquivo ON parametros_uso(arquivo);

CREATE TABLE IF NOT EXISTS perguntas_uso (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo         TEXT NOT NULL,
    grupo           TEXT NOT NULL
);
CREATE INDEX idx_pgu_grupo   ON perguntas_uso(grupo);
CREATE INDEX idx_pgu_arquivo ON perguntas_uso(arquivo);

CREATE TABLE IF NOT EXISTS operacoes_escrita (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo         TEXT NOT NULL,
    funcao          TEXT NOT NULL,
    tipo            TEXT NOT NULL,
    tabela          TEXT NOT NULL,
    campos          TEXT DEFAULT '[]',
    origens         TEXT DEFAULT '{}',
    condicao        TEXT DEFAULT '',
    linha           INTEGER DEFAULT 0
);
CREATE INDEX idx_oe_tabela  ON operacoes_escrita(tabela);
CREATE INDEX idx_oe_arquivo ON operacoes_escrita(arquivo);

CREATE TABLE IF NOT EXISTS sql_embedado (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo         TEXT NOT NULL,
    funcao          TEXT DEFAULT '',
    linha           INTEGER DEFAULT 0,
    operacao        TEXT DEFAULT 'select',
    tabelas         TEXT DEFAULT '[]',
    snippet         TEXT DEFAULT ''
);
CREATE INDEX idx_sqle_arquivo ON sql_embedado(arquivo);

CREATE TABLE IF NOT EXISTS funcao_docs (
    arquivo     TEXT,
    funcao      TEXT,
    tipo        TEXT,
    assinatura  TEXT,
    resumo      TEXT,
    tabelas_ref TEXT,
    campos_ref  TEXT,
    chama       TEXT,
    chamada_por TEXT,
    retorno     TEXT,
    params      TEXT,
    fonte       TEXT DEFAULT 'auto',
    updated_at  TEXT DEFAULT (datetime('now')),
    resumo_auto TEXT DEFAULT '',
    PRIMARY KEY (arquivo, funcao)
);
```

**Nível 2 — Extrações novas (5 tabelas):**

```sql
CREATE TABLE IF NOT EXISTS rest_endpoints (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo         TEXT NOT NULL,
    classe          TEXT DEFAULT '',            -- WSSERVICE name
    funcao          TEXT NOT NULL,
    verbo           TEXT NOT NULL,              -- GET|POST|PUT|DELETE
    path            TEXT DEFAULT '',
    annotation_style TEXT NOT NULL              -- 'wsmethod_classico'|'@verb_tlpp'
);
CREATE INDEX idx_rest_verb ON rest_endpoints(verbo);
CREATE INDEX idx_rest_path ON rest_endpoints(path);

CREATE TABLE IF NOT EXISTS http_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo         TEXT NOT NULL,
    funcao          TEXT DEFAULT '',
    linha           INTEGER DEFAULT 0,
    metodo          TEXT NOT NULL,              -- HttpGet|HttpPost|HttpsPost|MsAGetUrl
    url_literal     TEXT DEFAULT ''
);
CREATE INDEX idx_http_arquivo ON http_calls(arquivo);

CREATE TABLE IF NOT EXISTS env_openers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo         TEXT NOT NULL,
    funcao          TEXT NOT NULL,
    linha           INTEGER DEFAULT 0,
    empresa         TEXT DEFAULT '',
    filial          TEXT DEFAULT '',
    environment     TEXT DEFAULT '',
    modulo          TEXT DEFAULT ''
);
CREATE INDEX idx_env_arquivo ON env_openers(arquivo);

CREATE TABLE IF NOT EXISTS log_calls (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo         TEXT NOT NULL,
    funcao          TEXT DEFAULT '',
    linha           INTEGER DEFAULT 0,
    nivel           TEXT DEFAULT '',            -- INFO|WARN|ERROR|DEBUG (de FwLogMsg) ou 'conout'
    categoria       TEXT DEFAULT ''
);
CREATE INDEX idx_log_arquivo ON log_calls(arquivo);

CREATE TABLE IF NOT EXISTS defines (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo         TEXT NOT NULL,
    nome            TEXT NOT NULL,
    valor           TEXT DEFAULT '',
    linha           INTEGER DEFAULT 0
);
CREATE INDEX idx_define_arquivo ON defines(arquivo);
CREATE INDEX idx_define_nome    ON defines(nome);
```

**Nível 3 — Lint (1 tabela):**

```sql
CREATE TABLE IF NOT EXISTS lint_findings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    arquivo         TEXT NOT NULL,
    funcao          TEXT DEFAULT '',
    linha           INTEGER DEFAULT 0,
    regra_id        TEXT NOT NULL,              -- BP-001, SEC-001, etc.
    severidade      TEXT NOT NULL,              -- critical|error|warning
    snippet         TEXT DEFAULT '',
    sugestao_fix    TEXT DEFAULT ''
);
CREATE INDEX idx_lint_arquivo  ON lint_findings(arquivo);
CREATE INDEX idx_lint_regra    ON lint_findings(regra_id);
CREATE INDEX idx_lint_sev      ON lint_findings(severidade);
```

**Nível 1 — Lookup embarcadas (6 tabelas, pré-populadas via `lookups/*.json` no init):**

```sql
-- WITHOUT ROWID em todas as 6 lookups: rows pequenas (<400 bytes), PK textual
-- frequente, ganho de espaço + velocidade de SELECT por PK.

CREATE TABLE IF NOT EXISTS funcoes_nativas (
    nome            TEXT PRIMARY KEY,
    categoria       TEXT NOT NULL,
    assinatura      TEXT DEFAULT '',
    params_count    INTEGER DEFAULT 0,
    requer_unlock   INTEGER DEFAULT 0,
    requer_close_area INTEGER DEFAULT 0,
    deprecated      INTEGER DEFAULT 0,
    alternativa     TEXT DEFAULT '',
    descricao       TEXT DEFAULT ''
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS funcoes_restritas (
    nome            TEXT PRIMARY KEY,
    categoria       TEXT NOT NULL,
    bloqueada_desde TEXT DEFAULT '',
    alternativa     TEXT DEFAULT ''
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS lint_rules (
    regra_id        TEXT PRIMARY KEY,
    titulo          TEXT NOT NULL,
    severidade      TEXT NOT NULL,
    categoria       TEXT NOT NULL,
    descricao       TEXT NOT NULL,
    fix_guidance    TEXT DEFAULT '',
    detection_kind  TEXT DEFAULT 'regex'
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS sql_macros (
    macro           TEXT PRIMARY KEY,
    descricao       TEXT NOT NULL,
    exemplo         TEXT DEFAULT '',
    output_type     TEXT DEFAULT '',
    safe_for_injection INTEGER DEFAULT 1
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS modulos_erp (
    codigo          TEXT PRIMARY KEY,
    nome            TEXT NOT NULL,
    prefixos_tabelas TEXT DEFAULT '[]',
    prefixos_funcoes TEXT DEFAULT '[]',
    rotinas_principais TEXT DEFAULT '[]'
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS pontos_entrada_padrao (
    nome            TEXT PRIMARY KEY,
    descricao       TEXT DEFAULT '',
    modulo          TEXT DEFAULT '',
    paramixb_count  INTEGER DEFAULT 0,
    retorno_tipo    TEXT DEFAULT '',
    link_tdn        TEXT DEFAULT ''
) WITHOUT ROWID;
```

**Tabela auxiliar de lookup reverso (normalizada para queries "quem usa SA1"):**

`fontes.tabelas_ref` é JSON list — `json_each` não é indexável diretamente. Para
queries reversas ("quais fontes referenciam SA1") indexar via tabela normalizada
pequena, espelhando o JSON na ingestão:

```sql
CREATE TABLE IF NOT EXISTS fonte_tabela (
    arquivo     TEXT NOT NULL REFERENCES fontes(arquivo) ON DELETE CASCADE,
    tabela      TEXT NOT NULL,                  -- 'SA1', 'SC5', 'ZA1'
    modo        TEXT NOT NULL,                  -- 'read'|'write'|'reclock'
    PRIMARY KEY (arquivo, tabela, modo)
) WITHOUT ROWID;
CREATE INDEX idx_ft_tabela ON fonte_tabela(tabela COLLATE NOCASE, modo);
```

`fontes.tabelas_ref`/`write_tables`/`reclock_tables` continuam como JSON para
display rápido (uma row → tudo); `fonte_tabela` serve para SELECTs por tabela.

**Internas (2 tabelas):**

```sql
CREATE TABLE IF NOT EXISTS meta (
    chave   TEXT PRIMARY KEY,
    valor   TEXT NOT NULL
);
-- Linhas obrigatórias gravadas pelo init:
--   schema_version       = '1'         (incrementa quando migrations rodam)
--   plugadvpl_version    = '0.1.0'     (versão da CLI que criou o DB)
--   project_root         = <abs path>  (raiz do projeto cliente)
--   encoding_policy      = 'preserve'  (cp1252|preserve|utf8-warn; default preserve)
-- Linhas gravadas/atualizadas pelo ingest:
--   cli_version          = '0.1.0'     (versão da CLI que rodou o último ingest)
--   parser_version       = 'p1.0.0'    (versão do parser usada — invalida cache se mudar)
--   lookup_bundle_hash   = '<sha256>'  (hash dos 6 JSONs em lookups/ — invalida lookup join se mudar)
--   ingest_config_hash   = '<sha256>'  (hash de flags+encoding_policy do último ingest)
--   indexed_at, total_arquivos, total_funcoes, total_chamadas,
--   total_chunks, total_lint_findings
--
-- `status --check-stale` compara essas versões com as embutidas na CLI atual.
-- Se qualquer uma divergir → recomenda `ingest` full (não incremental).

CREATE TABLE IF NOT EXISTS ingest_progress (
    item        TEXT PRIMARY KEY,
    fase        INTEGER,
    status      TEXT,
    error_msg   TEXT,
    updated_at  TEXT DEFAULT (datetime('now'))
);
```

**FTS5 virtual:**

```sql
-- FTS5 com external content — economiza ~50% de espaço, single source of truth.
-- DOIS índices complementares para cobrir tanto palavras quanto identificadores:

-- Índice A: tokens lógicos (palavras + identificadores com underscore/hífen).
-- tokenchars '_-' mantém "A1_COD" e "FW-Browse" como UM token (não quebra).
CREATE VIRTUAL TABLE IF NOT EXISTS fonte_chunks_fts USING fts5(
    arquivo,
    funcao,
    content,
    content='fonte_chunks',
    content_rowid='rowid',
    tokenize = "unicode61 remove_diacritics 2 tokenchars '_-'"
);

-- Índice B: trigram — para busca substring exata com pontuação ADVPL
-- (SA1->A1_COD, %xfilial%, ::New, PARAMIXB[1]). Disponível desde SQLite 3.34.
-- Permite MATCH '"A1->"' como substring index. Custo: ~2x espaço, mas único
-- jeito de FTS5 lidar com pontuação especial sem perder tokens.
CREATE VIRTUAL TABLE IF NOT EXISTS fonte_chunks_fts_tri USING fts5(
    content,
    content='fonte_chunks',
    content_rowid='rowid',
    tokenize = 'trigram'
);

-- População em massa após bulk-load de fonte_chunks (mais rápido que triggers
-- por linha): INSERT INTO fonte_chunks_fts(fonte_chunks_fts) VALUES('rebuild');
-- Idem para fonte_chunks_fts_tri.
--
-- LIMITAÇÃO trigram: substrings <3 caracteres não casam (e.g., "U_" sozinho).
--
-- Os 3 modos do comando `grep` mapeiam para os índices:
--   --fts        → fonte_chunks_fts (default, BM25 ranking)
--   --literal    → fonte_chunks_fts_tri (substring exata, pontuação OK)
--   --identifier → normalização ADVPL antes do match (uppercase + drop U_)
```

### 4.3 Tabelas reservadas para v0.2+ (criadas via migration, NÃO no MVP)

Para evitar congelar contrato de colunas que talvez precisem mudar, **essas 17 tabelas não existem fisicamente no DB v0.1**. Quando a feature respectiva entrar (v0.2, v0.3, etc.), o `upgrade-schema` aplica a migration correspondente e popula:

- **Universo 2 — Dicionário SX (11 tabelas) — v0.2:** `tabelas`, `campos`, `indices`, `gatilhos`, `parametros`, `perguntas`, `consultas`, `pastas`, `relacionamentos`, `tabelas_genericas`, `grupos_campo`
- **Universo 3 — Rastreabilidade (2 tabelas) — v0.3:** `expressoes_dicionario`, `rastreabilidade_unificada`
- **Auxiliares (4 tabelas) — v0.4:** `jobs`, `schedules`, `record_counts`, `menus`

Comandos que dependem dessas tabelas (`impacto`, `ingest-sx`, etc.) retornam mensagem clara apontando para versão futura. Sem schema fantasma no MVP.

### 4.4 Capabilities (JSON list em `fontes.capabilities`)

Valores possíveis: `MVC`, `BROWSE`, `JOB`, `RPC`, `DIALOG`, `WS-REST`, `WS-SOAP`, `PE`, `TELA_CLASSICA`, `SCHEDULE`, `WORKFLOW`, `COMPATIBILIZADOR`, `TESTE_UNITARIO`, `WEBVIEW`, `REPORT_TR`, `REST_CLIENT`, `EXEC_AUTO_CALLER`, `ENV_OPENER`, `JSON_AWARE`, `MULTI_FILIAL`, `SEQUENCER`, `TRANSACTION`, `FILE_IO`, `PARAMBOX`.

### 4.5 Tipos em `chamadas_funcao.tipo`

`user_func`, `execauto`, `execblock`, `fwexecview`, `fwloadmodel`, `macro`, `method`, `startjob`, `mvc_hook`.

## 5. CLI Python — comandos

Distribuída via PyPI como `plugadvpl`.

### 5.0 Opções globais (aceitas por todos os subcomandos)

| Flag | Default | Significado |
|---|---|---|
| `--root <path>` | `.` (cwd) | Raiz do projeto (onde está/estará `.plugadvpl/`) |
| `--format {json\|table\|md}` | `table` em TTY, `json` em pipe | Formato de saída |
| `--quiet` | desligado | Suprime output não essencial (usado por hooks) |
| `--db <path>` | `<root>/.plugadvpl/index.db` | Caminho explícito do DB |
| `--limit N` | `20` (comandos de listagem) | Máximo de linhas retornadas. Acima desse limite, output inclui sufixo `... e mais N resultados; refine com --table/--module/--path` |
| `--offset N` | `0` | Paginação |
| `--compact` | desligado | Saída ultracompacta (~uma linha por registro) — útil para minimizar tokens |
| `--no-content` | desligado (exceto em `ingest`) | Em `ingest`: indexa metadados sem corpo de chunk (modo metadata-only para ambientes sensíveis). Em queries: omite snippet/content |
| `--next-steps` | ligado | Cada comando termina com "Próximo passo recomendado: ..." (desliga com `--no-next-steps`) |

### 5.1 Setup e manutenção

| Comando | Função |
|---|---|
| `plugadvpl init [--root .] [--encoding-policy {cp1252\|preserve\|utf8-warn}]` | Cria `./.plugadvpl/index.db` vazio com as 22 tabelas + FTS5. Aplica `PRAGMA page_size=8192` e `journal_mode=WAL` (persistidos no DB header). Escreve fragmento delimitado no `CLAUDE.md`. `--encoding-policy` default `preserve` |
| `plugadvpl ingest [paths...] [--incremental] [--workers N]` | Indexa fontes. Default `--incremental` (mtime > last_indexed). `--workers` paraleliza parsing |
| `plugadvpl reindex <arquivo>` | Re-indexa um fonte (após edição). **Inclui sync de FTS5:** `DELETE FROM fonte_chunks_fts WHERE arquivo=?` + `INSERT INTO fonte_chunks_fts SELECT ... WHERE arquivo=?` |
| `plugadvpl status [--check-stale]` | Total arquivos/funções/chamadas, último ingest. Com `--check-stale`: lista fontes com mtime > indexed_at. Comando rápido (sem doctor) — usado pelo hook |
| `plugadvpl doctor` | Diagnóstico completo: encoding suspeito, fontes falhados, chunks órfãos, FTS5 dessincronizado, lint findings inconsistentes. Mais lento que `status` |
| `plugadvpl version` | Versão CLI + schema_version do DB |
| `plugadvpl upgrade-schema` | Migra DB para nova versão (idempotente) |

### 5.2 Descoberta

| Comando | Exemplo |
|---|---|
| `plugadvpl find function <nome>` | `find function FATA050` → arquivo, linhas, assinatura |
| `plugadvpl find file <pattern>` | `find file 'MAT*.prw'` → lista com source_type, capabilities |
| `plugadvpl grep <padrão> [--fts\|--literal\|--identifier] [--limit N]` | 3 modos: `--fts` (default, BM25 ranking), `--literal` (LIKE com escape p/ pontuação tipo `%xfilial%`), `--identifier` (normaliza identificadores: uppercase, remove `U_` prefix). Default `--limit 20` com hint "mais X resultados" |

### 5.3 Análise

| Comando | Exemplo |
|---|---|
| `plugadvpl callers <funcao>` | Quem chama essa função (lê de `chamadas_funcao` onde `destino=funcao`) |
| `plugadvpl callees <funcao>` | O que ela chama (lê de `chamadas_funcao` onde `funcao_origem=funcao`) |
| `plugadvpl tables [--read\|--write\|--reclock] <SA1>` | Quem lê/escreve/RecLock-a |
| `plugadvpl param <MV_X>` | Onde é usado, modo (read/write), default |
| `plugadvpl pergunta <grupo>` | Onde grupo SX1 é usado |
| `plugadvpl sql [--op X] [--table Y]` | SQL embedado filtrado |

### 5.4 Arquétipo e estrutura

| Comando | Função |
|---|---|
| `plugadvpl arch <arquivo>` | **Comando-chefe.** Resumo completo do fonte: source_type, capabilities, includes, namespace, encoding, LOC, lista de funções compacta. Substitui Read de fonte inteiro |
| `plugadvpl mvc <arquivo>` | Se MVC: lista ModelDef/ViewDef/MenuDef + hooks |
| `plugadvpl ws <arquivo>` | WS structures (WSSTRUCT/WSSERVICE/WSMETHOD com WSDATA) |
| `plugadvpl rest [--path /pattern] [--verb GET]` | Lista endpoints REST |
| `plugadvpl env-openers` | Fontes que abrem ambiente via RpcSetEnv |
| `plugadvpl http-calls` | Lista chamadas HTTP outbound |

### 5.5 Qualidade

| Comando | Função |
|---|---|
| `plugadvpl lint [arquivo] [--rule X] [--severity Y]` | Lista findings filtrados |
| `plugadvpl lint-rules` | Lista as 24 regras catalogadas (13 ativas no v0.1 via regex, 11 deferidas para v0.2 — semantic/cross-file) |

### 5.6 Lookup

| Comando | Função |
|---|---|
| `plugadvpl native <nome>` | Info sobre função nativa TOTVS |
| `plugadvpl restricted [<nome>]` | Funções restritas (195) com alternativa |
| `plugadvpl pe <nome>` | PE conhecido: PARAMIXB count, módulo |
| `plugadvpl modulo <prefixo\|nome>` | Info sobre módulo ERP |

### 5.7 Reservados para v0.2+

`plugadvpl impacto <campo>`, `plugadvpl ingest-sx`, `plugadvpl ingest-ini` — retornam mensagem apontando versão futura.

## 6. Slash commands (via `skills/`, não `commands/`)

A documentação oficial do Claude Code (2026) diz: *"Custom commands have been merged into skills. Use `skills/` for new plugins."* Cada `skills/<nome>/SKILL.md` em plugin com `name: plugadvpl` gera automaticamente `/plugadvpl:<nome>`.

**Frontmatter SKILL.md — conforme docs oficiais:**

```yaml
---
description: O que essa skill faz (obrigatório de fato — auto-load usa)
disable-model-invocation: true     # opcional: Claude NÃO invoca sozinho, só via /
user-invocable: false              # opcional: NÃO aparece no menu de slash
when_to_use: "quando o usuário quer ..."  # opcional
allowed-tools: [Bash, Read]        # opcional: restringe tools
arguments: [arquivo]               # opcional: args nomeados (vira $arquivo)
---
```

**Por isso o plugin tem 23 skills no total:**
- **13 skills de comando** com `disable-model-invocation: true` (só via `/`, executam wrapper CLI)
- **10 skills de conhecimento** sem `disable-model-invocation` (Claude carrega automaticamente quando description casa com contexto; também invocáveis via `/`)
- **1 dessas** (`plugadvpl-index-usage`) é a skill-chefe que injeta a regra "consulte o índice antes de Read"

**Args em skills:** placeholder `$ARGUMENTS` = string completo; `$0`, `$1`, ... = posicionais; ou nomeados via frontmatter (`arguments: [arquivo]` → `$arquivo` na body do SKILL.md).

**Variáveis disponíveis no script:** `${CLAUDE_PLUGIN_ROOT}` (path do plugin, **muda em updates**), `${CLAUDE_PLUGIN_DATA}` (path persistente entre updates — útil para cache do plugin), `${CLAUDE_SESSION_ID}`, `${CLAUDE_SKILL_DIR}`.

### 6.1 Skills de comando

Cada uma é um `skills/<nome>/SKILL.md` curto com frontmatter + descrição + wrapper `Bash`:

| Slash gerado | Wrapper CLI |
|---|---|
| `/plugadvpl:init` | `uvx plugadvpl@<v> init` |
| `/plugadvpl:ingest` | `uvx plugadvpl@<v> ingest` |
| `/plugadvpl:reindex <arq>` | `uvx plugadvpl@<v> reindex <arq>` |
| `/plugadvpl:status` | `uvx plugadvpl@<v> status` |
| `/plugadvpl:find <termo>` | tenta `find function`, `find file`, `grep --fts` em sequência |
| `/plugadvpl:callers <f>` | `uvx plugadvpl@<v> callers <f>` |
| `/plugadvpl:callees <f>` | `uvx plugadvpl@<v> callees <f>` |
| `/plugadvpl:tables <T>` | `uvx plugadvpl@<v> tables <T>` |
| `/plugadvpl:param <MV>` | `uvx plugadvpl@<v> param <MV>` |
| `/plugadvpl:arch <arq>` | `uvx plugadvpl@<v> arch <arq>` |
| `/plugadvpl:lint [arq]` | `uvx plugadvpl@<v> lint [arq]` |
| `/plugadvpl:doctor` | `uvx plugadvpl@<v> doctor` |
| `/plugadvpl:help` | Lista comandos disponíveis (gerada por `plugadvpl --help`) |

**`<v>` é injetado em build time** pelo `scripts/bump_marketplace_version.py` — todos os SKILL.md são templates `{{plugadvpl_version}}` substituídos no release. Isso garante alinhamento plugin↔CLI.

### 6.2 Skills de conhecimento

Geram slash commands mas seu valor primário é ser **carregadas no contexto** quando relevante (Claude detecta via frontmatter `description`):

| Slash gerado | Conteúdo |
|---|---|
| `/plugadvpl:plugadvpl-index-usage` | **Skill-chefe**, sempre ativa. Tabela "qual ferramenta usar para qual pergunta" |
| `/plugadvpl:advpl-encoding` | Política preserve-by-default, casos cp1252 vs UTF-8 |
| `/plugadvpl:advpl-fundamentals` | Notação húngara, naming, prefixos, restricted functions |
| `/plugadvpl:advpl-mvc` | MenuDef/ModelDef/ViewDef, hooks |
| `/plugadvpl:advpl-embedded-sql` | Macros, 6 restrições |
| `/plugadvpl:advpl-matxfis` | Família MATXFIS |
| `/plugadvpl:advpl-pontos-entrada` | PARAMIXB, patterns |
| `/plugadvpl:advpl-webservice` | REST/SOAP, RpcSetEnv proibido em REST |
| `/plugadvpl:advpl-jobs-rpc` | RpcSetEnv, StartJob, funções proibidas em JOB |
| `/plugadvpl:advpl-code-review` | 24 regras (13 ativas no v0.1, 11 deferidas) |

## 7. Skills (10) — `skills/<nome>/SKILL.md`

| # | Skill | Quando ativa | Conteúdo principal |
|---|---|---|---|
| 1 | `plugadvpl-index-usage` | Sempre que envolve análise de fonte ADVPL | **Skill-chefe.** Fluxo: sempre consultar `arch/find/callers/tables/param` antes de Read |
| 2 | `advpl-encoding-cp1252` | Antes de Edit/Write em `.prw/.tlpp/.prx`, ou quando usuário menciona encoding/acentos | NUNCA UTF-8. Caracteres que quebram. Como verificar com `doctor` |
| 3 | `advpl-fundamentals` | Geração de código ADVPL | Notação húngara, prefixos de módulo, naming, `User Function` precisa prefixo de cliente. Linka `funcoes_restritas` |
| 4 | `advpl-mvc` | Trabalhando com MVC | MenuDef/ModelDef/ViewDef, `aRotina`, MODEL_OPERATION_*, hooks (bCommit/bTudoOk/bLineOk/bPosVld/bPreVld), FWFormStruct1/2 |
| 5 | `advpl-embedded-sql` | Editando BeginSQL/TCQuery | Macros `%table%`, `%xfilial%`, `%notDel%`, `%exp%`, `%Order%`. 6 restrições. Lint PERF-001..006 |
| 6 | `advpl-matxfis` | Faturamento/Fiscal | Família MATXFIS, integração SF2/SD2/SF3, SPED, ECF, REINF. PEs comuns do módulo fiscal |
| 7 | `advpl-pontos-entrada` | Criando/editando PE | `User Function NOME(PARAMIXB[1..N])`, pattern de nome, retorno via PARAMIXB. Linka `pontos_entrada_padrao` |
| 8 | `advpl-webservice` | WS REST/SOAP | WSRESTFUL com `@Get/@Post`, WSSERVICE+WSSTRUCT, content-type, retorno de erro. **NUNCA RpcSetEnv em REST** (SEC-001) |
| 9 | `advpl-jobs-rpc` | JOB, scheduler, threads | `Main Function`, `RpcSetEnv`, `PREPARE/END ENVIRONMENT`, `StartJob`, `MsRunInThread`. Funções proibidas em JOB |
| 10 | `advpl-code-review` | Após gerar/editar código | 24 regras lint catalogadas (BP/SEC/PERF/MOD) — 13 ativas no v0.1, 11 deferidas para v0.2. Como rodar `lint`. Checklist por severidade |

## 8. Agents (4) — `agents/<nome>.md`

**Distinção agent × skill:** *skill* é referência inline (Claude lê e aplica conhecimento); *agent* é orquestrador autônomo multi-step (recebe tarefa, executa N comandos+leituras, retorna resultado consolidado). Agent **dispara** skills durante o workflow; skill **não** dispara agent.

| Agent | Quando dispatchar | Workflow |
|---|---|---|
| `advpl-analyzer` | "explique como funciona X" | `arch` → `callers/callees` → lê chunks específicos → sumariza |
| `advpl-impact-analyzer` | "se eu mudar X, o que quebra?" | `callers/tables/param` → lista impacto por arquivo+linha |
| `advpl-code-generator` | "crie User Function/MVC/REST/PE para X" | Consulta skill → `find` para exemplos similares → gera respeitando encoding+naming+restricted → auto-`lint` |
| `advpl-reviewer-bot` | "revise este código" (workflow autônomo) | `arch + lint` → cruza com `funcoes_restritas` → sugere fix por severidade. **Renomeado para evitar colisão com skill #10 `advpl-code-review`** |

## 9. Hook — `hooks/`

### 9.1 `hooks/hooks.json` (formato oficial conferido em docs Claude Code 2026)

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "${CLAUDE_PLUGIN_ROOT}/hooks/session-start",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

### 9.2 Schema oficial de input/output do hook

**Input via stdin (JSON):**
```json
{
  "session_id": "abc123",
  "cwd": "/path/to/project",
  "hook_event_name": "SessionStart",
  "source": "startup"
}
```
`source` pode ser: `startup` | `resume` | `clear` | `compact`.

**Output via stdout (JSON, opcional):**
```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "texto que será injetado no contexto do Claude"
  }
}
```

**Exit codes:**
- `0` + stdout JSON → injeta `additionalContext`
- `0` + stdout vazio → silencioso (recomendado quando nada útil a reportar)
- `2` → blocking error (stderr mostrado ao usuário, tool call bloqueado)
- outros → non-blocking error (stderr em transcript)

### 9.3 `hooks/session-start` (lógica)

Executa só no início da sessão. **Retorna JSON apenas quando há algo útil para reportar** — se tudo OK ou pasta não tem ADVPL, exit 0 com stdout vazio (sem JSON).

```
1. Detecta .prw|.tlpp|.prx no diretório atual (depth ≤ 2).
2. Se NÃO há ADVPL → return {} (silêncio).
3. Se há ADVPL e .plugadvpl/index.db NÃO existe:
   → additionalContext: "Projeto ADVPL detectado (N fontes).
     Execute /plugadvpl:init seguido de /plugadvpl:ingest."
4. Se ambos existem:
   → uvx plugadvpl@<v> status --check-stale --quiet --format json
   → Compara mtime_ns, size_bytes E versions (parser_version, cli_version, lookup_bundle_hash):
     - Se M arquivos stale por mtime/size → additionalContext: "M arquivos
       modificados. /plugadvpl:reindex <arq> ou /plugadvpl:ingest --incremental"
     - Se parser_version/lookup_bundle_hash diferem → additionalContext:
       "Parser/lookups atualizados. Recomendado ingest full: /plugadvpl:ingest"
     - Se nada stale → return {} (silêncio).
5. NÃO indexa automaticamente.
```

**Por que `status --check-stale` e não `doctor`:** o hook roda a cada início de sessão
(várias vezes por dia). `status` faz só 1 query SQL (`SELECT arquivo, mtime_ns, size_bytes FROM fontes`)
e compara com `os.stat` de cada arquivo — milissegundos. `doctor` faz dezenas de checks
(integridade FTS5, encoding, órfãos) e leva segundos — apropriado só sob demanda do dev.
```

## 10. CLAUDE.md fragment

Escrito por `init` numa região delimitada (idempotente):

```markdown
<!-- BEGIN plugadvpl -->
## Plugadvpl — índice ADVPL local (consulte ANTES de ler fontes)

Este projeto tem `.plugadvpl/index.db` com metadados de TODOS os fontes
ADVPL/TLPP. NUNCA leia um `.prw`/`.tlpp` inteiro sem antes consultar o
índice — fontes Protheus têm 1.000–10.000 linhas e queimar tokens neles
desperdiça contexto.

### Regra de decisão — qual ferramenta usar

| Pergunta do usuário                       | Comando primeiro                          |
|-------------------------------------------|-------------------------------------------|
| "O que faz o fonte X?"                    | `plugadvpl arch X`                        |
| "Onde está a função Y?"                   | `plugadvpl find function Y`               |
| "Quem chama Y?"                           | `plugadvpl callers Y`                     |
| "O que Y chama por dentro?"               | `plugadvpl callees Y`                     |
| "Quem lê/grava na tabela SA1?"            | `plugadvpl tables SA1`                    |
| "Onde MV_LOCALIZA é usado?"               | `plugadvpl param MV_LOCALIZA`             |
| "Mostre o SQL de update em SC5"           | `plugadvpl sql --op update --table SC5`   |
| "Tem erro de boas práticas em X?"         | `plugadvpl lint X`                        |
| "Achar função que faz <descrição>"        | `plugadvpl grep "<termo>"`                |
| "Essa função é nativa do TOTVS?"          | `plugadvpl native <nome>`                 |
| "Posso usar `StaticCall`?"                | `plugadvpl restricted StaticCall`         |

### Quando É permitido `Read` no .prw cru

Só depois de localizar a linha exata via índice. Exemplos válidos:
- `Read FATA050.prw#L234-280`  ← intervalo identificado em operacoes_escrita
- `Read MATA461.prw#L1-50`     ← cabeçalho/header
NUNCA: `Read FATA050.prw` sem range.

### Codificação (preserve-by-default)

Cada fonte tem **seu próprio encoding** detectado e armazenado em `fontes.encoding`:
- `.prw`/`.prx` clássico: **cp1252** (Windows-1252) é o esperado.
- `.tlpp` moderno: pode ser **UTF-8** (TLPP suporta).
- Misturas são reais em clientes grandes.

**Regra para edição:** **preserve sempre o encoding detectado do arquivo.**
NUNCA mude UTF-8 para cp1252 ou vice-versa sem ordem explícita do dev — quebra o
compilador AppServer e/ou perde caracteres. Em caso de dúvida, rode
`plugadvpl doctor` e verifique a coluna `encoding` em `fontes`.

### Comandos slash equivalentes (preferíveis no chat)

`/plugadvpl:arch <arq>`, `/plugadvpl:find <termo>`, `/plugadvpl:callers <f>`,
`/plugadvpl:callees <f>`, `/plugadvpl:tables <T>`, `/plugadvpl:param <MV>`,
`/plugadvpl:lint [arq]`, `/plugadvpl:status`, `/plugadvpl:ingest`,
`/plugadvpl:reindex <arq>`.

### Output budget — Claude DEVE respeitar limites

Todo comando default retorna no máximo 20 resultados (`--limit 20`). Se a saída
indicar "... e mais N resultados; refine com --table/--module/--path", o Claude
deve refinar com filtros, **não pedir mais resultados sem critério**. Comandos
suportam `--compact` para output minimalista (uma linha/registro).

### Status do índice

`plugadvpl status` mostra contagens e última ingestão. Se arquivos foram
editados fora do Claude, rode `/plugadvpl:reindex <arquivo>` ou
`/plugadvpl:ingest --incremental`.
<!-- END plugadvpl -->
```

## 11. Performance e ingestão rápida

### 11.1 Técnicas portadas (validadas em ampla base de fontes ADVPL)

1. PRAGMAs durante ingest: `journal_mode=WAL`, `synchronous=NORMAL`, `cache_size=-20000`
2. `executemany` para todos os INSERTs em batch
3. Commit em lotes (ajustado — ver item 25 abaixo)
4. Fast-path encoding cp1252 (99% dos fontes); fallback utf-8 → chardet[:4096]
5. `os.walk` (1 traversal) em vez de `rglob` múltiplo
6. Regex pre-compilados em **module-level top** (importante p/ workers — ver item 27)
7. Pré-carregar lookups (módulos, prefixos) uma vez
8. `gc.collect()` a cada N arquivos + `del` agressivo
9. `MAX_FILE_BYTES = 5_000_000` — pula arquivos >5MB
10. Build de tuplas antes do `executemany`
11. Two-pass: metadados → chunks
12. ~~`INSERT OR REPLACE`~~ → substituído por UPSERT idempotente (ver item 24)
13. Memory monitoring (psutil.rss)
14. Pre-load module map (`lru_cache`)
15. Progress streaming via yield

### 11.2 Melhorias adicionais do plugin

16. `PRAGMA temp_store=MEMORY`
17. `PRAGMA mmap_size=268435456` (256MB)
18. ~~`locking_mode=EXCLUSIVE`~~ **REMOVIDO** — mata WAL. Usa `busy_timeout=5000` + WAL nativo (1 writer + N readers)
19. `PRAGMA page_size=8192` (definido antes do CREATE TABLE, no `init`)
20. **Paralelização adaptativa** (ajustado vs spec original):
    - **Default: single-thread** se ≤200 arquivos OR estimativa <2s total (overhead de pool não compensa)
    - **`ThreadPoolExecutor`** se 200–2000 arquivos OR estimativa 2–20s (regex Python libera GIL durante match em C; sem custo de spawn)
    - **`ProcessPoolExecutor`** só se >2000 arquivos OR estimativa >20s. Em Linux/Mac: `mp_context=multiprocessing.get_context("fork")` para evitar spawn overhead de Python 3.14. Em Windows: spawn é o único disponível, custa ~200ms/worker.
    - **CLI flag `--workers N`** sobrescreve a heurística. `--workers 0` força single-thread.
    - **Justificativa:** parser regex roda ~30–80ms/arquivo. ProcessPool spawn (200ms/worker) só vale para batches grandes. Confirmado em pesquisa 2026: pool só compensa quando task >500ms.
21. FTS5 com `content='fonte_chunks'` (**external content**) + populado em massa ao final via `INSERT INTO fonte_chunks_fts(fonte_chunks_fts) VALUES('rebuild')`. Idem para `fonte_chunks_fts_tri` (trigram). Economiza ~50% espaço.
22. **Reindex transacional por arquivo:** `BEGIN → DELETE FROM fonte_chunks_fts WHERE arquivo=? → DELETE dependentes WHERE arquivo=? → UPSERT em fontes via ON CONFLICT DO UPDATE → INSERT dependentes → INSERT INTO fonte_chunks_fts SELECT WHERE arquivo=? → COMMIT`. Consistência FTS5 garantida.
23. **Invalidação inteligente:** `--check-stale` compara `mtime_ns`, `size_bytes`, **e** `parser_version`, `lookup_bundle_hash`, `schema_version`. Versão diferente → recomenda ingest full.

### 11.3 Novas técnicas (descobertas em pesquisa de best practices 2026)

24. **UPSERT em vez de `INSERT OR REPLACE`:**
    ```sql
    INSERT INTO fontes (arquivo, hash, ...) VALUES (?, ?, ...)
    ON CONFLICT(arquivo) DO UPDATE SET
        hash = excluded.hash, ...
    WHERE excluded.hash != fontes.hash;
    ```
    Vantagens vs `INSERT OR REPLACE`:
    - Não destrói row (preserva rowid, FK CASCADE, FTS5 sync) — `OR REPLACE` faz DELETE+INSERT que dispara triggers desnecessários
    - `WHERE excluded.hash != fontes.hash` faz **skip** quando conteúdo idêntico (no-op rápido para incremental)

25. **Batch size aumentado:** commit a cada **500–1000 chunks** (não a cada 50 arquivos). Consenso: 1000–5000 rows/transação é ótimo para SQLite ([phiresky](https://phiresky.github.io/blog/2020/sqlite-performance-tuning/)). Para fontes ADVPL com ~10 chunks/arquivo, isso vira ~50–100 arquivos/transação.

26. **`PRAGMA optimize` antes de close()** — recomendação oficial >=3.46 (`sqlite.org/pragma.html#pragma_optimize`): "Applications with short-lived database connections should run PRAGMA optimize once when the database connection closes."

27. **Regex compilados em module-level top:** workers `ProcessPool` re-importam o módulo, então `re.compile` deve estar fora de qualquer função. Cada worker compila uma vez. Pattern objects **não devem** ser passados via pickle.

28. **`re` stdlib em vez de `regex` PyPI:** para nossos padrões simples (`^Function\s+`), `re` é mais rápido por menos overhead. Reservar `regex` PyPI só se precisar de lookbehind variável ou Unicode property class.

### 11.4 Strip-first: pré-tokenização leve antes das regex

**Problema:** regex sobre raw text gera falso-positivos óbvios:
- `// TODO: RecLock("SA1")` em comentário vira "write em SA1"
- `cMsg := "MV_LOCALIZA não definido"` em string vira "uso de parâmetro MV_LOCALIZA"

**Solução** (padrão da indústria — ProLeap COBOL faz isso): mini-tokenizer de
~100 linhas que **substitui comentários e strings por espaços** (preserva offsets
e contagem de linhas), e roda **antes** das 25 regex de extração:

```python
def strip_advpl(content: str) -> str:
    """Retorna content com comentários e strings substituídos por espaços.
    Preserva newlines e offsets (mesmo length). ~100 linhas, single pass.
    """
    out = []
    i, n = 0, len(content)
    state = 'code'  # code | line_comment | block_comment | str_dq | str_sq
    while i < n:
        c = content[i]
        if state == 'code':
            # detecta início de comentário/string
            if c == '/' and i+1 < n and content[i+1] == '/':
                state = 'line_comment'; out.append('  '); i += 2; continue
            if c == '/' and i+1 < n and content[i+1] == '*':
                state = 'block_comment'; out.append('  '); i += 2; continue
            if c == '"':
                state = 'str_dq'; out.append(' '); i += 1; continue
            if c == "'":
                state = 'str_sq'; out.append(' '); i += 1; continue
            out.append(c)
        elif state == 'line_comment':
            if c == '\n':
                state = 'code'; out.append('\n')  # preserva newline
            else:
                out.append(' ')
        elif state == 'block_comment':
            if c == '*' and i+1 < n and content[i+1] == '/':
                state = 'code'; out.append('  '); i += 2; continue
            out.append(' ' if c != '\n' else '\n')
        elif state in ('str_dq', 'str_sq'):
            quote = '"' if state == 'str_dq' else "'"
            if c == '\\' and i+1 < n:
                out.extend(['  ']); i += 2; continue  # escape
            if c == quote:
                state = 'code'; out.append(' ')
            else:
                out.append(' ' if c != '\n' else '\n')
        i += 1
    return ''.join(out)
```

**Overhead:** ~5% do tempo total de parse (single pass char-by-char). Roda 1× por arquivo, antes de qualquer regex.

**Ganho:** elimina ~80% dos falso-positivos típicos de regex em código fonte.

**Ressalva:** macros runtime `&var.` (substituição dinâmica) **não são resolvíveis estaticamente** — limitação inerente, documentada.

### 11.3 Estimativas (projeto cliente típico, ~2.000 fontes)

| Configuração | Tempo |
|---|---|
| Single-thread, sem otimizações | ~5–8 min |
| Single-thread, com PRAGMAs +6 | ~3–5 min |
| `--workers 8` | **~30–60s** |
| `--incremental` (10 arquivos mudaram) | <3s |
| `reindex` (1 arquivo) | <100ms |

### 11.4 Estrutura do ingest (`cli/plugadvpl/ingest.py`)

```python
def ingest(root: Path, *, workers: int = 0, incremental: bool = True) -> dict:
    """
    1. Scan: os.walk com filtro por suffix → lista de Paths.
       Filtra extensões exatas {.prw, .tlpp, .prx, .apw}; rejeita
       qualquer sufixo extra (.bak, .corrupted.bak, .old, .bak2, .tmp, etc.).
       Dedup case-insensitive.
    2. Stale filter (se --incremental): SELECT arquivo, mtime_ns FROM fontes
       → mantém só os com mtime > indexado_em ou novos.
    3. PRAGMAs de ingest (WAL, NORMAL, cache, mmap, exclusive lock, temp_store).
    4. Pass 1 — Metadados (paralelo se workers > 0):
       ProcessPoolExecutor parses em N procs → fila → 1 writer executemany
       em batches de 50 arquivos. Insere em fontes, funcao_docs,
       chamadas_funcao, parametros_uso, perguntas_uso, operacoes_escrita,
       sql_embedado, rest_endpoints, http_calls, env_openers, log_calls,
       defines.
    5. Pass 2 — Chunks (mesmo padrão paralelo).
    6. Pass 3 — FTS5 populate final (1 INSERT INTO ... SELECT).
    7. Pass 4 — Lint findings single-file (regex). MVP cobre 13 das 24 regras
       catalogadas — as detectáveis em arquivo único via regex/heurística
       (RecLock sem MsUnlock no mesmo escopo, BEGIN TRANSACTION sem END,
       MsExecAuto sem check de lMsErroAuto, SELECT *, sem %notDel%,
       sem %xfilial%, Pergunte sem retorno, RpcSetEnv em WSRESTFUL,
       ConOut em produção, função >6 parâmetros, RecLock misturado com
       DbRLock/dbAppend cru, PUBLIC declarado, ENV opener fora de Main Function).
    8. Pass 5 — Lint cross-file/semantic (DEFERIDO para v0.2): User Function sem
       prefixo de cliente, funções não chamadas, etc. Schema `lint_rules.detection_kind`
       já contempla 'regex'|'semantic'|'cross_file' para deixar as 11 regras
       restantes pré-cadastradas (vazias até v0.2).
    9. Restore PRAGMAs (synchronous=FULL, locking_mode=NORMAL).
   10. Atualiza meta (contagens, indexed_at, schema_version).
    """
```

## 12. Testes, CI e release

### 12.1 Pirâmide de testes

```
                  ┌──────────────────────┐
                  │  E2E manual (local)  │  ← test_e2e_local_*.py
                  │  fixture: ~2.000 prw │     compara com baseline interno
                  └──────────────────────┘
                ┌──────────────────────────┐
                │  Integration (CI)        │  ← test_ingest_synthetic.py
                │  fixture: ~20 prw curados│     ingest completo, asserts
                └──────────────────────────┘
              ┌──────────────────────────────┐
              │  Parser unit (CI)            │  ← test_parser_*.py
              │  cada extrator: ~5 inputs    │     funções, tabelas, MV, calls
              └──────────────────────────────┘
            ┌──────────────────────────────────┐
            │  Schema/CLI (CI, rápido)         │  ← test_schema.py, test_cli.py
            └──────────────────────────────────┘
```

### 12.2 Estrutura

```
cli/tests/
├── conftest.py
├── fixtures/
│   ├── synthetic/                    # ~20 .prw inventados, versionados
│   │   ├── mvc_complete.prw
│   │   ├── classic_browse.prw
│   │   ├── pe_simple.prw
│   │   ├── ws_rest.tlpp
│   │   ├── ws_soap.prw
│   │   ├── job_rpc.prw
│   │   ├── reclock_pattern.prw
│   │   ├── reclock_unbalanced.prw    # lint!
│   │   ├── exec_auto.prw
│   │   ├── sql_embedded.prw
│   │   ├── encoding_cp1252.prw
│   │   ├── encoding_utf8.prw         # deve avisar
│   │   ├── empty.prw                 # deve pular
│   │   ├── huge.prw                  # > 5MB — deve pular
│   │   ├── corrupted.bak             # extensão errada — deve pular
│   │   ├── tlpp_namespace.tlpp
│   │   ├── http_outbound.prw
│   │   ├── mvc_hooks.prw
│   │   ├── multi_filial.prw
│   │   └── pubvars.prw               # lint MOD-002
│   ├── expected/                     # snapshots JSON do parsing
│   └── baseline_snippet.db           # subset 50 fontes (gerado uma vez)
├── unit/                             # 13+ arquivos
├── integration/                      # 8 arquivos
├── bench/                            # pytest-benchmark
└── e2e_local/                        # marker `pytest -m local`
```

### 12.3 Testes-chave

**`test_ingest_synthetic_full`** (CI):
```python
def test_ingest_synthetic_full(tmp_path, synthetic_fixtures):
    shutil.copytree(synthetic_fixtures, tmp_path / "src")
    counters = ingest(tmp_path / "src", workers=2)
    assert counters["arquivos_total"] == 20
    assert counters["arquivos_ok"] >= 18
    assert counters["arquivos_pulado"] == 3  # huge + empty + corrupted

    conn = sqlite3.connect(tmp_path / "src/.plugadvpl/index.db")
    assert conn.execute("SELECT COUNT(*) FROM fontes WHERE source_type='mvc'").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM lint_findings WHERE regra_id='BP-001'").fetchone()[0] >= 1
    assert conn.execute("SELECT COUNT(*) FROM parametros_uso WHERE parametro='MV_LOCALIZA'").fetchone()[0] >= 1
```

**`test_e2e_local_parity`** (local-only):
```python
@pytest.mark.local
@pytest.mark.skipif(not Path(os.environ.get("PLUGADVPL_E2E_FONTES_DIR", "")).exists(),
                    reason="local fixture only")
def test_parity_with_baseline():
    """Garante paridade ≤10% com baseline interno (mesma base de fontes)."""
    fontes_dir = Path(os.environ["PLUGADVPL_E2E_FONTES_DIR"])
    counters = ingest(fontes_dir, workers=8)

    plug = sqlite3.connect(fontes_dir / ".plugadvpl/index.db")
    baseline = sqlite3.connect(os.environ["PLUGADVPL_E2E_BASELINE_DB"])

    for table in ["fontes", "fonte_chunks", "chamadas_funcao",
                  "parametros_uso", "perguntas_uso",
                  "operacoes_escrita", "sql_embedado"]:
        plug_n = plug.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        base_n = baseline.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        delta = abs(plug_n - base_n) / max(base_n, 1)
        assert delta < 0.10, f"{table}: plug={plug_n} vs baseline={base_n} (Δ={delta:.1%})"
```

**`test_ingest_2k_under_60s`** (CI com pytest-benchmark):
```python
def test_ingest_2k_under_60s(benchmark, large_synthetic_fixtures):
    result = benchmark(lambda: ingest(large_synthetic_fixtures, workers=4))
    assert result["arquivos_ok"] >= 1950
    assert benchmark.stats["mean"] < 60.0
```

### 12.4 Lint do plugin (markdown + JSON)

`scripts/validate_plugin.py`:
- Valida `.claude-plugin/plugin.json` (schema oficial Claude Code)
- Valida `.claude-plugin/marketplace.json`
- Valida cada `commands/*.md` tem frontmatter mínimo
- Valida cada `skills/*/SKILL.md` tem `name` + `description`
- Valida cada `agents/*.md` tem frontmatter
- Valida `hooks/hooks.json`

### 12.5 CI (GitHub Actions)

```yaml
# .github/workflows/ci.yml — todo PR
jobs:
  lint-plugin:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python scripts/validate_plugin.py

  test-cli:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
        python: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv pip install -e cli[dev]
      - run: pytest cli/tests/unit cli/tests/integration -v
      - run: pytest cli/tests/bench --benchmark-only --benchmark-fail-on-decrease

  smoke-uvx:
    runs-on: ubuntu-latest
    needs: test-cli
    steps:
      - uses: astral-sh/setup-uv@v3
      - run: uvx --from . plugadvpl --help
      - run: uvx --from . plugadvpl version
```

### 12.6 Release — dois canais independentes

**IMPORTANTE — esclarecimento sobre distribuição:**

O projeto tem **dois canais de release totalmente independentes**:

| Canal | Conteúdo | Como o usuário "consome" |
|---|---|---|
| **PyPI** | A CLI Python `plugadvpl` (parser, ingest, query) | `uvx plugadvpl@0.1.0` ou `uv tool install plugadvpl` |
| **Marketplace Claude Code** | O plugin (skills, agents, hook, plugin.json, marketplace.json) | `/plugin marketplace add github.com/owner/plugadvpl` + `/plugin install plugadvpl` |

**Claude Code plugins NÃO vão para PyPI.** Eles ficam no próprio repo GitHub. O marketplace é descoberto via clone do repo na pasta do usuário. PyPI é só para a CLI.

**Alinhamento entre os dois:** O plugin v0.1.0 (markdown) **chama** `uvx plugadvpl@0.1.0` (CLI). Para que isso funcione, os dois precisam ser lançados em ordem: **CLI primeiro (PyPI)**, depois plugin (marketplace).

### 12.6.1 Fluxo de release em duas etapas

**Problema com workflows acionados por tag:** o checkout numa tag fica em detached HEAD; `git commit && push` falha ou vai para lugar inesperado. Por isso o bump de versão acontece **antes** da tag, e o workflow de tag só publica artefatos.

**Etapa 1 — `release-prepare.yml`** (acionado por dispatch manual com input `version`):

```yaml
on:
  workflow_dispatch:
    inputs:
      version:
        description: 'Versão a lançar (ex: 0.1.0)'
        required: true

jobs:
  prepare-release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: main
      - run: |
          python scripts/bump_marketplace_version.py "${{ github.event.inputs.version }}"
          python scripts/render_skill_templates.py "${{ github.event.inputs.version }}"
          # gera CHANGELOG section
          python scripts/update_changelog.py "${{ github.event.inputs.version }}"
      - uses: peter-evans/create-pull-request@v6
        with:
          title: "Release ${{ github.event.inputs.version }}"
          branch: "release/${{ github.event.inputs.version }}"
          commit-message: "release: ${{ github.event.inputs.version }}"
          body: "Bump version + render skill templates + changelog. Após merge, criar tag v${{ github.event.inputs.version }}."
```

**Etapa 2 — `release.yml`** (acionado por tag `v*`, após merge da PR da etapa 1):

```yaml
on:
  push:
    tags: ['v*']

permissions:
  contents: write        # github-release
  id-token: write        # OIDC para PyPI trusted publisher

jobs:
  # Publica a CLI no PyPI (canal 1)
  publish-pypi:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv build cli/
      # Trusted Publisher (OIDC) — sem API token armazenado.
      # Configurar uma vez em pypi.org/manage/account/publishing/
      - uses: pypa/gh-action-pypi-publish@release/v1

  # Cria release no GitHub (canal 2 — plugin marketplace já está no repo;
  # usuários rodam /plugin marketplace update para receber a nova versão)
  github-release:
    runs-on: ubuntu-latest
    needs: publish-pypi
    steps:
      - uses: actions/checkout@v4
      - uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          files: dist/*
```

**Trusted Publisher OIDC** é a recomendação oficial PyPI 2026 ([docs.pypi.org/trusted-publishers](https://docs.pypi.org/trusted-publishers/)) — sem API token armazenado, sem rotação manual. Para pre-release (`v0.1.0-rc1`) usar Trusted Publisher separado configurado em test.pypi.org.

Nada que precise commitar de dentro do workflow disparado por tag.

### 12.7 Versionamento e pyproject.toml

- **SemVer**. `0.x.y` durante MVP.
- `CHANGELOG.md` atualizado a cada release.
- `meta.schema_version` no DB independe da CLI version. Migrations em `cli/plugadvpl/migrations/N_descricao.sql`.
- **Single-source via `hatch-vcs`:** versão derivada da git tag (`v0.1.0` → `pyproject.toml.version` automático). Script de release lê `hatch version` e sincroniza `marketplace.json.version`.

**`cli/pyproject.toml` (2026 best practices):**

```toml
[project]
name = "plugadvpl"
dynamic = ["version"]                       # hatch-vcs preenche
description = "CLI que indexa fontes ADVPL/Protheus em SQLite com FTS5 para análise por LLM"
readme = "README.md"
license-files = ["LICENSE", "NOTICE"]       # PEP 639
authors = [{ name = "<owner>", email = "<owner>@example.com" }]
requires-python = ">=3.11"
keywords = ["advpl", "tlpp", "protheus", "totvs", "claude-code", "sqlite"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Topic :: Software Development :: Libraries",
]
dependencies = [
    "typer >=0.15",
    "rich >=13.7",
    "chardet >=5.0",
    "psutil >=5.9",
]

[project.urls]
Homepage = "https://github.com/<owner>/plugadvpl"
Issues = "https://github.com/<owner>/plugadvpl/issues"
Source = "https://github.com/<owner>/plugadvpl"
Changelog = "https://github.com/<owner>/plugadvpl/blob/main/CHANGELOG.md"

[project.scripts]
plugadvpl = "plugadvpl.cli:main"

# PEP 735 — dependency groups (não optional-dependencies)
[dependency-groups]
dev = [
    "pytest >=8.0",
    "pytest-benchmark >=5.0",
    "syrupy >=4.0",
    "ruff >=0.6",
    "mypy >=1.10",
]

[build-system]
requires = ["hatchling", "hatch-vcs"]
build-backend = "hatchling.build"

[tool.hatch.version]
source = "vcs"

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "C4", "SIM"]

[tool.mypy]
strict = true
python_version = "3.11"
```

**Por que essas escolhas:**
- `hatchling` + `hatch-vcs`: padrão recomendado pelo PyPA em 2026, zero-config.
- `[dependency-groups]` (PEP 735, aceito out/2024): forma oficial de declarar dev deps. uv tem suporte nativo.
- `typer` para CLI: type-hint driven, build em cima de Click, `--format` aceita Enum direto.
- `rich` para progress + tabelas (stderr); stdout puro fica para JSON.
- `ruff` (lint+format) **e** `mypy` (type-check): ruff não substitui mypy. Ambos no CI.
- Wheel pure-Python `py3-none-any.whl` — sem C extensions, instalação rápida em qualquer OS.

### 12.8 Comandos dev (Makefile)

```makefile
.PHONY: test test-fast bench lint validate ingest-local

test: ; pytest cli/tests/unit cli/tests/integration -v
test-fast: ; pytest cli/tests/unit -v -x
bench: ; pytest cli/tests/bench --benchmark-only
lint: ; ruff check cli && python scripts/validate_plugin.py
validate: lint test bench
ingest-local: ; uvx --from . plugadvpl ingest $$PLUGADVPL_E2E_FONTES_DIR --workers 8
```

## 13. Fluxos canônicos

### Cenário 1 — "explique a função FATA050"

```
Plug-OFF: Read FATA050.prw → 3.000 linhas → ~12.000 tokens

Plug-ON:
  plugadvpl arch FATA050.prw          → ~200 tokens
  plugadvpl callers FATA050           → ~50 tokens
  plugadvpl callees FATA050           → ~80 tokens
  (decide ler só linhas 234–280)
  Read FATA050.prw#L234-280           → ~400 tokens
  TOTAL: ~730 tokens  (~16× menos)
```

### Cenário 2 — "se eu mudar MV_LOCALIZA, o que quebra?"

```
plugadvpl param MV_LOCALIZA           → 47 ocorrências, 23 arquivos
advpl-impact-analyzer cruza com chamadas_funcao
TOKENS: ~800 (vs. 23 Reads = ~80k)
```

### Cenário 3 — "crie um PE para validar item de pedido"

```
advpl-code-generator:
  plugadvpl pe MT100LOK               → pattern PARAMIXB
  plugadvpl find file 'MT*LOK*.prw'   → exemplos no cliente
  plugadvpl arch <melhor exemplo>     → estrutura
  Lê só o exemplo escolhido           → ~500 tokens
  Gera novo PE seguindo padrão
  plugadvpl lint <novo>               → 0 findings ✓
  Grava em cp1252
```

### Cenário 4 — projeto não indexado

```
hook session-start detecta .prw, .plugadvpl ausente
→ "Projeto ADVPL detectado (847 fontes). Execute:
   /plugadvpl:init
   /plugadvpl:ingest  (~3–5 min)"
Claude NÃO indexa sozinho. Usuário aciona.
```

## 13.5 Ambientes restritos (Windows corporativo, sem internet)

Protheus é majoritariamente Windows corporativo com proxy, antivírus agressivo e PowerShell restrito. O plugin precisa funcionar nesses cenários.

**Casos cobertos:**

| Cenário | Solução |
|---|---|
| `uv` não instalado | Documentação aponta `winget install astral-sh.uv` ou `irm https://astral.sh/uv/install.ps1 \| iex`. `plugadvpl doctor --env` detecta e instrui |
| Sem internet (PyPI bloqueado) | `uv tool install plugadvpl==<v>` em máquina com internet → exporta wheel via `uv build` → cliente final instala localmente: `uv tool install /path/to/plugadvpl-0.1.0-py3-none-any.whl` |
| Proxy corporativo | `uv` respeita `HTTPS_PROXY` env var. Doc cita configuração |
| Antivírus bloqueando `.plugadvpl/index.db` | `doctor --env` testa locking_mode; recomenda exceção no AV para a pasta |
| PowerShell execution policy restrita | Hook `session-start` usa `.cmd` no Windows (não `.ps1`) por compatibilidade |
| WSL/Cygwin paths | CLI normaliza paths via `pathlib.PurePosixPath` ao escrever no DB (relpath sempre forward slash) |

**Comando dedicado:** `plugadvpl doctor --env` faz check completo de ambiente (uv presente, PyPI alcançável, AV ativo, WAL funcionando, encoding do terminal, locale) e dá instrução acionável para cada falha.

## 13.6 Segurança e privacidade

O índice contém **nomes de tabelas, regras de negócio, endpoints, SQL e potencialmente credenciais literais** que aparecem no código. Tratamento adequado:

| Item | Política |
|---|---|
| `.gitignore` default | `init` adiciona `.plugadvpl/` ao `.gitignore` automaticamente (se não houver) |
| Detecção de DB versionado | `doctor` alerta se `.plugadvpl/index.db` está rastreado pelo git e sugere `git rm --cached + .gitignore` |
| Indexação metadata-only | Flag `--no-content` em `ingest`: indexa nomes/calls/tables/MV_ mas **não armazena `content` em `fonte_chunks`**. Útil para auditoria sem expor IP do cliente |
| Redação opcional | `ingest --redact-secrets`: regex detecta URLs com `user:pass@`, tokens hex >40 chars, `cKey := "..."` típicos e substitui por `[REDACTED]` no snippet |
| Reporte de vulnerabilidades | `SECURITY.md` na raiz com contato e SLA |
| Logs do CLI | Default não loga `content` — só metadados. `--verbose` exige confirmação interativa para projetos grandes |

## 14. Critérios de aceitação do MVP (v0.1.0)

- [ ] `uvx --from plugadvpl==0.1.0 plugadvpl --help` funciona em Windows/Mac/Linux
- [ ] `init` cria `.plugadvpl/index.db` com **22 tabelas físicas** (MVP) + FTS5 external content. Aplica `PRAGMA page_size=8192` + `journal_mode=WAL`. Escreve fragmento idempotente no CLAUDE.md. Adiciona `.plugadvpl/` ao `.gitignore` se não existir
- [ ] `ingest` em fixture local (~2.000 fontes — local-only, ver CONTRIBUTING.md) completa em <60s com `--workers 8`
- [ ] **Parity test:** contagens das **7 tabelas** comparáveis (`fontes`, `fonte_chunks`, `chamadas_funcao`, `parametros_uso`, `perguntas_uso`, `operacoes_escrita`, `sql_embedado`) ficam ≤10% das do baseline interno (mesma base de fontes). **Critério é row count, não comparação coluna-a-coluna** — colunas-delta do plugin (`mtime_ns`, `size_bytes`, `indexed_at`, `namespace`, `tipo_arquivo`) não entram na comparação. `funcao_docs` fica de fora da parity test (baseline não popula, plugin popula — não há referência)
- [ ] FTS5 populada e funcionando (`grep "RecLock" → top-N hits <300ms`)
- [ ] Os 5 smoke tests passam (`arch`, `callers`, `tables`, `param`, `grep`)
- [ ] **Token-budget test (manual):** consulta "explique FATA050" no Claude Code consome ≤2.000 tokens com o plugin ativo (medido via header `x-anthropic-output-tokens` ou contagem manual de chamadas). Sem o plugin, a mesma consulta consome >10.000 tokens. Razão alvo ≥5×.
- [ ] Lint detecta corretamente as **13 regras single-file (regex)** em fixtures sintéticas (precisão ≥90%, recall ≥80%). As 11 regras cross-file/semantic ficam cadastradas em `lint_rules` mas não disparam findings no MVP (deferidas para v0.2)
- [ ] Plugin instalável via `/plugin marketplace add <repo>` e funciona end-to-end
- [ ] As **23 skills** (13 de comando + 10 de conhecimento) + 4 agents + 1 hook estão presentes e validados. `validate_plugin.py` confere contagem
- [ ] `grep` funciona nos 3 modos (`--fts`, `--literal`, `--identifier`) com fixture testando `SA1->A1_COD`, `%xfilial%`, `U_FATA050`, `::New`, `PARAMIXB[1]`
- [ ] `reindex` mantém FTS5 consistente após 3× reindex do mesmo arquivo (teste de idempotência)
- [ ] `status --check-stale` detecta stale por (a) mtime/size diferente E (b) parser_version/lookup_bundle_hash diferente
- [ ] CI passa em todas as combinações da matriz (3 OS × 3 Python)
- [ ] PyPI publica `plugadvpl 0.1.0` automaticamente em push da tag `v0.1.0`
- [ ] README cobre instalação, uso básico, troubleshooting, contribuição
- [ ] LICENSE (MIT), NOTICE (créditos), CONTRIBUTING.md, CODE_OF_CONDUCT.md, SECURITY.md, CHANGELOG.md presentes

## 15. Roadmap pós-MVP (referencial — fora do escopo desta spec)

- **v0.2.0:** ingest do Universo 2 (Dicionário SX) a partir de CSV exportado da rotina U_DICEXP no Protheus. Popula `tabelas`, `campos`, `indices`, `gatilhos`, `parametros`, `perguntas`, `consultas`, `pastas`, `relacionamentos`, `tabelas_genericas`, `grupos_campo`.
- **v0.3.0:** ingest do Universo 3 (Rastreabilidade). Parser de expressões ADVPL nos campos X3_VALID, X3_INIT, X7_REGRA, X1_VALID, etc. → `expressoes_dicionario` + `rastreabilidade_unificada`. Habilita `plugadvpl impacto <campo>`.
- **v0.4.0:** ingest de `appserver.ini` + `schedule` → `jobs` + `schedules`. Skills adicionais (`advpl-refactoring`, `advpl-debugging`, `advpl-testing-probat`, `advpl-tlpp-modern`).
- **v0.5.0:** opção experimental de embeddings via `sqlite-vec` para queries semânticas avançadas.

## 16. Decisões em aberto

Nenhuma — todas as decisões arquiteturais foram tomadas durante a fase de brainstorm.

## 17. Atribuições

- **Parser de fontes ADVPL:** portado de projeto interno anterior do autor (~750 linhas) — schema e técnicas de ingestão validadas em aproximadamente 2.000 fontes ADVPL.
- **Lookup tables embarcadas:** funções nativas, funções restritas (195), regras de code-review (24), macros SQL, módulos ERP (8), PEs catalogados — extraídas com crédito de `advpl-specialist` (autor: Thalys Augusto, MIT) em `D:/IA/Projetos/advpl-specialist-main`.
- **Skills temáticas:** estilo/estrutura inspirados em `advpl-specialist`, conteúdo original adaptado ao escopo deste plugin.
- **Revisão crítica externa (2026-05-11):** revisão de IA independente trouxe 30+ pontos de atenção em P0/P1/P2 — aceitos 25, modificados 2 (P0-1, P0-4), mantidos sob justificativa 3 (P1-1 escopo, P0-1 PK, P2-4 paths). Registrados em `2026-05-11-plugadvpl-design-pontos-atencao.md`. Mudanças aplicadas: caminho_relativo UNIQUE, linha_inicio/linha_fim em fonte_chunks, pin uvx --from, encoding preserve-by-default, skills/ em vez de commands/, hooks.json literal, parser_version/lookup_bundle_hash invalidação incremental, COLLATE NOCASE, FTS5 external content, grep 3 modos, output budget, reindex transacional, release em 2 etapas, seções de ambientes restritos e segurança, remoção das 17 tabelas vazias do MVP.

- **Revisão técnica de best practices 2026 (2026-05-11):** 4 sub-agents pesquisaram independentemente docs oficiais (sqlite.org, code.claude.com, docs.astral.sh/uv, packaging.python.org) e blogs técnicos respeitados (phiresky, Simon Willison, Hynek). Aplicadas 13 correções de erros confirmados:
  - `synchronous=FULL` ao final era exagero — manter NORMAL (WAL é durável)
  - Tokenizer FTS5 `unicode61` quebrava `A1_COD`/`%xfilial%` — adicionar `tokenchars '_-'` + segundo índice `trigram`
  - `INSERT OR REPLACE` destrutivo com FTS5 external content — substituir por `INSERT ... ON CONFLICT DO UPDATE`
  - `locking_mode=EXCLUSIVE` matava WAL — remover, usar `busy_timeout=5000`
  - WAL não funciona em network share (SMB/CIFS) — detectar UNC e fallback para `journal_mode=DELETE`
  - Batch 50 arquivos pequeno — subir para 500–1000 chunks
  - PRAGMAs faltando: `journal_size_limit`, `wal_checkpoint(TRUNCATE)`, `PRAGMA optimize` antes do close
  - ProcessPool desperdício para parser <50ms/arquivo — usar **ThreadPool** default, ProcessPool só >2000 arquivos
  - Strip-first: mini-tokenizer ~100 linhas elimina ~80% dos falso-positivos de regex (padrão da indústria, COBOL/ProLeap)
  - Python 3.14 mudou default `fork→spawn` — em Linux/Mac forçar `mp_context=get_context("fork")`
  - PyPI **não** é canal do plugin Claude Code — separados (CLI vai PyPI, plugin vai marketplace via repo)
  - `minClaudeCodeVersion` não existe em plugin.json — workaround via SessionStart check
  - Hook input/output schema corrigido conforme docs oficiais
  + 15 melhorias adicionais: tabela `fonte_tabela` normalizada para "quem usa SA1", `WITHOUT ROWID` em lookups, frontmatter `disable-model-invocation` em skills de comando, `${CLAUDE_PLUGIN_DATA}` para cache cross-version, `uvx pkg@v` sintaxe curta, `[dependency-groups]` PEP 735, `hatch-vcs` single-source versioning, Trusted Publisher OIDC, ruff+mypy ambos, `re` stdlib em vez de `regex` PyPI, etc.
