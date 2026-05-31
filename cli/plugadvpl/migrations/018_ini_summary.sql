-- Migration 018 — sumário da auditoria de INI por arquivo.
--
-- Guarda o sumário de contagem (ok / mismatch / missing / intentional /
-- total_rules) calculado pelo audit_one_file, na mesma transação dos findings.
-- Alimenta o card de score do relatório (--format html) sem re-auditar.
ALTER TABLE ini_files ADD COLUMN summary_json TEXT NOT NULL DEFAULT '{}';
