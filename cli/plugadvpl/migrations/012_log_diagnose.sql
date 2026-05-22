-- Migration 012 — Monitor de log Protheus (console.log / error.log / profile.log).
--
-- Adiciona 6 tabelas + 3 lookups pra suportar `plugadvpl log-diagnose`:
--   1. log_files        — 1 row por log ingerido (path, tipo, metadata header)
--   2. log_events       — 1 row por evento tokenizado (Stage 1)
--   3. log_findings     — output (Stage 2: match contra log_rules + correction tip)
--   4. log_rules        — catálogo de patterns (vem de lookups/log_rules.json)
--   5. log_tips         — correction tips com URL TDN (vem de log_tips.json)
--   6. log_categories   — 12 categorias documentadas + fallback tip
--
-- Logs típicos auditados:
--   - console.log        AppServer (formato ISO + thread_id)
--   - error.log          THREAD ERROR PT-BR com call stack
--   - profile.log        Trace de profile
--   - compila.log        Build log com [SEVERITY] brackets
--
-- Pipeline em 2 estágios (idem env_manager.parse_log):
--   STAGE 1 (top-down): tokenize_events() → log_events
--   STAGE 2 (bottom-up): match_event() com short-circuit → log_findings
-- Reverse traversal espelha o comportamento natural de dev olhando log (erros
-- MAIS RECENTES primeiro).

-- =============================================================================
-- log_files: cada log ingerido (PK = caminho absoluto)
-- =============================================================================
CREATE TABLE IF NOT EXISTS log_files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    caminho         TEXT NOT NULL UNIQUE,        -- absolute path
    arquivo         TEXT NOT NULL,                -- basename
    tipo            TEXT NOT NULL,                -- console|error|profile|compile|outro
    hash            TEXT DEFAULT '',              -- sha256 do conteúdo (cache invalidation)
    size_bytes      INTEGER NOT NULL DEFAULT 0,
    mtime_ns        INTEGER NOT NULL DEFAULT 0,
    encoding        TEXT DEFAULT '',              -- detectado (utf-8|cp1252|...)
    total_events    INTEGER NOT NULL DEFAULT 0,
    first_ts        TEXT DEFAULT '',              -- ISO 8601 do primeiro evento com timestamp
    last_ts         TEXT DEFAULT '',              -- ISO do último (usado em --since)
    -- metadata extraída do header (error.log/profile.log têm [key: value] no topo)
    environment     TEXT DEFAULT '',
    appserver       TEXT DEFAULT '',
    build           TEXT DEFAULT '',
    rpo_version     TEXT DEFAULT '',
    -- metadata bruto + extras não-padrão (JSON serializado)
    metadata_json   TEXT DEFAULT '{}',
    -- métricas (do scan_metrics: memória, start time)
    memory_total_mb TEXT DEFAULT '',
    memory_used_mb  TEXT DEFAULT '',
    memory_free_mb  TEXT DEFAULT '',
    start_time_s    TEXT DEFAULT '',
    indexed_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_log_files_arquivo ON log_files(arquivo);
CREATE INDEX IF NOT EXISTS idx_log_files_tipo    ON log_files(tipo);

-- =============================================================================
-- log_events: eventos tokenizados (Stage 1)
-- =============================================================================
-- timestamp salvo como ISO TEXT (SQLite não tem DATETIME nativo). Sempre UTC-naive
-- ou TZ-aware uniforme dentro do mesmo log (mistura é normalizada no parser).
CREATE TABLE IF NOT EXISTS log_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id        INTEGER NOT NULL REFERENCES log_files(id) ON DELETE CASCADE,
    line_number    INTEGER NOT NULL,
    timestamp      TEXT DEFAULT '',
    thread_id      TEXT DEFAULT '',
    header_line    TEXT DEFAULT '',
    body           TEXT DEFAULT ''                -- linhas subsequentes (até próximo header)
);
CREATE INDEX IF NOT EXISTS idx_log_events_file    ON log_events(file_id);
CREATE INDEX IF NOT EXISTS idx_log_events_ts      ON log_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_log_events_thread  ON log_events(thread_id);

-- =============================================================================
-- log_findings: output do `log-diagnose` (Stage 2)
-- =============================================================================
CREATE TABLE IF NOT EXISTS log_findings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id         INTEGER NOT NULL REFERENCES log_files(id) ON DELETE CASCADE,
    event_id        INTEGER REFERENCES log_events(id) ON DELETE CASCADE,
    line_number     INTEGER NOT NULL DEFAULT 0,
    timestamp       TEXT DEFAULT '',
    thread_id       TEXT DEFAULT '',
    severity        TEXT NOT NULL,                -- critical|warning|info
    category        TEXT NOT NULL,                -- database|thread_error|rpo|...
    rule_id         TEXT NOT NULL,                -- LOG-DB-ORA, LOG-RPO-CHECKAUTH, etc.
    message         TEXT DEFAULT '',
    snippet         TEXT DEFAULT '',              -- até 1000 chars de contexto (header+body)
    correction_tip  TEXT DEFAULT '',
    tdn_url         TEXT DEFAULT '',
    username        TEXT DEFAULT '',
    computer_name   TEXT DEFAULT '',
    ora_code        TEXT DEFAULT '',              -- ORA-xxx capturado quando aplicável
    status          TEXT DEFAULT 'active'         -- active|suppressed (futuro)
);
CREATE INDEX IF NOT EXISTS idx_log_findings_file       ON log_findings(file_id);
CREATE INDEX IF NOT EXISTS idx_log_findings_severity   ON log_findings(severity);
CREATE INDEX IF NOT EXISTS idx_log_findings_category   ON log_findings(category);
CREATE INDEX IF NOT EXISTS idx_log_findings_rule       ON log_findings(rule_id);
CREATE INDEX IF NOT EXISTS idx_log_findings_ts         ON log_findings(timestamp);

-- =============================================================================
-- log_rules: catálogo (seed via lookups/log_rules.json)
-- =============================================================================
-- pattern             — regex (Python flavor; aplicado com re.IGNORECASE quando case_insensitive=1)
-- message_template    — string com placeholders {1}, {2} pros capture groups
--                       (ex: "Thread Error na rotina {2} (Thread {1})")
-- case_insensitive    — 1 se a regex deve compilar com re.IGNORECASE
-- multiline           — 1 se a regex precisa de re.MULTILINE (^$ por linha)
CREATE TABLE IF NOT EXISTS log_rules (
    rule_id           TEXT PRIMARY KEY,
    category          TEXT NOT NULL,
    severidade        TEXT NOT NULL,               -- critical|warning|info
    pattern           TEXT NOT NULL,
    message_template  TEXT NOT NULL,
    case_insensitive  INTEGER NOT NULL DEFAULT 0,
    multiline         INTEGER NOT NULL DEFAULT 0,
    descricao         TEXT DEFAULT '',
    priority          INTEGER NOT NULL DEFAULT 100,
    status            TEXT DEFAULT 'active'
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_log_rules_category ON log_rules(category);
CREATE INDEX IF NOT EXISTS idx_log_rules_priority ON log_rules(priority);

-- =============================================================================
-- log_tips: correction tips (seed via lookups/log_tips.json)
-- =============================================================================
-- 92+ tips com link pra página TDN oficial TOTVS. Aplicado em match_event() pra
-- enriquecer o finding com sugestão de fix concreta. Match: category bate +
-- pattern casa em message+raw_line.
CREATE TABLE IF NOT EXISTS log_tips (
    tip_id            TEXT PRIMARY KEY,
    category          TEXT NOT NULL,
    pattern           TEXT NOT NULL,
    tip_text          TEXT NOT NULL,
    tdn_url           TEXT DEFAULT '',
    case_insensitive  INTEGER NOT NULL DEFAULT 1,
    priority          INTEGER NOT NULL DEFAULT 100
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_log_tips_category ON log_tips(category);

-- =============================================================================
-- log_categories: catálogo de 12 categorias (seed via lookups/log_categories.json)
-- =============================================================================
CREATE TABLE IF NOT EXISTS log_categories (
    category_id        TEXT PRIMARY KEY,
    descricao          TEXT NOT NULL,
    severity_default   TEXT NOT NULL,             -- severidade típica (info|warning|critical)
    fallback_tip       TEXT DEFAULT '',
    tdn_url            TEXT DEFAULT ''
) WITHOUT ROWID;
