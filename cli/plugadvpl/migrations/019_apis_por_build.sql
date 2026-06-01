-- v0.20.0 — issue #26: catálogo de disponibilidade de métodos FW*/Ms*/FWBrowse
-- por build Protheus. Denylist: método NÃO catalogado = assume que existe.
-- `chave` sintética ('classe:metodo') é a PK para compatibilidade com
-- seed_lookups (upsert single-column). A janela de disponibilidade é
-- [build_min, build_max] (NULL = sem limite). Populada via lookups/apis_por_build.json.
CREATE TABLE IF NOT EXISTS apis_por_build (
    chave     TEXT PRIMARY KEY,   -- 'FWMarkBrowse:SetBlkBackColor'
    classe    TEXT NOT NULL,      -- 'FWMarkBrowse', 'FWBrowse', 'MsDialog'
    metodo    TEXT NOT NULL,      -- 'SetBlkBackColor'
    build_min TEXT,               -- 1ª build onde existe (NULL = sem limite inferior)
    build_max TEXT,               -- última build onde existe (NULL = ainda existe)
    fonte     TEXT,               -- 'TDN @since', 'observação de campo'
    nota      TEXT                -- alternativa/workaround
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_apis_classe ON apis_por_build(classe);
