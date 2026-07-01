-- Migration 034 — U6 (apply-patch): PATCHES_APPLIED
--
-- Registro de patches .PTM aplicados via `plugadvpl apply-patch` (issue #4).
-- Base: docs/superpowers/specs/2026-06-16-u6-apply-patch-design.md (decisao D1).
--
-- Grava UM registro por .PTM (nao por batch). Isso resolve o "Quirk 2" descoberto
-- na Fase 0: o script de referencia aplica a batch inteira num unico `advpls cli`
-- e, se um patch do meio falha, os anteriores ja entraram no RPO mas nenhum e
-- registrado -> re-run reaplica. Aqui cada patch bem-sucedido e gravado na hora.
--
-- A idempotencia vem do UNIQUE(env, ptm_hash): reaplicar o mesmo .PTM no mesmo
-- environment vira skip (detectado ANTES de invocar o advpls).

-- =============================================================================
-- PATCHES_APPLIED — historico de aplicacao por .PTM por environment
-- =============================================================================
CREATE TABLE IF NOT EXISTS patches_applied (
    id            INTEGER PRIMARY KEY,
    env           TEXT NOT NULL,            -- environment do AppServer (ex: protheus_cmp)
    build         TEXT DEFAULT '',          -- build do AppServer detectado no log
    ptm_name      TEXT NOT NULL,            -- basename do .PTM
    ptm_hash      TEXT NOT NULL,            -- sha256 do conteudo do .PTM (idempotencia)
    status        TEXT NOT NULL,            -- applied | partial (parseado do log)
    applied_at    TEXT NOT NULL,            -- ISO-8601 (UTC) do momento da aplicacao
    batch_ts      TEXT DEFAULT '',          -- YYYYMMDD_HHMMSS da batch (agrupa p/ rollback cascata)
    log_path      TEXT DEFAULT '',          -- caminho do log do advpls daquele patch
    backup_path   TEXT DEFAULT '',          -- RPO backup pre-patch (vazio se backup nao disponivel)
    detail        TEXT DEFAULT ''           -- nota (ex: "Only new sources applied")
);

-- Idempotencia: mesmo .PTM no mesmo env = skip. INSERT usa OR IGNORE contra este indice.
CREATE UNIQUE INDEX IF NOT EXISTS ux_patches_env_hash ON patches_applied(env, ptm_hash);

-- Consultas frequentes: --list-applied por env, e rollback por batch.
CREATE INDEX IF NOT EXISTS idx_patches_env ON patches_applied(env);
CREATE INDEX IF NOT EXISTS idx_patches_batch ON patches_applied(batch_ts);
