-- v0.6.0 (Universo 4 / Feature B): tabela cache fonte_metrics +
-- placeholder pra backfill fontes.modulo (popula em ingest, nao via SQL).
--
-- fonte_metrics: 1 row por funcao indexada, com metricas pre-computadas
-- (cc/nesting/loc/fan-out). Cache invalidado via DELETE CASCADE quando
-- fonte_chunks remove a funcao (re-ingest do arquivo).

CREATE TABLE IF NOT EXISTS fonte_metrics (
  id            TEXT PRIMARY KEY,                -- = fonte_chunks.id
  arquivo       TEXT NOT NULL,
  funcao        TEXT,
  linha_inicio  INTEGER NOT NULL,
  linha_fim     INTEGER NOT NULL,
  loc           INTEGER NOT NULL,                -- linha_fim - linha_inicio + 1
  cc            INTEGER NOT NULL DEFAULT 1,      -- complexidade ciclomatica McCabe
  nesting       INTEGER NOT NULL DEFAULT 0,      -- max depth de blocos
  n_calls_out   INTEGER NOT NULL DEFAULT 0,      -- fan-out (chamadas que faz)
  params_count  INTEGER NOT NULL DEFAULT 0,      -- N de parametros da assinatura
  has_doc       INTEGER NOT NULL DEFAULT 0,      -- 1 se tem Protheus.doc
  FOREIGN KEY (id) REFERENCES fonte_chunks(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_metrics_arquivo ON fonte_metrics(arquivo);
CREATE INDEX IF NOT EXISTS idx_metrics_cc      ON fonte_metrics(cc DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_loc     ON fonte_metrics(loc DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_funcao  ON fonte_metrics(funcao COLLATE NOCASE);
