-- Migration 014 — Universo 6 (Workflow): SCHEDULES + JOBS
--
-- Absorve 2 dos 4 CSVs Workflow que o COLETADB.tlpp emite:
--
--   - SCHEDULES.csv: agendamentos do scheduler interno Protheus (XX0/XX1/XX2
--     joined + recorrência decodificada via DecodificaRecorrencia no servidor).
--   - JOBS.csv: parse de appserver*.ini recursivo (todas as definições
--     [<job_name>] com MAIN/ENVIRONMENT/RefreshRate/Parametros).
--
-- Os schemas refletem 1:1 o header literal dos CSVs (que ja sao colunas
-- decodificadas e human-readable — diferente das outras SX que tem colunas
-- fisicas X*_*).

-- =============================================================================
-- SCHEDULES — agendamentos do scheduler Protheus
-- =============================================================================
-- Cada linha = um job agendado (do dicionario XX1, com FK pra XX2/XX0).
-- Recorrencia ja vem decodificada em colunas humanas (tipo, detalhe, etc.).
-- A coluna recorrencia_raw preserva o texto cru pra debug.
CREATE TABLE IF NOT EXISTS schedules (
    codigo                 TEXT PRIMARY KEY,        -- XX1_CODIGO
    rotina                 TEXT DEFAULT '',         -- XX1_ROTINA (programa ADVPL)
    empresa_filial         TEXT DEFAULT '',         -- XX2_EMP+XX2_FIL ou XX2_EMPFIL
    environment            TEXT DEFAULT '',         -- XX1_ENV
    modulo                 TEXT DEFAULT '',         -- XX1_MODULO
    status                 TEXT DEFAULT '',         -- XX1_STATUS (1=Ativo, ...)
    tipo_recorrencia       TEXT DEFAULT '',         -- Diario, Semanal, Mensal, Anual, Sempre, Smart
    detalhe_recorrencia    TEXT DEFAULT '',         -- Descricao humana
    execucoes_dia          TEXT DEFAULT '',         -- N por dia ou N/A
    intervalo_hh_mm        TEXT DEFAULT '',         -- HH:MM ou N/A
    data_fim_recorrencia   TEXT DEFAULT '',         -- DD/MM/YYYY ou N/A
    hora_inicio            TEXT DEFAULT '',         -- XX1_HORA
    data_criacao           TEXT DEFAULT '',         -- XX1_DATA formatada
    ultima_execucao        TEXT DEFAULT '',         -- XX1_ULTDIA formatada
    ultima_hora            TEXT DEFAULT '',         -- XX1_ULTHOR
    recorrencia_raw        TEXT DEFAULT ''          -- XX1_RECORR_TXT (debug)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_schedules_rotina ON schedules(rotina);
CREATE INDEX IF NOT EXISTS idx_schedules_env ON schedules(environment);

-- =============================================================================
-- JOBS — definicoes [<job_name>] do appserver*.ini
-- =============================================================================
-- Diferente de schedules (que vem do banco), jobs vem do parse do INI.
-- PK composta porque o mesmo nome de sessao pode aparecer em multiplos
-- appserver*.ini (slave_rest, master, broker, etc.).
CREATE TABLE IF NOT EXISTS jobs (
    arquivo                TEXT NOT NULL,            -- nome do appserver*.ini
    sessao                 TEXT NOT NULL,            -- [JOB_NAME] no INI
    rotina_main            TEXT DEFAULT '',          -- MAIN= no JOB
    refresh_rate           TEXT DEFAULT '',          -- RefreshRate=
    parametros             TEXT DEFAULT '',          -- Parametros= (CSV concat)
    PRIMARY KEY (arquivo, sessao)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_jobs_main ON jobs(rotina_main);
