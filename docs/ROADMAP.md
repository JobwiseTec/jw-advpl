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

## ✅ v0.9.0 — Cofre nativo de credenciais + zero-config flow (2026-05-19)

- **Keyring nativo do OS** (Win Credential Manager / macOS Keychain / Linux Secret Service) para credenciais Protheus — substitui variáveis de ambiente.
- **Zero-config flow**: `import-tds-servers` + `set-credentials` → `compile` direto, sem precisar de `runtime.toml`.
- Resolução de credenciais em camadas (CLI > keyring > env vars).
- Base para todas as integrações autenticadas subsequentes (ingest-protheus, tq, ini-audit).

## ✅ v0.9.1 — Probe de AppServer + explain-config (2026-05-19)

- **Keyring** já entregue em v0.9.0; v0.9.1 refina o zero-config flow.
- **`--probe-appserver network`** testa conectividade com AppServer via `advpls validate`.
- **`--explain-config`** mostra qual server foi resolvido e por quê (debug de configuração).
- Hints claros quando credenciais ou servidor não são encontrados.

## ✅ v0.10.0 — Auditoria de ambiente Protheus (2026-05-20)

- **`plugadvpl ini-audit`**: audita arquivos `.ini` do ambiente (appserver/dbaccess/smartclient/tss/broker) contra **487 regras TDN-oficiais** filtradas por tipo + role.
- **`plugadvpl log-diagnose`**: diagnostica console.log/error.log/profile.log/compila.log contra **93 correction tips** da KB TDN. Pipeline em 2 estágios com janela `--since` relativa.
- 12 categorias de diagnóstico, schema bump 10 → 12 (migrations 011 + 012).
- Skills `/plugadvpl:ini-audit` + `/plugadvpl:log-diagnose` + 135 testes novos.

## ✅ v0.11.0 — Universo 5: Live Protheus Inspector (2026-05-21)

- **`plugadvpl ingest-protheus --endpoint <url>`**: substitui workflow CSV manual por dump ao vivo via REST API do `COLETADB.tlpp` instalado no AppServer.
- Bundle pattern: `POST /coletadb/run` gera CSVs; `POST /coletadb/file` baixa em chunks; cliente verifica sha256. Auth via HTTP Basic (mesmas credenciais do `compile`).
- Reference impl `docs/reference-impl/coletadb.tlpp` (~1900 linhas, MIT).
- Skill `/plugadvpl:ingest-protheus` + 20 testes novos (11 unit + 9 integration).

## ✅ v0.12.0 — Universo 5b estendido: SX adicional + RECORD_COUNTS (2026-05-22)

- **XXA/XAL/XAM**: `dominios`, `classificacoes_lgpd`, `anonimizacao_campos` — cobertura sobe de 11/21 → 15/21 CSVs do bundle COLETADB.
- **RECORD_COUNTS**: popula `tabelas.num_rows` a partir do CSV de inventário de rows físicas (match por prefix de 3 chars, sem tabela nova).
- Schema bump 12 → 13 (migration 013). Smoke real: 395.858 SX rows + 5.112 rows de anonimização.

## ✅ v0.13.0 — Universo 5b: Workflow + Menus — cobertura 21/21 (2026-05-24)

- **Universo 6 — Workflow** (migration 014): `schedules` (XX0/XX1/XX2, recorrência decodificada) + `jobs` (parse recursivo de `appserver*.ini`).
- **Universo 8 — Menus** (migration 015, 6 tabelas): `mpmenu_menu`, `mpmenu_function`, `mpmenu_item`, `mpmenu_i18n`, `mpmenu_key_words`, `mpmenu_rw`.
- Cobertura total: **21/21 CSVs do bundle COLETADB** (52% → 100%). Schema bump 13 → 15.
- Smoke real: 66.098 rows de menus (12.589 items + 7.549 funcs + 37.767 i18n).

## ✅ v0.13.1 — Hash dinâmico no cliente REST + smoke fixes (2026-05-24)

- **Hash dinâmico**: cliente escolhe `sha256`/`sha1`/`md5` via campo `hash_algo` do manifest — builds Protheus antigas sem `Sha2_256` agora funcionam.
- **Hash parcial** para arquivos >64KB via `MemoRead` truncado no servidor.
- `coletadb.tlpp` v1.0.3 com 3 bugs corrigidos (path separator Linux, `InventarioCarregar` false positive, `HashArquivo` fallback).
- 4 gotchas reais do smoke incorporados nas skills (`SetKeyHeaderResponse`, `@Post` só com `User Function`, `ErrorBlock` em `Begin Sequence`, `function` lowercase).

## ✅ v0.14.0 — Troca Quente MVP local + compile multi-env (2026-05-27)

- **`plugadvpl tq`**: restart do AppServer via `restart_cmd` + healthcheck HTTP (GET retorna 200/401/404). Flags: `--use-server`, `--timeout`, `--no-healthcheck`, `--dry-run`.
- **`compile --all-envs`**: compila para todos os environments cadastrados no server em sequência — resolve o problema de RPO desatualizado no env REST.
- Campo `restart_cmd` no `Server` dataclass; `--set-restart-cmd` para configurar.
- Skill `/plugadvpl:tq` + 16 testes novos. Escopo MVP (sem rollback automático).

## ✅ v0.14.1 — Hints acionáveis no `tq` + skill `/plugadvpl:deploy` (2026-05-27)

- **Hints acionáveis quando `tq` falha**: lista o que verificar (console.log, porta REST, `--timeout`), reduzindo pingback em ambientes novos.
- **Skill `/plugadvpl:deploy`**: orquestrador que encadeia `compile → tq → smoke` opcional. Sem subcomando CLI novo — o agente segue o playbook com pre-flight e tabela de troubleshoot.

## ✅ v0.15.0 — Guarda contra restart acidental de PROD (2026-05-27)

- **`--confirm-prod` no `tq`**: servers marcados como produção exigem flag explícita; `--dry-run` dispensa.
- **Flag `is_prod`** no `Server` dataclass: `compile --mark-prod` / `--no-prod` toggleam o flag.
- `compile --list-servers` mostra marcador `PROD` ao lado do nome.
- 7 testes de integração novos (suite: 1044 → 1051).

## ✅ v0.16.0 — Interop com Sonar TOTVS oficial (2026-05-29)

- **Coluna `sonar_rules`** em `lint_rules` (migration 016, SCHEMA_VERSION 15 → 16): cada finding carrega o ID Sonar oficial TOTVS quando há equivalência.
- **10 regras mapeadas** (3 fortes: SEC-001→BG1000, SEC-004→CA2052, MOD-001→CA1004; 7 adjacentes com prefixo `~`). Catálogo completo offline — sem dependência do Sonar instalado.
- **SessionStart hook** silencia em `docs/`/`tests/`/`fixtures/`/`gaps/` — elimina ruído em meta-repos.
- 8 testes novos. Suite: 1060 passed.

## ✅ v0.16.1 — AGENTS.md gêmeo do CLAUDE.md (2026-05-29)

- **`plugadvpl init` grava `AGENTS.md`** além do `CLAUDE.md` — mesmo fragment versionado, atende Cursor/Copilot/Codex e qualquer agente que segue o padrão `AGENTS.md`.
- **`plugadvpl status`** detecta fragment desatualizado em qualquer um dos dois arquivos.
- Idempotente: segundo `init` não duplica o fragment.
- 3 testes novos (suite: 1060 → 1063).

## ✅ v0.16.2 — Cursor Rules nativos no `init` (2026-05-29)

- **`plugadvpl init` gera Cursor Rules**: 1 rule global em `~/.cursor/rules/plugadvpl.mdc` (`alwaysApply: true`) + 52 rules locais em `.cursor/rules/plugadvpl-<skill>.mdc` com `globs` específico por contexto.
- **Single source**: rules geradas em runtime a partir das `skills/<X>/SKILL.md` embarcadas no wheel (mesma fonte que Claude Code consome).
- **Marker `<!-- plugadvpl-rule-version: X.Y.Z -->`** controla idempotência; arquivos do usuário com nome conflitante são preservados com warning.
- **Flag `--no-cursor`** desabilita mesmo com sinais presentes. Falha de I/O nunca quebra o `init`.
- Módulo `cursor_rules.py` (~400 linhas, stdlib only). 34 testes novos (suite: 1063 → 1097).

## 🟡 Próximas Fases — Runtime ADVPL completo (sem ETA fixa)

Roadmap restante para fechar o ciclo "indexar → compilar → executar →
testar → deployar" sem precisar abrir TDS:

- **Fase 2 — `plugadvpl exec`**: cliente HTTP nativo que consome o contrato
  `U_EXEC` (v0.7.0). Executa função arbitrária com args via CLI.
- **Fase 3 — `plugadvpl deploy`**: hot-swap RPO (strategies a definir).
- **Fase 4 — `plugadvpl smoke` + `test`**: bateria CI completa usando exec.
- **Fase 5 — hooks + orchestrator agent**: integração nativa Claude Code.

## 🔵 Backlog (sem ETA)

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
