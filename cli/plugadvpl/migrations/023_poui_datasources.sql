-- Migration 023 — datasources REST do frontend POUI (chamadas HttpClient).
-- Cruzadas com rest_endpoints (backend TLPP) via poui_bridge.
CREATE TABLE IF NOT EXISTS poui_datasources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    caminho     TEXT NOT NULL,           -- .ts onde a chamada está (absoluto)
    linha       INTEGER NOT NULL DEFAULT 0,
    verbo       TEXT NOT NULL,           -- GET|POST|PUT|DELETE|PATCH
    url_raw     TEXT NOT NULL DEFAULT '',
    path_norm   TEXT NOT NULL DEFAULT ''  -- path estático casável com rest_endpoints.path
);
CREATE INDEX IF NOT EXISTS idx_poui_ds_path ON poui_datasources(path_norm);
