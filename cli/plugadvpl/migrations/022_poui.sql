-- Migration 022 — projetos PO UI (frontend Angular TOTVS).
-- 1 row por package.json com dependência @po-ui/*. Ver ingest_poui.py.
CREATE TABLE IF NOT EXISTS poui_projetos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    caminho         TEXT NOT NULL UNIQUE,          -- path absoluto do package.json
    poui_version    TEXT NOT NULL DEFAULT '',
    poui_major      INTEGER,
    angular_version TEXT NOT NULL DEFAULT '',
    angular_major   INTEGER,
    compativel      INTEGER NOT NULL DEFAULT 1,    -- poui_major == angular_major
    pacotes_json    TEXT NOT NULL DEFAULT '[]',    -- JSON list de @po-ui/*
    hash            TEXT NOT NULL DEFAULT '',       -- sha256 do package.json (cache)
    mtime_ns        INTEGER NOT NULL DEFAULT 0,
    indexed_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_poui_compat ON poui_projetos(compativel);
