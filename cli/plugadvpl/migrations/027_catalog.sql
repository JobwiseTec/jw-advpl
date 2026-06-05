-- v0.25.0 (#75) — dumps TSV/CSV de tabelas-catálogo (Z*/X*) importados pro índice.
-- Modelo row-JSON (1 linha por registro, colunas em JSON) — schema arbitrário
-- sem ALTER TABLE por dump; query-side agrega em Python (dumps típicos ~N×k).
-- Populadas por `ingest-tsv`, consultadas por `catalog`.
CREATE TABLE IF NOT EXISTS catalog_meta (
    alias         TEXT PRIMARY KEY,   -- nome lógico do dump (--as)
    source_file   TEXT,               -- caminho do arquivo importado
    sx_table      TEXT,               -- tabela SX correlata (se o nome bate; p/ --decode-cbox)
    columns_json  TEXT NOT NULL,      -- lista ordenada de colunas (JSON)
    row_count     INTEGER NOT NULL DEFAULT 0,
    ingested_at   TEXT,
    encoding      TEXT,
    delimiter     TEXT                -- 'tab' | 'csv'
);

CREATE TABLE IF NOT EXISTS catalog_data (
    alias    TEXT NOT NULL,
    row_id   INTEGER NOT NULL,        -- ordinal 1..N na ordem do dump
    row_json TEXT NOT NULL,           -- {coluna: valor}
    PRIMARY KEY (alias, row_id)
);

CREATE INDEX IF NOT EXISTS idx_catalog_data_alias ON catalog_data(alias);
