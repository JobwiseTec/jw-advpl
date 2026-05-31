-- Migration 017 — score de conformidade por INI.
--
-- Adiciona `score` (0-100) + `compliance` (selo) em ini_files. Ambos são
-- calculados pelo audit engine (parsing/ini_audit.py::audit_one_file) na MESMA
-- transação que reconstrói os findings — nunca ficam stale em relação a
-- ini_audit_findings. Permite que `status`/`ini-audit` mostrem a saúde de cada
-- INI por ambiente sem re-auditar (vira um SELECT).
--
-- score:      razão ponderada (0.0–100.0) entre regras conformes e total avaliado.
--             100.0 quando não há regras aplicáveis ao role (sem baseline).
-- compliance: 'compliant' (>=85) | 'partial' (>=60) | 'non_compliant' (<60) | ''
ALTER TABLE ini_files ADD COLUMN score REAL NOT NULL DEFAULT 100.0;
ALTER TABLE ini_files ADD COLUMN compliance TEXT NOT NULL DEFAULT '';
