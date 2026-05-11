# Changelog

Todas as mudanças notáveis estão documentadas aqui, seguindo [Keep a Changelog](https://keepachangelog.com/) e [SemVer](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-05-11

### Added

- **Plugin Claude Code completo**: 24 skills (14 command wrappers + 10 thematic knowledge), 4 agents (analyzer/impact-analyzer/code-generator/reviewer-bot), 1 SessionStart hook (Node.js cross-platform)
- **CLI Python `plugadvpl`** com 14 subcomandos (init, ingest, reindex, status, find, callers, callees, tables, param, arch, lint, doctor, grep, version)
- **SQLite schema** (22 tabelas + 2 FTS5 + 6 lookups) espelhado do extrairpo.db do Protheus
- **Parser ADVPL/TLPP** (strip-first + 25+ regex extractors, 91% coverage)
- **Lint single-file** (13 regras: BP/SEC/PERF/MOD via regex)
- **Lookups pré-populados** com dados do advpl-specialist (279 funcoes_nativas, 194 funcoes_restritas, 24 lint_rules, 5 sql_macros, 8 modulos_erp, 15 pontos_entrada_padrao)
- **Ingest paralelo** adaptive (single-thread <200 arquivos, ProcessPool acima; mp_context fork/spawn por plataforma)
- **FTS5 dual-index** (unicode61 com tokenchars `_-` para palavras + trigram para substring exata como `SA1->A1_COD`)
- **CI/CD completo**: GitHub Actions matrix 3 OS x 3 Python, github-action-benchmark, Trusted Publisher OIDC PyPI, validate_plugin.py

### Notes

- 239 testes (unit + integration), 87% coverage
- Parity test com cliente real (1.990 fontes) — ingest <60s, parser tabelas/funcoes OK, gap em parametros/sql para refinamento em v0.2
- 17 tabelas reservadas para v0.2 (Universo 2 SX dictionary + Universo 3 Rastreabilidade) via migrations
