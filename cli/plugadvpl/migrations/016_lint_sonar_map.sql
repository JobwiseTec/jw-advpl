-- Migration 016 — adiciona coluna sonar_rules em lint_rules.
--
-- Contexto: a TOTVS publicou um conjunto OFICIAL de regras SonarQube para
-- AdvPL/TLPP (sonar-rules.engpro.totvs.com.br), referenciado pelas skills do
-- repositório oficial totvs/engpro-advpl-tlpp-skills. Mapeamos cada regra do
-- nosso catálogo (lookups/lint_rules.json) para o(s) ID(s) SonarQube oficiais
-- equivalentes — quando existem — para:
--   (a) falar a língua que o mercado já conhece (dev vê "BG1000" e entende),
--   (b) interop/legitimidade SEM dependência (continuamos offline/independentes),
--   (c) ponte de adoção para quem já roda Sonar no CI.
--
-- Formato: JSON array de strings. ID puro = equivalência forte (ex: "BG1000").
-- Prefixo "~" = relação parcial/adjacente (ex: "~CA1000"). Array vazio "[]" =
-- regra exclusiva nossa, sem equivalente Sonar oficial (a maioria — é argumento
-- de venda: cobrimos coisas que nem o Sonar oficial cobre).
--
-- ALTER TABLE ADD COLUMN é não-destrutivo em SQLite (registros existentes
-- recebem o DEFAULT '[]'). seed_lookups() re-popula a coluna no próximo ingest.

ALTER TABLE lint_rules ADD COLUMN sonar_rules TEXT DEFAULT '[]';
