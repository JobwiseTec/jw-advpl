# plugadvpl

[![CI](https://github.com/JoniPraia/plugadvpl/actions/workflows/ci.yml/badge.svg)](https://github.com/JoniPraia/plugadvpl/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/plugadvpl.svg)](https://pypi.org/project/plugadvpl/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

Plugin Claude Code + CLI Python que indexa fontes **ADVPL/TLPP** (TOTVS Protheus) em SQLite com FTS5. Permite ao Claude consultar metadados de funções, tabelas, MV_*, call graph e SQL embedado **antes** de abrir arquivos `.prw` inteiros — economiza **10–15× tokens** em projetos Protheus reais.

## Por que existe

Projetos Protheus têm de 500 a 30.000+ arquivos `.prw`/`.tlpp` com 1.000–10.000 linhas cada. Pedir para o Claude "explicar a função FATA050" tipicamente consome 12k+ tokens só para abrir o arquivo. Com plugadvpl, a mesma pergunta consome ~700 tokens — Claude consulta metadados estruturados (funções, chamadores, tabelas, parâmetros, SQL embedado) e só abre o range específico que precisa.

## Quick start

```bash
# 1. Instalar uv (https://docs.astral.sh/uv/)
winget install astral-sh.uv                              # Windows
# OU: curl -LsSf https://astral.sh/uv/install.sh | sh    # Linux/macOS

# 2. Dentro do Claude Code, adicionar marketplace e instalar plugin
/plugin marketplace add JoniPraia/plugadvpl
/plugin install plugadvpl

# 3. Abrir projeto Protheus, executar:
/plugadvpl:init      # cria .plugadvpl/index.db e fragment CLAUDE.md
/plugadvpl:ingest    # indexa fontes (~30s-60s para 2000 fontes com --workers 8)

# 4. Pronto! Claude usa o índice automaticamente.
/plugadvpl:arch FATA050.prw         # visão geral de um fonte
/plugadvpl:callers FATA050           # quem chama essa função
/plugadvpl:tables SA1                # quem lê/grava na tabela SA1
/plugadvpl:param MV_LOCALIZA         # onde esse parâmetro é usado
```

## Features

### Plugin Claude Code (24 skills + 4 agents + 1 hook)

| Comando slash | Função |
|---|---|
| `/plugadvpl:init` | Cria índice + CLAUDE.md fragment + .gitignore |
| `/plugadvpl:ingest` | Indexa fontes (paralelo adaptive) |
| `/plugadvpl:reindex <arq>` | Re-indexa um arquivo após edição |
| `/plugadvpl:status` | Estatísticas do índice |
| `/plugadvpl:find <termo>` | Busca composta (função → arquivo → conteúdo FTS) |
| `/plugadvpl:callers <funcao>` | Quem chama essa função |
| `/plugadvpl:callees <funcao>` | O que essa função chama |
| `/plugadvpl:tables <T>` | Quem usa a tabela T (read/write/reclock) |
| `/plugadvpl:param <MV>` | Onde o parâmetro MV_* é usado |
| `/plugadvpl:arch <arq>` | **Visão arquitetural** — use ANTES de Read |
| `/plugadvpl:lint [arq]` | Lint findings (13 regras single-file) |
| `/plugadvpl:doctor` | Diagnósticos do índice |
| `/plugadvpl:grep <pattern>` | Busca textual (FTS5 / LIKE / identifier) |

**10 skills de conhecimento** (auto-load por contexto): plugadvpl-index-usage, advpl-encoding, advpl-fundamentals, advpl-mvc, advpl-embedded-sql, advpl-matxfis, advpl-pontos-entrada, advpl-webservice, advpl-jobs-rpc, advpl-code-review.

**4 agents especializados**: advpl-analyzer (explique X), advpl-impact-analyzer (o que quebra se mudar Y?), advpl-code-generator (crie UF/MVC/REST/PE), advpl-reviewer-bot (revise).

### CLI Python (`plugadvpl`)

Todos os subcomandos aceitam `--format {json|table|md}`, `--limit`, `--compact`, `--no-content` (ingest), `--redact-secrets` (ingest). Veja `plugadvpl --help`.

### Schema SQLite

- **22 tabelas físicas** + **2 FTS5 virtuais** (unicode61 com tokenchars `_-` + trigram para substring exata)
- **6 lookups** pré-populados: 279 funções nativas TOTVS, 194 funções restritas, 24 regras de lint, 5 macros SQL, 8 módulos ERP, 15 PEs catalogados
- **Schema mirror** do `extrairpo.db` do projeto Protheus (validado em 24k+ fontes)

## Estrutura do projeto

```
plugadvpl/
├── .claude-plugin/                 # plugin.json + marketplace.json
├── skills/                          # 24 SKILL.md (14 comando + 10 conhecimento)
├── agents/                          # 4 .md (analyzer, impact-analyzer, code-generator, reviewer-bot)
├── hooks/                           # SessionStart hook (Node.js .mjs cross-platform)
├── cli/                             # CLI Python (PyPI: plugadvpl)
│   ├── pyproject.toml               # hatchling + hatch-vcs + PEP 735 dep groups
│   └── plugadvpl/
│       ├── parsing/                 # parser.py, stripper.py, lint.py
│       ├── migrations/              # 001_initial.sql (22 tables + 2 FTS5)
│       ├── lookups/                 # 6 JSONs pré-populados
│       ├── db.py, scan.py, ingest.py, query.py, output.py, cli.py
│       └── tests/                   # 239 tests, 87% coverage
├── scripts/                         # validate_plugin.py, bump_marketplace_version.py
├── docs/                            # spec + plan + cli-reference + schema
└── .github/workflows/               # CI matrix 3 OS × 3 Python, release Trusted Publisher OIDC
```

## Métricas

| | Valor |
|---|---|
| Linhas Python (CLI) | ~3.500 |
| Testes | **239 passing** (unit + integration), 15 syrupy snapshots, 1 bench, 3 e2e_local |
| Coverage | 87% (linhas + branches) |
| Ingest 2.000 fontes | <60s com `--workers 8` |
| Token-budget "explique FATA050" | ~700 tokens (vs ~12.000 sem o plugin) |

## Documentação

- [docs/cli-reference.md](docs/cli-reference.md) — referência completa dos 14 subcomandos
- [docs/schema.md](docs/schema.md) — schema SQLite detalhado
- [docs/superpowers/specs/](docs/superpowers/specs/) — design history + critical reviews
- [docs/superpowers/plans/](docs/superpowers/plans/) — implementation plan (14 chunks TDD)

## Contribuindo

[CONTRIBUTING.md](CONTRIBUTING.md) tem o setup local. Em resumo:

```bash
git clone https://github.com/JoniPraia/plugadvpl.git
cd plugadvpl
uv sync --directory cli
make test
```

## Status

**v0.1.0** — MVP release-ready. Universo 1 (Fontes) populado. Universo 2 (Dicionário SX) e Universo 3 (Rastreabilidade) reservados para v0.2+ via migrations.

Roadmap em `docs/superpowers/specs/2026-05-11-plugadvpl-design.md` §15.

## Créditos

- **Parser de fontes:** portado do projeto Protheus interno do autor (parser_source.py, ~750 linhas validadas em 24.592 fontes padrão TOTVS + 1.990 fontes de cliente)
- **Lookup catalogs:** funções nativas/restritas/lint rules/SQL macros extraídas de [advpl-specialist](https://github.com/thalysjuvenal/advpl-specialist) (Thalys Augusto, MIT) — crédito no [NOTICE](NOTICE)

## Licença

[MIT](LICENSE).
