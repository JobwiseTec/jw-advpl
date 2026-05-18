-- v0.4.6 (C): coluna op_dynamic em execauto_calls.
-- Distingue "sem op_code" (sem args) de "op_code via variavel/expressao"
-- (ha args mas nenhum eh literal numerico). Permite filtro --op-dynamic.

ALTER TABLE execauto_calls ADD COLUMN op_dynamic INTEGER NOT NULL DEFAULT 0;
