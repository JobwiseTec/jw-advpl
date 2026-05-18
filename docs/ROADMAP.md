# Roadmap

Visão pública do que vem no plugadvpl. Datas são estimativas — comunidade pode mudar prioridades.

## ✅ v0.1.x — Lançamento inicial (2026-05)

- Plugin Claude Code + CLI Python publicados (PyPI + marketplace GitHub)
- Schema SQLite com 22 tabelas + 2 FTS5 + 6 lookups embarcados
- Parser ADVPL/TLPP com strip-first, ~25 extractors
- 13 lint rules single-file (regex)
- 14 subcomandos CLI + slash commands
- 24 skills no plugin
- Onboarding via one-liner installer

## ✅ v0.2.0 — Biblioteca de referência embarcada (2026-05)

- ~23k linhas de docs ADVPL/TLPP integradas como `reference.md` em 6 skills
- 5 novas knowledge skills: `advpl-advanced`, `advpl-tlpp`, `advpl-web`,
  `advpl-dicionario-sx`, `advpl-mvc-avancado`
- 7 exemplos `.prw/.tlpp` de produção embarcados em `skills/<x>/exemplos/`
- CLAUDE.md fragment muito mais rico (tabela de decisão + workflow numerado)
- Skill `setup` com detecção de ambiente CLI vs VSCode

## ✅ v0.3.0 — Universo 2: Dicionário SX (2026-05)

[Milestone v0.3.0](https://github.com/JoniPraia/plugadvpl/milestone/1)

- Ingest do dicionário SX exportado da rotina de exportação do Protheus
  (CSV — Configurador → Misc → Exportar Dicionário). Apenas customizações
  do cliente; padrão TOTVS é ignorado por design.
- 11 tabelas populadas: `tabelas` (SX2), `campos` (SX3), `gatilhos` (SX7),
  `parametros` (SX6), `perguntas` (SX1), `consultas` (SXB), `pastas` (SXA),
  `relacionamentos` (SX9), `indices` (SIX), `tabelas_genericas` (SX5),
  `grupos_campo` (SXG).
- 3 comandos novos: `plugadvpl ingest-sx <pasta-csv>`, `plugadvpl impacto
  <campo> [--depth N]` (killer feature), `plugadvpl gatilho <campo>` +
  `plugadvpl sx-status` (auxiliar).
- 11 lint rules cross-file ativadas (`SX-001..SX-011`): valida que
  `X3_VALID`/`X7_REGRA` referenciam funções/campos/consultas que
  realmente existem.
- Skill nova: `advpl-dicionario-sx-validacoes` (X3_VALID, X3_INIT, X3_WHEN,
  X3_VLDUSER, X7_REGRA + workflow plugadvpl impacto).
- Parser portado de projeto interno do autor (872 linhas, MIT) — adaptado
  para plugadvpl removendo dependências SaaS.

## ✅ v0.4.x — Universo 3: Rastreabilidade (2026-05)

[Milestone v0.4.0](https://github.com/JoniPraia/plugadvpl/milestone/2)

Universo 3 entregue em 4 dot-releases consecutivas (3 features + polish):

### v0.4.0 — Feature A: execução não-direta
- Tabela `execution_triggers` (schema v5, migration 005)
- Detector `parsing/triggers.py` com 4 mecanismos canônicos TOTVS:
  - `workflow` — `TWFProcess`/`MsWorkflow`/`WFPrepEnv` (callbacks aprovação)
  - `schedule` — `Static Function SchedDef()` (configurador SIGACFG)
  - `job_standalone` — `Main Function` + `RpcSetEnv` (daemon ONSTART)
  - `mail_send` — `MailAuto`/`SEND MAIL` UDC/`TMailManager`
- Comando `workflow` + skill `/plugadvpl:workflow`

### v0.4.1 — Feature B: ExecAuto chain expansion
- Tabela `execauto_calls` (schema v6, migration 006)
- Catálogo `execauto_routines.json` (31 rotinas TOTVS — MATA*/FINA*/CTBA*/
  EECAP*/TMSA* com módulo + tabelas primárias/secundárias + URL fonte)
- Detector `parsing/execauto.py` resolve `MsExecAuto({|x,y,z| MATA410(x,y,z)},
  ...)` → rotina + tabelas inferidas + op_code (3/4/5 → inc/alt/exc)
- Comando `execauto` + enrichment de `arch` (campo
  `tabelas_via_execauto_resolvidas: list[str]`)

### v0.4.2 — Feature C: Protheus.doc agregada
- Tabela `protheus_docs` (schema v7, migration 007)
- Detector `parsing/protheus_doc.py` extrai 16 tags canônicas TOTVS
  (`@type`, `@author`, `@param`, `@return`, `@deprecated`, `@history`, etc)
  + `raw_tags` catch-all
- Inferência de módulo dual (path-based + routine-prefix)
- Comando `docs [modulo]` com 3 modos: lista, `--show <fn>` Markdown
  estruturado, `--orphans` (cross-ref BP-007)

### v0.4.3 — Polish pack
- Code review independente identificou 5 críticos com repro confirmado
  (todos corrigidos): callbacks misturados entre TWFProcess vizinhos,
  Protheus.doc fechando em `/*/` literal de @example, RpcSetEnv perdendo
  módulo com 6 args literais, bloco órfão puxando função distante,
  `infer_module` retornando SIGAEST silenciosamente
- 4 importantes endereçados: TMailManager solo, `--show` com homônimos,
  catálogo +6 rotinas + dup test, índices em `funcao` (migration 008)
- 489 testes verde (era 478)

## ✅ v0.5.x / v0.6.x — Universo 4: Trace + Qualidade (2026-05)

Universo 4 entregue em 2 features:

- **Feature A — Trace unificado** (`v0.5.x`): `plugadvpl trace <entidade>` que
  agrega visão cross-universo (fontes + SX + chamadas + workflow + jobs).
  Auto-detect de tipo (campo|funcao|tabela|arquivo|parametro|pergunte).
- **Feature B — Qualidade & métricas** (`v0.6.x`): `plugadvpl metrics`,
  `plugadvpl hotspots`, `plugadvpl cobertura-doc`. Complexidade ciclomática
  McCabe, nesting, fan-out, params_count, has_doc por função. Schema v10
  (tabela `fonte_metrics`).
- v0.6.1 polish: 3 bugs reportados em uso real (`infer_module` filename prefix,
  `cobertura-doc` heurística estendida, UX hint em tabela vazia).

## ✅ v0.7.0 — Fase 0: Quick Wins runtime/encoding/webservice (2026-05)

Fase 0 do roadmap de runtime. 5 lint rules + 1 comando + 1 contract doc.
Detalhes em [`docs/fase0/quick-wins.md`](fase0/quick-wins.md):

- **5 lint rules novas**: WS-001, WS-002, WS-003, XF-001, ENC-001
- **`plugadvpl edit-prw {check,open,save}`** — conversão CP1252↔UTF-8 in-place
- **`docs/exec-contract.md`** + **`docs/examples/uexec.prw`** (MIT) — contrato
  canônico HTTP/JSON `POST /rest/uexec` para execução headless DEV/CI

622 testes verde. Zero dependência externa.

## ✅ v0.8.0 — Fase 1: plugadvpl compile (wrapper TDS-LS) (2026-05-18)

Primeiro passo do roadmap de runtime ADVPL — wrapper Python sobre o binário
oficial `advpls` (TOTVS) com saída JSON estruturada. Detalhes em
[`docs/fase1/compile-design.md`](fase1/compile-design.md).

- **`plugadvpl compile <fonte...>`** com modos `appre` (local) e `cli` (full
  via AppServer TCP), auto-detect.
- **`plugadvpl compile --init-config`** gera template `runtime.toml`.
- **Schema JSON estável** + 5 lint patterns externalizados em
  `lookups/compile_patterns.json` + 6 redact patterns em
  `lookups/redact_patterns.json`.
- **140+ novos testes** (702 verde total). 5 testes de no-credential-leak.
- **4 módulos novos** isolados: runtime_config, compile_parser, compile, cli.

Pavimenta Fase 2 (`plugadvpl exec` — cliente HTTP do contrato U_EXEC).

## 🟡 Próximas Fases — Runtime ADVPL completo (sem ETA fixa)

Roadmap restante para fechar o ciclo "indexar → compilar → executar →
testar → deployar" sem precisar abrir TDS:

- **Fase 2 — `plugadvpl exec`**: cliente HTTP nativo que consome o contrato
  `U_EXEC` (v0.7.0). Executa função arbitrária com args via CLI.
- **Fase 3 — `plugadvpl deploy`**: hot-swap RPO (strategies a definir).
- **Fase 4 — `plugadvpl smoke` + `test`**: bateria CI completa usando exec.
- **Fase 5 — hooks + orchestrator agent**: integração nativa Claude Code.

## 🔵 Backlog (sem ETA)

- **`appserver.ini` parser** — ingest de `jobs` e `schedules`
- **`record_counts`** via conexão DBAccess (opcional, exige deps externas)
- **`menus`/`mpmenu_*`** — parser de menu Protheus
- **Embeddings opcionais** via `sqlite-vec` para queries semânticas
- **Skill `advpl-refactoring`** — 6 padrões de refactor com before/after
- **Skill `advpl-debugging`** — top 50 erros comuns + métodos de debug
- **Skill `advpl-testing-probat`** — framework ProBat para TLPP
- **LSP server** experimental (autocomplete em editores baseado no índice)
- **VSCode native extension** complementando o plugin Claude Code

## Como influenciar o roadmap

- **Sugerir feature**: abrir Issue com label `enhancement` no [GitHub](https://github.com/JoniPraia/plugadvpl/issues/new/choose)
- **Discussão pública**: [GitHub Discussions](https://github.com/JoniPraia/plugadvpl/discussions)
- **Pull request**: especialmente bem-vindas para parser, lint rules e skills temáticas

Comunidade ADVPL define o que vem primeiro.
