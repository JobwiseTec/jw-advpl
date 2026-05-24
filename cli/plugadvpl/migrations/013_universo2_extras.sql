-- Migration 013 — Universo 2 extras (XXA/XAM/XAL + RECORD_COUNTS placeholder)
--
-- Adiciona 3 tabelas SX que o COLETADB.tlpp emite mas que a migration 002
-- nao cobria. Schema baseado em smoke real contra Protheus 7.00.240223P
-- (2026-05-24), inspecionando headers dos CSVs gerados pelo COLETADB v1.0.1.
--
-- RECORD_COUNTS NAO criou tabela nova — vai popular a coluna `num_rows`
-- da tabela `tabelas` (placeholder ja existente desde migration 002).

-- =============================================================================
-- XXA — Tabela de Dominios (codigos auxiliares com chave composta DOM/CDOM)
-- =============================================================================
-- Diferente do SX5 (genericas), XXA tem dominios HIERARQUICOS — cada DOM
-- pode ter multiplos CDOM com descricao em 3 idiomas + tipo.
-- Ex: DOM="COM_MODSUG", CDOM="COM_MODACA", DESCRI="Modalidade Acatada"
CREATE TABLE IF NOT EXISTS dominios (
    dominio       TEXT NOT NULL,       -- XXA_DOM (chave principal)
    cod_dominio   TEXT NOT NULL,       -- XXA_CDOM (codigo no dominio)
    sequencia     TEXT DEFAULT '',     -- XXA_SEQUEN (ordem visual)
    descricao     TEXT DEFAULT '',     -- XXA_DESCRI (PT-BR)
    descricao_es  TEXT DEFAULT '',     -- XXA_DSCSPA (espanhol)
    descricao_en  TEXT DEFAULT '',     -- XXA_DSCENG (ingles)
    tipo          TEXT DEFAULT '',     -- XXA_TYPE (classifica subdominio)
    PRIMARY KEY (dominio, cod_dominio, sequencia)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_dominios_dom ON dominios(dominio);

-- =============================================================================
-- XAL — Classificacoes LGPD (catalogo master de tipos de dado sensivel)
-- =============================================================================
-- Tabela referenciada por XAM via IDXAL. Pequena (poucas dezenas de rows
-- tipicamente). Ex: id=501 desc="Nome", id=502 desc="CPF", id=503 desc="Email".
CREATE TABLE IF NOT EXISTS classificacoes_lgpd (
    filial        TEXT NOT NULL DEFAULT '', -- XAL_FILIAL (em geral vazio)
    classificacao_id TEXT NOT NULL,         -- XAL_ID (chave numerica)
    descricao     TEXT DEFAULT '',          -- XAL_DESC
    tipo          TEXT DEFAULT '',          -- XAL_TIPO
    proprietario  TEXT DEFAULT '',          -- XAL_PROPRI (S = standard TOTVS)
    custom        INTEGER DEFAULT 0,        -- 1 se proprietario != "S"
    PRIMARY KEY (filial, classificacao_id)
) WITHOUT ROWID;

-- =============================================================================
-- XAM — Anonimizacao de Campos (LGPD/Compliance)
-- =============================================================================
-- Mapeia cada campo do dicionario que precisa ser anonimizado, com
-- classificacao (FK XAL), justificativa, modulo, alias da tabela e flag
-- de uso atual (XAM_SINUSE).
CREATE TABLE IF NOT EXISTS anonimizacao_campos (
    filial            TEXT NOT NULL DEFAULT '', -- XAM_FILIAL
    classificacao     TEXT DEFAULT '',          -- XAM_CLASSI (categoria LGPD)
    anonimizar        TEXT DEFAULT '',          -- XAM_ANONIM (1=sim, 0=nao)
    justificativa     TEXT DEFAULT '',          -- XAM_JUSTIF
    campo             TEXT NOT NULL,            -- XAM_FIELD (ex: A02_NOMMBR)
    modulo            TEXT DEFAULT '',          -- XAM_MODULE
    classificacao_id  TEXT DEFAULT '',          -- XAM_IDXAL (FK -> XAL.id)
    alias             TEXT NOT NULL,            -- XAM_ALIAS (ex: A02)
    identificador     TEXT DEFAULT '',          -- XAM_IDENT
    proprietario      TEXT DEFAULT '',          -- XAM_PROPRI (S = standard)
    justificativa2    TEXT DEFAULT '',          -- XAM_JUSTI2 (livre)
    em_uso            TEXT DEFAULT '',          -- XAM_SINUSE (S=em uso)
    custom            INTEGER DEFAULT 0,        -- 1 se proprietario != "S"
    PRIMARY KEY (filial, alias, campo)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_anonimizacao_campos_idxal ON anonimizacao_campos(classificacao_id);
CREATE INDEX IF NOT EXISTS idx_anonimizacao_campos_alias ON anonimizacao_campos(alias);
