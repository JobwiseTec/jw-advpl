-- Migration 011 — Auditor de INI Protheus.
--
-- Adiciona 6 tabelas + 2 lookups pra suportar `plugadvpl ini-audit`:
--   1. ini_files            — 1 row por INI ingerido (path, tipo, role, hash, mtime)
--   2. ini_sections         — 1 row por seção (commented, comentários, linhas)
--   3. ini_keys             — 1 row por par chave=valor (com comments inline/above)
--   4. ini_audit_findings   — output da auditoria (regra_id, severidade, snippet)
--   5. ini_rules            — catálogo de regras (vem de lookups/ini_rules.json)
--   6. ini_roles            — catálogo de roles de INI (vem de lookups/ini_roles.json)
--
-- INIs típicos auditados:
--   - appserver*.ini   (com 14 roles possíveis: broker_http, slave_rest, tss, ...)
--   - dbaccess*.ini    (master, slave, standalone)
--   - smartclient*.ini
--   - tss*.ini
--   - broker.ini (HTTP/SOAP/REST)
--
-- Não substitui `ingest` (fontes ADVPL) — é uma trilha paralela. INIs são
-- indexados sob demanda quando o usuário chama `ini-audit <path>`; auto-discover
-- via glob (`appserver*.ini`, `dbaccess*.ini`, ...) quando sem args.

-- =============================================================================
-- ini_files: cada INI ingerido (PK = caminho absoluto)
-- =============================================================================
CREATE TABLE IF NOT EXISTS ini_files (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    caminho       TEXT NOT NULL UNIQUE,         -- absolute path
    arquivo       TEXT NOT NULL,                 -- basename (paridade com `fontes`)
    tipo          TEXT NOT NULL,                 -- appserver|dbaccess|smartclient|tss|broker|custom
    role          TEXT DEFAULT '',               -- 14 roles: broker_http|slave|slave_rest|...
    encoding      TEXT DEFAULT '',               -- cp1252|utf-8|utf-8-bom (detectado via chardet)
    hash          TEXT DEFAULT '',               -- sha256 do conteúdo bruto (cache de re-ingest)
    size_bytes    INTEGER NOT NULL DEFAULT 0,
    mtime_ns      INTEGER NOT NULL DEFAULT 0,
    indexed_at    TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ini_files_arquivo ON ini_files(arquivo);
CREATE INDEX IF NOT EXISTS idx_ini_files_tipo    ON ini_files(tipo);
CREATE INDEX IF NOT EXISTS idx_ini_files_role    ON ini_files(role);

-- =============================================================================
-- ini_sections: seções dentro de cada INI
-- =============================================================================
-- name_raw       — exatamente como aparece no arquivo (preserva case)
-- name_norm      — lowercase pra merge case-insensitive ([General] == [general])
-- commented      — 1 se `;[NomeSecao]` (seção inativa; chaves abaixo também inativas)
-- comment_text   — comentários acima da declaração da seção (para detectar tip
--                  intencional, ex: "; desativado por causa X")
CREATE TABLE IF NOT EXISTS ini_sections (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id       INTEGER NOT NULL REFERENCES ini_files(id) ON DELETE CASCADE,
    name_raw      TEXT NOT NULL,
    name_norm     TEXT NOT NULL,
    commented     INTEGER NOT NULL DEFAULT 0,
    linha_inicio  INTEGER NOT NULL,
    linha_fim     INTEGER NOT NULL,
    comment_text  TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ini_sections_file     ON ini_sections(file_id);
CREATE INDEX IF NOT EXISTS idx_ini_sections_namenorm ON ini_sections(name_norm);

-- =============================================================================
-- ini_keys: pares chave=valor
-- =============================================================================
-- comment_inline — comentário na MESMA linha após `;` (ex: `Port=4301 ; padrão`)
-- comment_above  — comentários nas linhas IMEDIATAMENTE acima da chave
--                  (usado pra detectar `ok_with_note` quando cliente documentou
--                   justificativa pra um valor não-recomendado)
CREATE TABLE IF NOT EXISTS ini_keys (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id        INTEGER NOT NULL REFERENCES ini_files(id) ON DELETE CASCADE,
    section_id     INTEGER NOT NULL REFERENCES ini_sections(id) ON DELETE CASCADE,
    key_name       TEXT NOT NULL,                -- preserva case
    key_norm       TEXT NOT NULL,                -- lowercase pra lookup
    value          TEXT DEFAULT '',
    linha          INTEGER NOT NULL,
    comment_inline TEXT DEFAULT '',
    comment_above  TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_ini_keys_file_section ON ini_keys(file_id, section_id);
CREATE INDEX IF NOT EXISTS idx_ini_keys_keynorm      ON ini_keys(key_norm);

-- =============================================================================
-- ini_audit_findings: output do `ini-audit`
-- =============================================================================
-- Espelha o estilo de `lint_findings` (mesma forma: arquivo/funcao/linha/regra_id/sev).
-- status:
--   active        — finding em aberto
--   ok_with_note  — valor não-default mas cliente documentou justificativa em comment_above
--   suppressed    — usuário ignorou via flag/config (futuro)
CREATE TABLE IF NOT EXISTS ini_audit_findings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id         INTEGER NOT NULL REFERENCES ini_files(id) ON DELETE CASCADE,
    section_raw     TEXT DEFAULT '',
    key_name        TEXT DEFAULT '',
    regra_id        TEXT NOT NULL,                -- INI-001, SEC-001, etc.
    severidade      TEXT NOT NULL,                -- critical|warning|info
    snippet         TEXT DEFAULT '',              -- a linha problemática (<=200 chars)
    sugestao_fix    TEXT DEFAULT '',
    linha           INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'active'
);
CREATE INDEX IF NOT EXISTS idx_ini_findings_file       ON ini_audit_findings(file_id);
CREATE INDEX IF NOT EXISTS idx_ini_findings_regra      ON ini_audit_findings(regra_id);
CREATE INDEX IF NOT EXISTS idx_ini_findings_severidade ON ini_audit_findings(severidade);
CREATE INDEX IF NOT EXISTS idx_ini_findings_status     ON ini_audit_findings(status);

-- =============================================================================
-- ini_rules: catálogo (seed via lookups/ini_rules.json)
-- =============================================================================
-- section_glob   — pattern da seção alvo. Suporta:
--                    [Geral]                  — seção exata
--                    [<DRIVER>/<env>]         — wildcard (ex: MSSQL/protheus_dev)
--                    [environment]            — placeholder qualquer seção de environment
--                    *                        — qualquer
-- expected       — valor recomendado (texto livre; lógica de match em parsing/ini_audit.py)
-- applies_to_role — filtra a regra. Vazio = todos os roles.
-- detection_kind — value_eq | value_neq | value_in | key_missing | key_present | regex
CREATE TABLE IF NOT EXISTS ini_rules (
    regra_id        TEXT PRIMARY KEY,
    section_glob    TEXT NOT NULL,
    key_name        TEXT NOT NULL,
    expected        TEXT DEFAULT '',
    severidade      TEXT NOT NULL,
    detection_kind  TEXT NOT NULL DEFAULT 'value_eq',
    descricao       TEXT NOT NULL,
    fix_guidance    TEXT DEFAULT '',
    applies_to_tipo TEXT NOT NULL DEFAULT '',    -- appserver|broker|dbaccess|tss (vazio = todos)
    applies_to_role TEXT DEFAULT '',              -- filtro fino dentro do tipo (vazio = todos os roles)
    status          TEXT DEFAULT 'active'
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_ini_rules_severidade ON ini_rules(severidade);
CREATE INDEX IF NOT EXISTS idx_ini_rules_tipo       ON ini_rules(applies_to_tipo);
CREATE INDEX IF NOT EXISTS idx_ini_rules_role       ON ini_rules(applies_to_role);

-- =============================================================================
-- ini_roles: catálogo de roles (seed via lookups/ini_roles.json)
-- =============================================================================
-- 14 roles documentados no env_manager:
--   appserver:       broker_http, broker_soap, broker_rest, slave, slave_ws,
--                    slave_rest, rest_server, job_server, standalone,
--                    standalone_multi_env
--   tss:             tss
--   dbaccess:        dbaccess_master, dbaccess_slave, dbaccess_standalone
--
-- detection_kind:
--   section_match — role detectado quando uma seção específica existe
--                   (ex: [DBAccess] => standalone; [Broker]+[HTTPV11] => broker_http)
--   key_value     — role detectado por uma chave=valor específica
--                   (ex: [General] FNAME=master => dbaccess_master)
CREATE TABLE IF NOT EXISTS ini_roles (
    role_id           TEXT PRIMARY KEY,
    tipo_ini          TEXT NOT NULL,             -- appserver|tss|dbaccess|smartclient|broker
    descricao         TEXT NOT NULL,
    detection_kind    TEXT NOT NULL,
    detection_pattern TEXT NOT NULL,             -- JSON com regras de detecção
    prioridade        INTEGER NOT NULL DEFAULT 100
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_ini_roles_tipo ON ini_roles(tipo_ini);
