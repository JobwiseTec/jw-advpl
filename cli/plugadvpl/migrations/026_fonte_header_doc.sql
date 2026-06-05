-- v0.23.0 (#63) — header doc declarativo extraído do topo do fonte.
-- Bloco de metadados que muitos fontes Protheus trazem no cabeçalho
-- (Programa/Autor/Data/Descrição/Doc.Origem/Solicitante/Uso/Obs), distinto do
-- Protheus.doc. Populada no ingest por parsing/header.py (no-op quando ausente).
-- Cobertura varia por convenção do projeto (~0% a ~40% dos fontes).
CREATE TABLE IF NOT EXISTS fonte_header_doc (
    arquivo       TEXT PRIMARY KEY,   -- basename do fonte (== fontes.arquivo)
    programa      TEXT,               -- nome declarado (pode != arquivo)
    autor         TEXT,
    data_criacao  TEXT,               -- string crua (formatos variados dd/mm/aaaa)
    descricao     TEXT,               -- Descrição/Objetivo
    doc_origem    TEXT,               -- Doc.Origem / GAP / Chamado
    solicitante   TEXT,
    uso           TEXT,               -- empresa/projeto onde roda
    observacao    TEXT,               -- costuma conter histórico de versões
    raw_header    TEXT                -- bloco completo, fallback
);
