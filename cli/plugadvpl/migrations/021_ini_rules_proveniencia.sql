-- Migration 021 — procedência + verificação no catálogo ini_rules.
--
-- A base de 487 regras (migration 011) foi gerada em lote sem trilha de
-- procedência estruturada; o `ini-audit` chegou a "inventar tag" (flagar
-- chave/valor que não procede). Estes campos dão rastreabilidade e permitem
-- não-flagar chaves opcionais-de-feature:
--
--   fonte         — URL/pageId TDN estruturado (antes vivia solto no fix_guidance)
--   verificado    — 0=não-curada (default), 1=validada contra TDN/realidade
--   condicional   — 1=chave opcional-de-feature ([Mail]/[FTP]/...); nunca vira
--                   finding de "missing" (a feature pode simplesmente não ser usada)
--   default_totvs — valor default documentado pela TOTVS (contexto no relatório)
--   versao_min    — versão Protheus mínima onde a chave existe (futuro: build-check)
--
-- Populados via lookups/ini_rules.json (seed_lookups). Colunas com default
-- seguro: INIs já auditados não quebram.
ALTER TABLE ini_rules ADD COLUMN fonte         TEXT    DEFAULT '';
ALTER TABLE ini_rules ADD COLUMN verificado    INTEGER DEFAULT 0;
ALTER TABLE ini_rules ADD COLUMN condicional   INTEGER DEFAULT 0;
ALTER TABLE ini_rules ADD COLUMN default_totvs TEXT    DEFAULT '';
ALTER TABLE ini_rules ADD COLUMN versao_min    TEXT    DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_ini_rules_verificado  ON ini_rules(verificado);
CREATE INDEX IF NOT EXISTS idx_ini_rules_condicional ON ini_rules(condicional);
