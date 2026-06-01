-- v0.20.0 — issue #27: dicionário de semântica contextual de campos SX.
-- Alguns campos têm significado não-óbvio que muda conforme um discriminador
-- (TIPO/PODER3/STATUS). `chave` sintética ('campo:discriminador') é a PK para
-- compatibilidade com seed_lookups. Populada via lookups/campos_semantica.json
-- (só semântica PADRÃO Protheus — sem termo de negócio de cliente).
CREATE TABLE IF NOT EXISTS campos_semantica (
    chave         TEXT PRIMARY KEY,   -- 'B6_CLIFOR:B6_PODER3=R'
    tabela        TEXT NOT NULL,      -- 'SB6'
    campo         TEXT NOT NULL,      -- 'B6_CLIFOR'
    discriminador TEXT,               -- 'B6_PODER3=R' ('' = sem discriminador)
    semantica     TEXT NOT NULL,      -- significado contextual
    fonte         TEXT
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_semantica_campo ON campos_semantica(campo);
