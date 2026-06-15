-- 033 — Sub-projeto 1 (spec SX completo): colunas faltantes de SX2/SX3/SX9.
-- Ver docs/superpowers/specs/2026-06-15-sx-completo-chave-indice-design.md.
-- Habilitam: guarda de chave única (X2_UNICO), pais/filhos com filial (SX9),
-- e enriquecem browse/relação (SX3). DEFAULT '' = ALTER rápido (constante).

-- SX2 (tabelas): chave única + modos de compartilhamento
ALTER TABLE tabelas ADD COLUMN unico       TEXT DEFAULT '';  -- X2_UNICO
ALTER TABLE tabelas ADD COLUMN modo_unico  TEXT DEFAULT '';  -- X2_MODOUN
ALTER TABLE tabelas ADD COLUMN modo_emp    TEXT DEFAULT '';  -- X2_MODOEMP

-- SX3 (campos): ordem de browse, init de browse, e X3_RELACAO (distinto de X3_INIT)
ALTER TABLE campos ADD COLUMN ordem    TEXT DEFAULT '';  -- X3_ORDEM
ALTER TABLE campos ADD COLUMN inibrw   TEXT DEFAULT '';  -- X3_INIBRW
ALTER TABLE campos ADD COLUMN relacao  TEXT DEFAULT '';  -- X3_RELACAO

-- SX9 (relacionamentos): filial + chave estrangeira
ALTER TABLE relacionamentos ADD COLUMN usa_filial        TEXT DEFAULT '';  -- X9_USEFIL
ALTER TABLE relacionamentos ADD COLUMN vincula_filial    TEXT DEFAULT '';  -- X9_VINFIL
ALTER TABLE relacionamentos ADD COLUMN chave_estrangeira TEXT DEFAULT '';  -- X9_CHVFOR
