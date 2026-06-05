# Changelog

Todas as mudanças notáveis estão documentadas aqui, seguindo [Keep a Changelog](https://keepachangelog.com/) e [SemVer](https://semver.org/).

## [Unreleased]

### Added

- **`tables <T> --catalog` — catálogo de campos com X3_CBOX decodificado** ([#64](https://github.com/JoniPraia/plugadvpl/issues/64)): mostra os campos da tabela (do dicionário SX3) com tipo formatado (`C(1)`, `N(14,2)`), título e o **X3_CBOX decodificado** (`1=Item, 2=Cabeçalho, 3=Ambos`) — os valores aceitos de cada discriminador, que ficavam opacos só pelo schema. Marca `discriminador` os campos `C(1)`/`C(2)` com cbox (enum de negócio). Resolve a dor "que valores `XX_TIPO` aceita?" sem ir ao banco. Flag no comando `tables` (sem skill nova). **Validado na SX real** (tabela standard com 54 campos / 8 discriminadores; 18,7k campos com cbox na base).
- **`tables --mode write` agora enxerga gravação via MVC e ExecAuto** ([#61](https://github.com/JoniPraia/plugadvpl/issues/61)): o fonte que define um `ModelDef` (tabela master via `FWFormStruct(1, 'X')`) passa a contar como **mantenedor** da tabela (`modo='write_mvc'` no `fonte_tabela`) — gravação que a detecção clássica (RecLock/Replace) não via, deixando o cadastro MVC **invisível**. Idem para `MsExecAuto` (`modo='write_execauto'`, tabelas resolvidas pelo catálogo). `--mode write` virou **abrangente** (inclui os dois); `write_mvc`/`write_execauto` existem como filtro explícito. Modelo read-only (`SetOnlyView`) não dispara. Sem migration (`modo` é free-text). **Validado em base real** (cadastros MVC antes invisíveis agora aparecem como gravadores).
- **Comando `family <prefixo>` + glob no `find`** ([#62](https://github.com/JoniPraia/plugadvpl/issues/62)): `family` lista os fontes de uma **família** (basename começa com o prefixo) numa tabela com `source_type`, LoC, `capabilities` e a **descrição do header** (LEFT JOIN com `fonte_header_doc` do #63). `find` agora aceita **glob** (`find "MOD12*"` → ancorado no início; `*FAT*` → substring; `?` = um char). Cross-link (P3): `arch` sugere `family <prefixo>` nos próximos passos. Skill `family` (catálogo 62 → **63**). Validado em base real (famílias de 4–6 fontes, descrição vinda do header).
- **`arch --include-header` + parser de header doc declarativo** ([#63](https://github.com/JoniPraia/plugadvpl/issues/63)): novo `parsing/header.py` extrai o bloco de metadados do topo de fontes ADVPL (`Programa/Autor/Data/Descrição/Doc.Origem/Solicitante/Uso/Obs`), distinto do Protheus.doc. Tabela `fonte_header_doc` (migration 026, schema **v25 → v26**), populada no ingest (no-op gracioso quando ausente). `arch <fonte> --include-header` anexa o `header_doc`. Tolerante a variações de pontuação/acento; **validado em base real** (cobertura ~0–40% conforme convenção do projeto). Decisões empíricas travadas em teste: escopo no 1º bloco de comentário (evita falso-positivo de `:=`), normalização de `DESCRIÇÃO / OBJETIVO`, mínimo de 2 labels.

## [0.22.0] - 2026-06-04

🔒 Release **Segurança & Privacidade (opt-in)** + **POUI completo** (Fases 1–3b) + curadoria do `ini-audit`. A camada de segurança é **opt-in com default desligado** — sem ligar, o comportamento é **byte-idêntico** ao de sempre, sem overhead nem dependência nova.

### Changed

- **`ini-audit` — curadoria das regras (lotes 1-2):** primeiras regras `critical` validadas contra a documentação TDN real (via fetch). `verificado=1` em RootPath/SourcePath (obrigatórias), JOB_WS ENVIRONMENT. Rebaixadas `critical`→`warning` as que têm default documentado (DBAccess Port→7890, MaxStringSize, LogClient Port). Cobertura de verificação 12→25 (10 das 18 críticas curadas; as 8 restantes — TSS SPED/JOB_WS/cert — precisam do Manual de Configuração TSS). Meta-audit (`scripts/audit_ini_rules.py`) guia a fila.

### Added

- **`ingest-poui`** — detecção de projetos PO UI (frontend Angular TOTVS): lê `package.json`, extrai família `@po-ui/*`, major do Angular exigido e flag de incompatibilidade. Cache hash+mtime; ignora `node_modules`. Tabela `poui_projetos` (migration 022, schema v22). Skill `ingest-poui`. Docs: `docs/schema.md`, `docs/cli-reference.md`.
- **`poui-bridge`** (Fase 2) — cruza chamadas `HttpClient` Angular (`this.http.get/post/...`) com rotas REST do Protheus (`@Get`/`@Post` TLPP indexadas em `rest_endpoints`), entregando rastreabilidade ponta-a-ponta front↔back. Tabela `poui_datasources` (migration 023, schema v23). Skill `poui-bridge`. `ingest-poui` agora também extrai datasources dos `.ts`.
- **`poui-componentes`** (Fase 3a) — catálogo verificado de bindings `p-*` (inputs/outputs) por componente PO UI Angular. 948 entradas extraídas do código-fonte do `po-angular`. Tabela `poui_componentes` (migration 024, schema v24). Comando `plugadvpl poui-componentes [componente]`. Skill `poui-componentes` (anti-alucinação: IA verifica atributos antes de escrever templates). Guard `test_poui_componentes_consistency` (6 invariantes). Docs: `docs/schema.md`, `docs/cli-reference.md`.
- **`poui-lint`** (Fase 3b) — lint de templates PO UI: detecta bindings `p-*` usados em `<po-*>` que não existem no catálogo `poui_componentes`. Regra `POUI-PROP` (anti-alucinação). Parser `extract_poui_template_usage` em `parsing/poui.py`. Tabela `poui_componentes_uso` (migration 025, schema v25). `ingest-poui` agora também varre `.html` → `poui_componentes_uso`. Skill `poui-lint` (61 skills no catálogo). Docs: `docs/schema.md`, `docs/cli-reference.md`. Fecha épica POUI.

### Security

Camada **opt-in** de segurança/privacidade em defesa-em-profundidade. **Default desligado** — sem ligar, o output é **byte-idêntico** ao de sempre e não há overhead nem dependência nova (tudo stdlib). Tudo **determinístico** (mesmo input → mesma saída; sem chamada de LLM no caminho quente).

- **Camada 0 — Prevenção (`gitleaks`):** varredura de segredos no `pre-commit` e no CI (job `secret-scan`, gitleaks v8.30.1). Config + allowlist em `.gitleaks.toml` (regras `advpl-hardcoded-password`, `conn-url-credentials` + ruleset default). Impede segredo de entrar no repositório. Guia do cliente: `docs/seguranca-gitleaks-cliente.md`.
- **Camada 2 — Egress (`--privacy` / `PLUGADVPL_PRIVACY`):** mascara PII/segredo no funil único de saída (`output.render`). CPF/CNPJ/e-mail → **token estável HMAC** (pseudonimização mão-única, sem disco); segredo → `***REDACTED***`; valor financeiro → faixa (`~10k-100k`); estrutura/flags preservadas. Estilos `label` (default) e `fpe` (format-preserving). Classificação de campo financeiro pela **verdade do SX3** (`X3_TIPO`/`X3_DECIMAL` + `X3_PICTURE`), não por heurística de nome (~100% vs ~66% de precisão). Módulos `privacy/{config,engine,buckets,brdocs,__init__}.py`.
- **Camada 3 — Input / prompt injection (`PLUGADVPL_INJECTION_SCAN`):** detector heurístico determinístico de alta precisão (OWASP LLM01) — 8 padrões PT+EN (ignorar-instruções, troca-de-papel, system-prompt, jailbreak, exfiltração…) sobre conteúdo de terceiros (comentário no `.prw`, linha de log). Marca o trecho com `[!INJECAO?]` e alerta em `stderr`, sinalizando à IA que aquilo é **dado**, não comando. Código/SQL legítimo não dispara. Módulo `privacy/injection.py`.
- **Relativização — comando `diagnose`:** `plugadvpl diagnose <fonte> --record-file <json> [--fields-file <campos.json>]` avalia os pontos de decisão de uma rotina contra um registro real e devolve o **desfecho exato** com o valor sensível **relativizado** (`( nSaldo + nValPed ) ~103% de A1_LC -> VERDADEIRO`), sem o R$ real. Aritmética exata local (`ast`, sem `eval`); `outcome=None` quando irresolvível (não chuta). Parser `parsing/decisions.py` + `privacy/diagnose.py`. Skill `diagnose` (catálogo 61 → **62**).
- **Garantias:** sem estado, sem disco (processo efêmero); custo < 1 ms no uso real (proporcional ao tamanho da saída). Cobertura: módulos `privacy/*` + `parsing/decisions.py` no gate de lint (ruff+mypy strict) do CI; suíte de testes dedicada (mascaramento, buckets, validação SX, determinismo, decisões, diagnose, injeção).
- **Docs:** guia em camadas com fluxo + pré-requisitos de instalação em `docs/seguranca.md`; seção **Segurança & Privacidade** no README.

## [0.21.1] - 2026-06-02

Patch de **segurança** — continuação do hardening SSL/TLS da v0.21.0 (mesma classe do bug SSL2/SSL3), surfado pelo meta-audit.

### Fixed

- **`ini-audit` 🔒 — TLS 1.0 legado não é mais recomendado habilitado**: `TSS-SSLCONFIGURE-TLS1` recomendava `=1` (TLS 1.0 ligado), divergindo da gêmea `APP-SSLCONFIGURE-TLS1='0'`; e `TSS-TSSREST_SERVER-SSLPROTOCOLMIN` aceitava mínimo `TLSv1.0`. Corrigidos para `0` / `TLSv1.2` (BEAST/POODLE; PCI-DSS exige ≥ TLS 1.2). Mesma classe do bug SSL2/SSL3 da v0.21.0.

### Added

- **Guard `test_ssl_tls_protocolo_legado_desabilitado`**: invariante de segurança no CI — `value_eq` de SSL2/3 + TLS1.0/1.1 deve recomendar `0`; TLS1.2/1.3 deve recomendar `1`. Inequívoco (padrão de indústria, não Protheus-específico) — pega regressão de protocolo inseguro.

### Changed

- **Curadoria `ini_rules` — 1º lote (segurança SSL/TLS)**: família de protocolos on/off marcada `verificado=1` (5 → **12** regras curadas, todas guard-protegidas).

## [0.21.0] - 2026-06-02

Release de **confiabilidade do `ini-audit`**: a base de 487 regras tinha sido gerada em lote sem trilha de procedência e continha valores fabricados (inclusive 1 bug de segurança). Esta versão corrige os dados quebrados, dá rastreabilidade ao catálogo e encerra a classe de falso-positivo "inventou tag".

### Fixed

- **`ini-audit --format html` — encoding real no relatório** ([#37](https://github.com/JoniPraia/plugadvpl/pull/37)): o relatório lia o INI já decodificado (`str`) e o parser devolvia o placeholder `"str"`; agora lê **bytes** → detecção real (`ascii`/`cp1252`/`utf-8-bom`).
- **`ini-audit` — score não penaliza mais boa-prática ausente** ([#37](https://github.com/JoniPraia/plugadvpl/pull/37)): chave `info` ausente não vira `missing` (nice-to-have); chave `warning` ausente é flagada mas **não derruba o score** (só `critical`-missing pune). Evitava selo "FORA DE CONFORMIDADE" indevido.
- **`ini-audit` — correção de dados fabricados no catálogo `ini_rules`** (estes valores não procediam):
  - 🔒 **Segurança:** `TSS-SSLCONFIGURE-SSL2`/`SSL3` recomendavam `=1` (habilitar protocolo legado inseguro), divergindo da regra APP gêmea (`=0`, "INSEGURO. Deve estar desabilitado"). Um TSS já seguro (SSL2=0) era marcado **crítico → FORA DE CONFORMIDADE** e o fix mandava ligar. Corrigido para `=0`.
  - `APP-GENERAL-MAXSTRINGSIZE`: enum fabricado `1|Maior|Menor` (a regra recomendava `10`, que nem estava no próprio enum) → `key_present`.
  - **71 regras `range_check` sem range real** (`expected` sem `..`) eram no-ops silenciosos — `_evaluate_value` sempre retornava `True`. Rebaixadas para `key_present` pendente curadoria (5 delas tinham um valor recomendado mal-aplicado como mínimo, ex: `THREADMAX=50` ⇒ "≥50").

### Added

- **`ini-audit` — procedência e verificação no catálogo `ini_rules`** (migration 021, schema v20 → v21). 5 campos novos por regra:
  - `fonte` — URL/pageId TDN **estruturado** (antes vivia solto no `fix_guidance`); populado em 455/487 regras.
  - `verificado` — `0`=não-curada (default), `1`=validada (5 regras SSL/TLS de segurança já marcadas). Guard exige `fonte` quando `verificado=1`.
  - `condicional` — `1`=chave opcional-de-feature (`[Mail]`/`[FTP]`/`[WebApp]`/`[WebAgent]`/`[SQLiteServer]`, 48 regras); **ausência NÃO vira finding** (a feature pode simplesmente não ser usada) — encerra a classe de falso-positivo "inventou tag". Valor presente-e-errado ainda é flagado.
  - `default_totvs` / `versao_min` — reservados para a curadoria (default vazio).
- **Guard `test_ini_rules_consistency`**: barra no CI dado quebrado voltando ao catálogo `ini_rules` — `range_check` sem range, `value_in` misturando número e texto, regras `critical` `value_eq` contraditórias na mesma (seção, chave), e `verificado=1` sem `fonte`. Espelha o `test_lint_catalog_consistency`.

### Changed

- **Schema v20 → v21** (migration 021 `ini_rules` procedência: `fonte`/`verificado`/`condicional`/`default_totvs`/`versao_min`).

> Próximo: curadoria incremental das 487 regras (eleva `verificado` por lote validado contra TDN) + uso de `verificado` no selo de conformidade quando a cobertura de verificação for significativa.

## [0.20.0] - 2026-06-01

### Added

- **Lint `SQL-001`** (critical): comentário SQL line-style `--` dentro de `BeginSql..EndSql`. O preprocessador não garante preservação de `\n` → ao concatenar linhas, o `--` comenta o resto da query até o `EndSql` (ORA-00936 silencioso). Detecta fora de literal de string, só em blocos multi-linha. Closes [#24](https://github.com/JoniPraia/plugadvpl/issues/24).
- **Lint `SQL-002`** (critical): `UPDATE`/`DELETE` SQL sem `WHERE` (corrupção de tabela em massa). Captura a string SQL COMPLETA em `TCSqlExec(literal)`/`BeginSql` (não o snippet truncado nas aspas internas) — sem falso-positivo quando o `WHERE` vem depois de um valor entre aspas.
- **Catálogo `apis_por_build` + comando `check-build <fonte> --target-build`**: sinaliza uso de método `FW*`/`MsDialog`/`FWBrowse` ausente na build Protheus alvo, antes de compilar. Resolve `oVar := Classe():New()` por função e só reporta com a classe confirmada (zero falso-positivo). Migration 019. Closes [#26](https://github.com/JoniPraia/plugadvpl/issues/26).
- **Catálogo `campos_semantica` + comando `semantica <campo>`**: semântica contextual de campos SX cujo significado muda conforme um discriminador (TIPO/PODER3/STATUS) — só semântica padrão Protheus. Migration 020. Closes [#27](https://github.com/JoniPraia/plugadvpl/issues/27).
- **`lint --target-build <build>`**: inclui findings `BUILD-001` (build-check do `apis_por_build`) no fluxo normal do lint. Persiste em `meta.target_build` — configurar uma vez faz o build-check rodar automático no `lint` seguinte (inclusive multi-agente).
- **Skill `advpl-ui-patterns`**: catálogo de patterns visuais Protheus (browses `FWMarkBrowse`/`FWBrowse`/`MsSelect`, `MsDialog` via `MsAdvSize`, ParamBox por tipo, atalhos `SetKey`+`VK_*`, coloração, export Excel via `FWMSExcel:GetXMLFile` → `.xml`). Closes [#25](https://github.com/JoniPraia/plugadvpl/issues/25).

### Changed

- **Schema v18 → v20** (migration 019 `apis_por_build` + 020 `campos_semantica`).
- **42 lint rules** (era 40, +`SQL-001`/`SQL-002`); **57 skills** (era 54, +`advpl-ui-patterns`/`check-build`/`semantica`); **35 subcomandos**.
- `docs/cli-reference.md` atualizada — documenta os 35 comandos (faltavam ~10: Universo 4/5/6/7 + auditoria INI/log).

## [0.19.0] - 2026-05-31

### Added — `ini-audit` ganha score de conformidade + detecção de fonte de banco + `--format html` (PR #21 [@tbarbito](https://github.com/tbarbito))

Closes [#20](https://github.com/JoniPraia/plugadvpl/issues/20).

**Score de conformidade ponderado por severidade** (crit ×3.0, warn ×1.5, info ×0.5) com selo (`compliant ≥85` / `partial ≥60` / `non_compliant <60`) persistido em `ini_files.score` + `compliance` (migration 017+018) na **mesma transação** dos findings — nunca stale. Aparece no resumo do CLI: `Score AppServer_TSS.ini: 34.7 (non_compliant)`.

**Detecção estrutural de fonte de banco:** quando INI define a conexão por **uma** fonte (`[TopConnect]` / `[DBAccess]` / `DB*` no `[Environment]`), as demais viram `ok_with_note` (alternativas redundantes). **2+ fontes ativas** num papel que conecta direto viram finding `warning` `INI-DB-CONFLICT` — captura uma classe de problema real em ambientes mal configurados.

**`--format html` self-contained:** card de score + selo + findings agrupados (críticos/warnings/justificados) + chaves não-reconhecidas (typos/obsoletas via novo módulo `ini_known_keys.py` com catálogo de ~170 chaves canônicas TDN) + seções comentadas + dirty lines + **INI sugerido** que reescreve preservando comentários (`[CORRECAO]` no valor divergente, chaves críticas ausentes injetadas DENTRO da seção existente, BOM removido). Botão "copiar" no HTML.

`OutputFormat.html` adicionado ao `output.py` — infra reusável por outros comandos.

### Added — `log-diagnose` ganha cross-link console↔profile + `--format html` (PR #23 [@tbarbito](https://github.com/tbarbito))

Closes [#22](https://github.com/JoniPraia/plugadvpl/issues/22).

**`--link <arquivo>`:** ingere o arquivo oposto e correlaciona por `environment::thread` (fallback `thread` → `environment`). Enriquece findings do principal cuja thread bate com a do linkado, com contexto do profile (pico memória, uptime, stack). Sem match → resultado gracioso. Resume cross-link em stderr + bloco no HTML.

**`--format html`:** cards de severidade + métricas, resumo por categoria, tabela de findings com link TDN/Oracle, trecho original num expansível, dicas de correção, bloco de correlação. **Deep-link Oracle pro código específico** (`docs.oracle.com/error-help/db/ora-xxxxx/`) em vez da página índice — economiza 1 click no troubleshooting.

### Review do mantedor

Ambos PRs passaram por revisão técnica antes do merge:
- **Smoke E2E** com INIs e logs sintéticos — `INI-DB-CONFLICT` detectado, HTML renderizado, score correto (34.7 non_compliant em INI com 2 fontes DB ativas).
- **Edge cases** validados: XSS multi-vetor (`<svg onload>`, `<img onerror>`, `javascript:` URL, `</td>` injection), BOM+CRLF, chaves duplicadas, connection strings com `;`/`=`, seções comentadas, unicode/acentos.
- **Lint cleanup** dos 5 arquivos novos: `RUF002`, `TC003`, `UP035`, `F401`, `I001`, `SIM103`, `PLR2004` (extrai `_MAX_TIPS_IN_REPORT` constante), `format` pass — todos `ruff` + `mypy` clean.
- **6 regression tests adicionados** (4 em `ini_*`, 2 em `log_*`) cobrindo XSS multi-vetor, duplicate keys, connection strings com chars especiais, seção comentada, URL Oracle lowercase.

### Changed — Schema bump v16 → v18

Migrations 017 (`ini_score`) e 018 (`ini_summary`) adicionam colunas `score`, `compliance`, `summary_json` em `ini_files`.

### Tests

- PR #21: 21 unit tests novos do @tbarbito + 4 regression do review = 25
- PR #23: 11 unit tests novos do @tbarbito + 2 regression do review = 13
- Total: **38 testes novos**. Suite full: 1297 → 1339 passed.

### Bumped

- `uvx plugadvpl@0.18.0` → `uvx plugadvpl@0.19.0` nas 28 skills.
- `plugin.json` / `marketplace.json` → 0.19.0.

### Créditos

Features inteiramente desenhadas e implementadas por **[@tbarbito](https://github.com/tbarbito)** — mesmo autor da feature original de `ini-audit` + `log-diagnose` no PR [#6](https://github.com/JoniPraia/plugadvpl/pull/6) (v0.4.x, ~16k linhas com 487 regras TDN + 19 alert rules). Esta release v0.19.0 estende as ferramentas que ele mesmo entregou, com revisão técnica + regression tests do mantedor.

## [0.18.0] - 2026-05-31

### Added — `plugadvpl migrate-tlpp` (migrador determinístico ADVPL clássico → TLPP moderno)

Primeiro migrador determinístico do ecossistema TOTVS. Inverso da migração manual: aplica 11 recipes em ordem topológica fixa, com auto-validação via `plugadvpl compile` e rollback cascata em 3 níveis. Endereça gap #6 do `roadmap-vs-engpro-totvs.md`.

**Posicionamento (do research multi-modal):**
- TOTVS oficial (`totvs/engpro-advpl-tlpp-skills`) tem knowledge skill `advpl-to-tlpp-migration` (15 passos + `tlpp-migration-patterns.md`) mas **nenhuma ferramenta executável**.
- `tds-vscode` não tem refactor/code-action ADVPL→TLPP. `advpls` CLI não tem `--migrate`.
- Único competidor (`thalysjuvenal/advpl-specialist`, 155★) é AI-driven, sem garantia de equivalência semântica.
- **plugadvpl v0.18.0 = primeiro com migrador determinístico + auto-validação via compile + impact analyzer via DB**.

**4 subcomandos (pipeline ts-migrate-style):**

```bash
plugadvpl migrate-tlpp init <pasta>      # analisa, gera report, read-only
plugadvpl migrate-tlpp rename <arq>      # só rename + encoding (mais conservador)
plugadvpl migrate-tlpp recipes <arq>     # aplica recipes (diff por default; --write aplica)
plugadvpl migrate-tlpp todos             # lista débitos `@plugadvpl-todo` pendentes
```

**11 recipes em ordem canônica topológica (spec §3.6):**

| # | Recipe ID | Categoria | Função |
|---|---|---|---|
| 1 | `convert-encoding` | SAFE | cp1252 → utf-8 (decodificado pelo orquestrador antes dos recipes) |
| 2 | `rename-extension` | SAFE | `.prw` → `.tlpp` |
| 3 | `header-includes` | SAFE | `protheus.ch` → `totvs.ch` + adiciona `tlpp-core.th` se TLPP features detectadas |
| 4 | `remove-public-default` | SAFE | `PUBLIC cVar` → `cVar` (TLPP é private por default) |
| 5 | `user-function-lowercase` | SAFE | `User Function X()` → `function u_x()`; preserva nome se há callers externos (DB query) |
| 6 | `named-args` | SAFE | `:=` → `=` em chamadas (gated `--tlpp-version=20.3.2+`) |
| 7 | `namespace-infer` | IDIOMS | Adiciona `namespace custom.<modulo>.<nome>` baseado em path |
| 8 | `begin-sequence-to-try` | IDIOMS | `Begin Sequence/Recover/End Sequence` → `try/catch`; aninhado → `@plugadvpl-todo` |
| 9 | `conout-to-fwlog` | IDIOMS | `ConOut("msg")` → `FwLogMsg("info", "msg")` |
| 10 | `json-inline` | IDIOMS | Detecta `JsonObject():New()` chains, emite `@plugadvpl-todo` (consolidação inline manual) |
| 11 | `expand-truncated-names` | IDIOMS | Detecta nomes 10-char (limite ADVPL legacy); emite `@plugadvpl-todo` via DB lookup |

**Safety gates (spec §4):**

- **Pre-flight:** git working tree clean (override `--allow-dirty`); DB ingest populado (override `--no-impact-check` — modo conservador preserva nomes truncados); lint pre-flight rejeita arquivos com `SEC-001`/`SEC-004`; backup `.bak.<YYYYMMDDHHMMSS>` automático (preserva `.bak` legado).
- **Post-flight (com `--validate`):** roda `plugadvpl compile` automaticamente. Se falha, rollback cascata: (1) `.bak.<timestamp>` mais antigo → (2) `git checkout HEAD -- <file>` → (3) abort `typer.Exit(2)` com mensagem CRITICAL.
- **NEVER-propagate:** exception em qualquer recipe vira `status="error"` sem matar restantes.

**Markers `@plugadvpl-todo`:** recipes que não conseguem 100% inserem comentário `// @plugadvpl-todo:<recipe-id> <razão>`. `migrate-tlpp todos` varre projeto e lista débitos. Sintaxe `//` confirmada válida em TLPP moderno.

**Atribuição (spec §9):** Material TOTVS Engenharia de Produto (`engpro-advpl-tlpp-skills/skills/advpl-tlpp/advpl-to-tlpp-migration/`) sob licença MIT (commit `8131443e23cdcf6c7b6e4c943756d98aa7d42f75`, verificado em 2026-05-31). plugadvpl é MIT — derivação compatível. Permalinks SHA-fixo na skill `/plugadvpl:migrate-tlpp`.

**Skill `/plugadvpl:migrate-tlpp`** (54ª skill do plugin; agora adicionada a `_SKILL_GLOBS` + `_CURSOR_META_ALWAYS_APPLY`).

### Added — `edit_prw.convert_and_save` ganha `timestamp` kwarg

Backup com timestamp (`.bak.<YYYYMMDDHHMMSS>`) ao invés de `.bak` fixo. Default `False` — backward-compat preservada com callers existentes. Necessário pra `migrate-tlpp` permitir re-runs sem sobrescrever backup original.

### Added — Snapshot fixtures pra roundtrip

5 fixtures `.prw` em `cli/tests/fixtures/migrate_tlpp/` cobrem padrões típicos (User Function simples, Begin Sequence, JsonObject chain, PUBLIC var, namespace hint via path SIGAFAT). Snapshot tests via syrupy bloqueiam regressão de transformação.

### Changed — Lint scope expand

`LINT_FILES` ganha novos arquivos: `migrate_tlpp.py`, `migrate_tlpp_diff.py`, `migrate_tlpp_recipes/*.py` (11 arquivos). Total: 29 → ~41 arquivos cobertos por `ruff check` + `format` + `mypy`.

### Tests

- 30+ unit tests recipes (11 recipes × 3-4 tests cada)
- 13 unit tests orquestrador (dataclasses, pre-flight, dry_run, apply, rollback cascata 3 caminhos)
- 12 integration tests CLI (init/rename/recipes/todos)
- 5 snapshot tests fixtures
- 3 rollback cascata integration tests

Suite full: 1216 → **1297 passed** (+81 testes).

### Bumped

- `uvx plugadvpl@0.17.0` → `uvx plugadvpl@0.18.0` nas 28 skills (27 + `migrate-tlpp` nova).
- `plugin.json` / `marketplace.json` → 0.18.0.

## [0.17.0] - 2026-05-30

### Added — `plugadvpl doc-writer` gera blocos Protheus.doc canônicos TOTVS

Inverso de `plugadvpl docs` (que **lê**) — `doc-writer` **escreve** o bloco `/*/{Protheus.doc} ... /*/` no formato canônico TOTVS a partir de flags estruturadas. Endereça gap #4 do `roadmap-vs-engpro-totvs.md`.

Roundtrip-compatible: `extract_protheus_docs(generate_protheus_doc(spec))` recupera o spec sem perda.

**CLI:**

```bash
plugadvpl doc-writer <funcao>
    [--type function|user_function|method|class|property]
    [--summary "descrição"] [--author "X"] [--since YYYY-MM] [--version V]
    [--deprecated "motivo"]
    [-p "nome,tipo,desc"]   # repetível; [nome] = opcional
    [--return "tipo,desc"]
    [-e "exemplo"]           # repetível
```

`--format json` emite metadata estruturada (`spec_to_dict`).

**API pública** (`cli/plugadvpl/doc_writer.py`):

- `DocSpec` frozen dataclass (13 campos seguindo shape de `_empty_doc()` do parser).
- `Param` / `Return` dataclasses.
- `generate_protheus_doc(spec) -> str` — bloco formatado canônico.
- `spec_from_cli_args(funcao, **kwargs) -> DocSpec` — construtor a partir de flags brutas.
- `spec_to_dict(spec) -> dict` — serialização JSON.

**Skill:** `skills/doc-writer/SKILL.md` com when-to-use, exemplos completos, workflow recomendado, convenções de tipos canônicos ADVPL (`character`/`numeric`/`logical`/`date`/`array`/`block`/`object`/`nil`/`mixed`). Adicionada também a `_CURSOR_META_ALWAYS_APPLY` (Cursor sempre injeta — par simétrico de `docs`).

**Testes (30 novos):**

- 26 unit em `test_doc_writer.py` (basic, metadata, params com `[nome]` opcional, return, deprecated, examples multi-linha, history, CLI args, roundtrip extract→generate, edge cases vazios).
- 4 integration em `TestDocWriter` (minimal, full metadata, `--format json`, deprecated com reason).

Suite full: 1184 → 1216 passed.

### Changed — CI `LINT_FILES` expandido de 22 → 30 (issue #17)

Antes da v0.17.0, CI lintava só 22 dos 31 `.py` em `cli/plugadvpl/`. Os 8 arquivos novos do multi-agente (Fases 1-3) e v0.16.5 (`agent_doctor`, `codex_config`) ficavam fora do scope, acumulando débito.

Adicionados ao `LINT_FILES` (todos `ruff check` + `ruff format` + `mypy` clean):

- `_skill_catalog.py`, `_version.py`
- `agent_doctor.py`, `codex_config.py` (v0.16.5)
- `copilot_instructions.py`, `cursor_rules.py`, `gemini_skills.py` (v0.16.1-v0.16.4)
- `doc_writer.py` (v0.17.0)

**Refactors aplicados** pra deixar lint-clean:

- `_skill_catalog.py`: `RET504` (remove assign antes de return) + `noqa: PLC0415` em import lazy intencional (evitar circular).
- `copilot_instructions.py`: `TC003` (Path em `TYPE_CHECKING` block).
- `cursor_rules.py`: extracts `_install_global_rule` + `_install_one_local_rule` helpers — preempt `PLR0912` em `install_cursor_rules`.

Restante: ~9 `.py` em `cli/plugadvpl/parsing/` ainda têm débito legado (endereço em sub-issue futura quando demanda surgir).

### Bumped

- `uvx plugadvpl@0.16.5` → `uvx plugadvpl@0.17.0` nas 27 skills (incluindo `doc-writer`).
- `plugin.json` / `marketplace.json` → 0.17.0.

## [0.16.5] - 2026-05-30

### Fixed — `_transform_body` agora respeita formato por agente (CRÍTICO)

Antes da v0.16.5, `_transform_body` em `_skill_catalog.py` substituía `/plugadvpl:<X>` por `` `Bash: uvx plugadvpl@<ver> <X>` `` (sintaxe MDC Cursor-específica) em **todos** os agentes. Copilot e Gemini interpretavam isso como string literal, não como sugestão de comando — perdiam ~50% do valor das 52 skills.

Agora `_transform_body` aceita param `style: Literal["cursor", "plain"]`:
- `style="cursor"` (Cursor opt-in) — emite `` `Bash: uvx ...` `` (MDC syntax)
- `style="plain"` (default; Copilot/Gemini) — emite `uvx plugadvpl@<ver> <X>` (texto puro)

Todos callers atualizados: `cursor_rules.render_skill_rule` passa `style="cursor"`; `copilot_instructions.render_skill_instructions` e `gemini_skills.render_skill_for_gemini` passam `style="plain"`.

### Added — `plugadvpl doctor --check-agents` valida 5 agentes

Novo subcomando que valida formato dos arquivos gerados pra todos 5 agentes (Claude, Codex/AGENTS.md, Cursor, Copilot, Gemini) **sem precisar instalar os agentes**. Nenhum agente externo tem CLI oficial de validação — preenchemos o gap.

Checks:
- CLAUDE.md e AGENTS.md: fragment markers + version
- Cursor: `.cursor/rules/plugadvpl-*.mdc` frontmatter parseável, `globs` é STRING (não array YAML), version
- Copilot: `.github/instructions/plugadvpl-*.instructions.md` `applyTo` é STRING (não array), version
- Gemini: `.gemini/skills/plugadvpl-*/SKILL.md` frontmatter `name`+`description`, version
- Keywords: 52 SKILL.md descriptions têm "ADVPL"/"Protheus"/"TLPP"/".prw"/"SX"

Output prefixed com `OK`/`--`/`FAIL`/`WARN` (plain ASCII pra compat console Windows). Exit code 1 se algum check fail.

### Added — Cursor meta-skills com `alwaysApply: true`

12 meta-skills transversais (init, ingest, status, doctor, help, workflow, trace, setup, ingest-protheus, reindex, execauto, docs) viravam "Manual only" no Cursor (precisavam `@plugadvpl-init` explícito). Agora ganham `alwaysApply: true` automaticamente quando não têm `globs`.

### Added — Gemini `.agents/skills/` cross-agent install

Quando projeto tem `.agents/skills/` (cross-agent standard emergente, precedência maior que `.gemini/skills/`), Gemini install duplica nas duas pastas. `InstallResult` ganha campo `installed_agents_skills_count` separado.

### Added — Codex `.codex/config.toml` mínimo

Codex CLI usa `.codex/config.toml` per-project. Quando detectado (`.codex/` no projeto OU `codex` no PATH), `init` gera template mínimo com defaults comentados + marker `# plugadvpl-codex-version: X.Y.Z`. Flag `--no-codex` desabilita.

Codex já lê AGENTS.md (gerado pelo init via fragment writer). Este config é opt-in pra customizações futuras.

### Audited — 52 SKILL.md descriptions com keywords ADVPL/Protheus (52/52 pass)

Gemini ativa skills via matching semântico da `description`. Descrições genéricas sem keywords (find, lint, callers, grep, etc.) impediam JIT activation. Auditadas e editadas 11 SKILL.md pra incluir pelo menos 1 keyword de: ADVPL, Protheus, TLPP, .prw, SX. **Threshold accept era ≥40/52; chegamos a 52/52 (100%)**.

### Changed — Cursor global rule rotulada como "(experimental)"

`OK Cursor rules: 1 global (experimental) + 52 locais instaladas`. Cursor docs oficial não confirma que `~/.cursor/rules/` é lido (User Rules globais são UI-only via Settings → Rules). Mantemos o código por compat futura mas sinalizamos a incerteza.

### Added — 28 testes novos

- 3 em TestTransformBody (`_skill_catalog`)
- 4 em test_cursor_rules (style + meta_always_apply + experimental + cursor style assertion)
- 1 em test_copilot_instructions (plain style)
- 3 em test_gemini_skills (plain style + 2 .agents/skills/)
- 6 em test_codex_config (3 detect + 2 render + 1 install no-op)
- 9 em test_agent_doctor
- 5 em TestInitCodexConfig
- 3 em TestDoctorCheckAgents
- 1 em TestInitMultiAgent

Suite full: 1157 → 1186 passed.

### Bumped

- `uvx plugadvpl@0.16.4` → `uvx plugadvpl@0.16.5` nas 26 skills.
- `plugin.json` / `marketplace.json` → 0.16.5.

## [0.16.4] - 2026-05-30

### Added — Gemini CLI native skills no `plugadvpl init` (Fase 3 multi-agente)

`plugadvpl init` agora detecta Gemini CLI (via `~/.gemini/`, `gemini` no PATH, ou `.gemini/` no projeto) e gera:

- **`~/.gemini/GEMINI.md`** (global home) — convenções ADVPL/TLPP machine-wide quando `~/.gemini/` existe ou `gemini` está no PATH.
- **`<project>/GEMINI.md`** (4º gêmeo, junto com CLAUDE.md + AGENTS.md já existentes) — necessário porque Gemini CLI não lê AGENTS.md por padrão.
- **52 arquivos** em `.gemini/skills/plugadvpl-<skill>/SKILL.md` — uma por skill com frontmatter Gemini (`name: plugadvpl-<X>` + `description`). Frontmatter mais simples que Cursor/Copilot — Gemini usa JIT scan + activation por descrição.

Detection conservadora com **sinais INDEPENDENTES**: sinal global (`~/.gemini/` ou `gemini` PATH) ativa apenas global home; sinal de project (`.gemini/` no projeto) ativa apenas project. Consistente com Cursor policy — evita pegada não-solicitada.

Single source: as 52 SKILL.md específicas são geradas em runtime a partir das `skills/<X>/SKILL.md` embarcadas no wheel (mesma fonte que Claude Code, Cursor e Copilot consomem). Substituições idênticas (`/plugadvpl:<X>` → `` `Bash: uvx plugadvpl@0.16.4 <X>` ``).

Marker `<!-- plugadvpl-gemini-version: X.Y.Z -->` controla idempotência. **Distinto dos 3 markers existentes** (`plugadvpl-rule-version`, `plugadvpl-instructions-version`, `plugadvpl-fragment-version`) — evita falso-positivo cross-agent. `plugadvpl status` detecta GEMINI.md ou skill desatualizadas.

**Flag:** `plugadvpl init --no-gemini` desabilita mesmo com sinais presentes.

**Garantia:** falha de I/O em Gemini nunca quebra `init` — mesmo NEVER-propagate das Fases 1/2.

**Estrutura de skill por diretório:** Gemini espera `<skills_dir>/<name>/SKILL.md` (não arquivo flat). O orquestrador cria `.gemini/skills/plugadvpl-<X>/` antes de escrever SKILL.md.

Predecessor: v0.16.3 entregou Copilot Instructions (Fase 2). v0.16.4 completa Fase 3 cobrindo Gemini CLI via mecanismo oficial GEMINI.md + `.gemini/skills/`.

### Changed — `_skill_catalog.py` ganha `GEMINI_MARKER_PREFIX`

Adição mínima (+1 constante) pra cobrir o terceiro marker distinto:
- `RULE_MARKER_PREFIX` (Cursor, v0.16.2)
- `INSTRUCTIONS_MARKER_PREFIX` (Copilot, v0.16.3)
- `GEMINI_MARKER_PREFIX` (Gemini, v0.16.4 — novo)

### Changed — `_check_fragment_staleness()` cobre Gemini files

`plugadvpl status` agora detecta versão desatualizada em:
- `CLAUDE.md` + `AGENTS.md` (v0.16.1)
- Cursor rules (`~/.cursor/rules/plugadvpl.mdc` + `<project>/.cursor/rules/plugadvpl-*.mdc`, v0.16.2)
- Copilot instructions (`.github/copilot-instructions.md` + `.github/instructions/plugadvpl-*.instructions.md`, v0.16.3)
- **Gemini files** (`~/.gemini/GEMINI.md` + `<project>/GEMINI.md` + `.gemini/skills/plugadvpl-*/SKILL.md`, v0.16.4 — novo)

Helper `_check_gemini_staleness` paralelo ao Cursor/Copilot helpers (mantém PLR0912 ≤12).

### Added — `plugadvpl.gemini_skills` módulo

Novo módulo isolado (~321 linhas) com:
- `GeminiTarget` + `InstallResult` dataclasses (frozen, mutable fields com `default_factory=list`)
- `detect_gemini()` — política conservadora, sinais independentes
- `render_global_gemini_md()` — markdown plano com marker
- `render_skill_for_gemini()` — frontmatter Gemini (`name` + `description` apenas)
- `install_gemini_skills()` — orquestrador top-level NEVER-propagate
- Helpers `_install_gemini_global_home` + `_install_gemini_project_md` + `_install_one_gemini_skill` (PLR0912 preempt)

Reusa `_skill_catalog` (DRY).

### Added — 28 testes novos (TDD)

- 17 unit em `test_gemini_skills.py` (6 detect + 3 render_global + 6 render_skill + 2 install)
- 8 integration em `TestInitGeminiSkills` (no signals/project only/home only/--no-gemini/quiet + idempotency + overwrite + preserve)
- 3 integration em `TestStatus` (stale home + project + skill)

Suite full: 1123 → 1151 passed.

### Bumped

- `uvx plugadvpl@0.16.3` → `uvx plugadvpl@0.16.4` nas 26 skills operacionais.
- `plugin.json` / `marketplace.json` → 0.16.4.

### Multi-agente status (v0.16.4)

Plugadvpl agora cobre nativamente **5 agentes IA**:

| Agente | Mecanismo | Versão entregue |
|---|---|---|
| Claude Code | `CLAUDE.md` fragment | v0.1.x |
| Codex CLI | `AGENTS.md` gêmeo | v0.16.1 |
| Cursor | `.cursor/rules/*.mdc` (Cursor Rules) | v0.16.2 |
| GitHub Copilot | `.github/copilot-instructions.md` + `.github/instructions/*.instructions.md` | v0.16.3 |
| **Gemini CLI** | **`GEMINI.md` + `.gemini/skills/<X>/SKILL.md`** | **v0.16.4 (novo)** |

Cada agente recebe convenções globais + 52 skills específicas no formato nativo.

## [0.16.3] - 2026-05-29

### Added — Copilot Instructions nativos no `plugadvpl init` (Fase 2 multi-agente)

`plugadvpl init` agora detecta `.github/` no projeto e gera:

- **1 arquivo global** em `.github/copilot-instructions.md` (markdown plano, repo-wide) — convenções ADVPL/TLPP, encoding cp1252, tabela de decisão, comandos `uvx`. Respeita soft limit de ~2 páginas documentado pelo Copilot.
- **52 arquivos específicos** em `.github/instructions/plugadvpl-<skill>.instructions.md` — uma por skill com frontmatter `applyTo` glob específico por contexto (string única, não array YAML como em Cursor MDC).

Single source: as 52 instructions são geradas em runtime a partir das `skills/<X>/SKILL.md` embarcadas no wheel (mesma fonte que Claude Code e Cursor consomem). Substituições idênticas (`/plugadvpl:<X>` → `` `Bash: uvx plugadvpl@0.16.3 <X>` ``).

Marker `<!-- plugadvpl-instructions-version: X.Y.Z -->` controla idempotência. **Distinto do Cursor (`plugadvpl-rule-version`)** — evita falso-positivo entre os 2 agentes. `plugadvpl status` detecta instructions desatualizadas.

**Flag:** `plugadvpl init --no-copilot` desabilita mesmo com `.github/` presente.

**Garantia:** falha de I/O em Copilot nunca quebra `init` — mesmo guarantee da Fase 1 Cursor.

Predecessor: v0.16.2 entregou Cursor Rules nativos (Fase 1). v0.16.3 completa Fase 2 cobrindo GitHub Copilot via mecanismo oficial `.github/copilot-instructions.md` + `.github/instructions/`.

### Changed — refactor `_skill_catalog.py` compartilhado (DRY multi-agente)

Helpers neutros movidos de `cli/plugadvpl/cursor_rules.py` pra novo `cli/plugadvpl/_skill_catalog.py`:

- `_SKILL_GLOBS` dict (52 skills + globs) — source-of-truth da lista canônica de skills
- `_parse_skill_md(text)` — parse YAML frontmatter
- `_transform_body(body, version)` — substituições slash→uvx + version normalize
- `_skills_root()` — dev tree vs wheel fallback
- `WriteOutcome` enum
- `_write_managed_file(target, content, marker_substring)` — renomeado de `_write_rule`; agora aceita `marker_substring` como param obrigatório (sem default — caller passa `RULE_MARKER_PREFIX` ou `INSTRUCTIONS_MARKER_PREFIX`)
- `RULE_MARKER_PREFIX` e `INSTRUCTIONS_MARKER_PREFIX` — **distintos** por agente pra evitar falso-positivo

`cursor_rules.py` importa do `_skill_catalog`. Comportamento Cursor 100% preservado.

### Changed — `_check_fragment_staleness()` cobre Copilot instructions

`plugadvpl status` agora detecta versão desatualizada em:
- `CLAUDE.md` (já cobria)
- `AGENTS.md` (v0.16.1)
- `~/.cursor/rules/plugadvpl.mdc` + `<project>/.cursor/rules/plugadvpl-*.mdc` (v0.16.2)
- **`.github/copilot-instructions.md`** + **`.github/instructions/plugadvpl-*.instructions.md`** (v0.16.3 — novo)

Helper `_check_copilot_instructions_staleness` paralelo ao `_check_cursor_rules_staleness` (mantém PLR0912 ≤12).

### Added — `plugadvpl.copilot_instructions` módulo

Novo módulo isolado (~280 linhas) com:
- `CopilotTarget` + `InstallResult` dataclasses
- `detect_copilot()` — `.github/` no projeto
- `render_global_instructions()` — markdown plano com marker
- `render_skill_instructions()` — frontmatter Copilot (`applyTo` string, `description`)
- `install_copilot_instructions()` — orquestrador top-level com same NEVER-propagate guarantee
- Helpers `_install_global_instructions` + `_install_one_skill` extraídos pra manter complexidade abaixo de PLR0912

Reusa `_skill_catalog` (DRY).

### Added — testes novos (TDD)

- 10 unit em `test_skill_catalog.py` (movidos + 1 novo `test_distinct_marker_does_not_match_other_agent`)
- 12 unit em `test_copilot_instructions.py` (detect/render/install)
- 7 integration em `TestInitCopilotInstructions` (init real com mocks)
- 2 integration em `TestStatus` (stale global + local)

Refactor: 3 tests removidos de `test_cursor_rules.py::TestWriteRule` (cobertura migrou pra `test_skill_catalog.py`).

Suite full: 1097 → 1123 passed.

### Bumped

- `uvx plugadvpl@0.16.2` → `uvx plugadvpl@0.16.3` nas 26 skills operacionais.
- `plugin.json` / `marketplace.json` → 0.16.3.

## [0.16.2] - 2026-05-29

### Added — Cursor Rules nativos no `plugadvpl init`

`plugadvpl init` agora detecta Cursor instalado (via `~/.cursor/` no home ou `.cursor/` no projeto) e gera:

- **1 rule global** em `~/.cursor/rules/plugadvpl.mdc` (`alwaysApply: true`) — convenções ADVPL/TLPP, encoding cp1252, tabela de decisão, comandos `uvx`.
- **52 rules locais** em `.cursor/rules/plugadvpl-<skill>.mdc` — uma por skill embarcada, com `globs` específico por contexto (ex: `plugadvpl-arch.mdc` aplica em `**/*.prw,**/*.tlpp,**/*.prx,**/*.apw`; `plugadvpl-ini-audit.mdc` em `**/*.ini`).

Single source: as 52 rules são geradas em runtime a partir das `skills/<X>/SKILL.md` embarcadas no wheel (mesma fonte que Claude Code consome). 2 substituições simples: `/plugadvpl:<X>` → `` `Bash: uvx plugadvpl@0.16.2 <X>` `` e normalização de versão antiga.

Marker `<!-- plugadvpl-rule-version: X.Y.Z -->` controla idempotência: regen sobrescreve só arquivos nossos (com marker); arquivos do usuário com nome conflitante são preservados com warning. `plugadvpl status` detecta rules desatualizadas igual ao fragment do CLAUDE.md.

**Flag:** `plugadvpl init --no-cursor` desabilita mesmo com sinais presentes (CI/usuários que não querem).

**Garantia:** falha de I/O em rules nunca quebra `init` — Cursor é secundário (silent fail + warning informativo). Exit code do init nunca muda por causa disso.

Predecessor: v0.16.1 entregou AGENTS.md gêmeo (Codex). v0.16.2 completa Fase 1 do multi-agente focando em Cursor com integração nativa via formato MDC.

### Added — `plugadvpl.cursor_rules` módulo

Novo módulo isolado (~400 linhas) com:
- `CursorTarget` + `InstallResult` dataclasses
- `detect_cursor()` — política conservadora
- `render_global_rule()` + `render_skill_rule()` — geradores puros
- `_SKILL_GLOBS` — mapping canônico (52 entradas; dobra como source-of-truth da lista de skills)
- `install_cursor_rules()` — orquestrador top-level
- `_write_rule()` + `WriteOutcome` enum — política de marker

Stdlib only (sem deps novas).

### Changed — `_check_fragment_staleness()` cobre Cursor rules

`plugadvpl status` agora detecta fragment desatualizado em:
- `CLAUDE.md` (já cobria)
- `AGENTS.md` (v0.16.1)
- `~/.cursor/rules/plugadvpl.mdc` (novo)
- `<project>/.cursor/rules/plugadvpl-*.mdc` (novo)

### Changed — wheel inclui `skills/` via `force-include`

`cli/pyproject.toml` ganha `force-include = { "../skills" = "plugadvpl/skills" }` no target wheel. Skills vivem em repo root (fora do package); sem isso, install_cursor_rules() em wheel instalado não acharia SKILL.md de nenhuma skill.

### Added — 34 testes novos (TDD)

- 8 unit em `TestRenderSkillRule` (parse frontmatter, substituições, frontmatter MDC, markers, fallback)
- 2 unit em `TestRenderGlobalRule` (`alwaysApply: true`, sem globs)
- 6 unit em `TestDetectCursor` (sinais + cross-platform + RuntimeError)
- 3 unit em `TestWriteRule` (WRITTEN/OVERWRITTEN/SKIPPED_USER_FILE)
- 2 unit em `TestInstallCursorRules` (smoke end-to-end + no-op)
- 2 unit em `TestSkillGlobs` (52 entradas + paridade com skills/)
- 9 integration em `TestInitCursorRules` (init real com mocks)
- 2 integration em `TestStatus` (stale global + stale local)

Suite full: 1063 → 1097 passed.

### Bumped

- `uvx plugadvpl@0.16.1` → `uvx plugadvpl@0.16.2` nas skills que usam o CLI.
- `plugin.json` / `marketplace.json` → 0.16.2.

## [0.16.1] - 2026-05-29

### Added — Suporte multi-agente via `AGENTS.md` gêmeo

`plugadvpl init` agora grava **dois** arquivos de instruções na raiz do projeto: `CLAUDE.md` (para Claude Code) e `AGENTS.md` (para Cursor, GitHub Copilot, Codex e outros agentes que seguem o padrão `AGENTS.md`). Conteúdo idêntico — ambos ganham a mesma região `<!-- BEGIN plugadvpl --> ... <!-- END plugadvpl -->` versionada via marker `<!-- plugadvpl-fragment-version: X.Y.Z -->`.

Sem isso, Cursor/Copilot/Codex não tinham forma nativa de descobrir as convenções do plugadvpl (índice SQLite, tabela de decisão de comandos, encoding cp1252, etc) e o claim "funciona em qualquer agente" era só na CLI — não nas instruções globais.

Mantém retrocompatibilidade: projetos que já tinham só `CLAUDE.md` ganham o `AGENTS.md` no próximo `plugadvpl init`. Idempotente — segundo `init` não duplica fragment.

### Changed — `_check_fragment_staleness()` cobre ambos arquivos

`plugadvpl status` agora detecta fragment desatualizado em `CLAUDE.md` **ou** `AGENTS.md` (antes só olhava `CLAUDE.md`). Reporta o primeiro arquivo com fragment desatualizado encontrado.

### Added — 3 testes novos (TDD)

- `test_init_creates_agents_md_for_multi_agent` — AGENTS.md existe + tem markers.
- `test_init_agents_md_fragment_mirrors_claude_md` — fragment em CLAUDE.md == fragment em AGENTS.md.
- `test_init_agents_md_is_idempotent` — segundo init não duplica.

Suite full: 1063 passed (1060 → 1063).

### Bumped

- `uvx plugadvpl@0.16.0` → `uvx plugadvpl@0.16.1` nas 26 skills.
- `plugin.json` / `marketplace.json` → 0.16.1.

## [0.16.0] - 2026-05-29

### Added — Interop com Sonar TOTVS oficial (`sonar_rules` em `lint`)

Cada lint finding agora carrega o ID Sonar oficial TOTVS (`BG1000`, `CA1004`, …) quando há equivalência no catálogo `sonar-rules.engpro.totvs.com.br` (referenciado pelas skills oficiais [`totvs/engpro-advpl-tlpp-skills`](https://github.com/totvs/engpro-advpl-tlpp-skills)). Quem já roda Sonar no CI reconhece o finding pelo ID oficial; quem não roda continua usando nosso `regra_id` interno.

```bash
plugadvpl lint --regra SEC-001 -f json
# [
#   {
#     "arquivo": "WSReg.tlpp",
#     "regra_id": "SEC-001",
#     "sonar_rules": ["BG1000"]
#   }
# ]
```

**Convenção:** ID puro = equivalência forte; prefixo `~` = adjacente/parcial; `[]` = regra exclusiva nossa, sem equivalente Sonar oficial.

**10 regras mapeadas hoje** (de 40 totais):

- **Fortes:** SEC-001→`BG1000`, SEC-004→`CA2052`, MOD-001→`CA1004`
- **Adjacentes:** ENC-001→`~CA0000`; BP-008→`~CA2024`,`~CA2025`; SEC-003→`~CA1004`; SEC-005→`~CA2017`,`~CA2019`,`~CA2022`,`~CA2023`; MOD-004→`~CA1006`,`~CA2020`,`~BG1100`; PERF-001→`~CS1000`; SX-007→`~CA2022`,`~CA2023`

As 30 restantes seguem `[]` (cross-file SX, encoding cp1252, prefixo cliente, MVC, etc — especificidades nossas sem cobertura no Sonar oficial). Catálogo completo em [`cli/plugadvpl/lookups/lint_rules.json`](cli/plugadvpl/lookups/lint_rules.json).

100% offline, sem dependência do Sonar instalado. Mapeamento é só ponte de nomenclatura.

### Added — Schema v16 (migration 016)

`ALTER TABLE lint_rules ADD COLUMN sonar_rules TEXT DEFAULT '[]'`. Não-destrutivo em SQLite — registros antigos recebem o default. `seed_lookups()` re-popula a coluna no próximo ingest a partir do JSON.

`SCHEMA_VERSION` bumpou de `"15"` para `"16"`. Quem tem índice v15 vai reingerir transparente no primeiro `plugadvpl ingest` da v0.16.0 (migration roda automática).

### Added — `query.lint_query()` faz LEFT JOIN com `lint_rules`

Saída JSON/table/MD ganha a coluna `sonar_rules` automaticamente (renderer usa as chaves do dict). LEFT JOIN é defensivo: finding cuja regra sumiu do catálogo vira `[]` em vez de quebrar.

### Fixed — SessionStart hook não flagga mais fixtures como projeto ADVPL

Hook estava emitindo "Projeto ADVPL detectado" toda vez que o repo tinha `.prw`/`.tlpp` em pastas convencionalmente não-projeto: `docs/`, `tests/`, `fixtures/`, `examples/`, `samples/`, `gaps/`, `marketing/`. Em meta-repos (tipo o próprio plugadvpl) e em repos Protheus com `docs/` contendo samples, o ruído era constante.

Adicionado ao `SKIP_DIRS` do `hooks/session-start.mjs`. Em projetos reais o código fica no root, em pasta de cliente (`customizado/`, `ABCFAT/`, `XYZ/`) ou em `src/` — nenhuma dessas convenções auxiliares.

### Added — 8 testes novos (TDD)

- 2 em `TestLintQuery` (`test_lint_query_exposes_sonar_rules_when_populated`, `test_lint_query_returns_empty_list_when_sonar_rules_unset`).
- 2 em `test_lint_catalog_consistency` (`test_strong_sonar_mappings_present` congela os 3 fortes; `test_sonar_rules_format_valid` valida regex `~?[A-Z]+[0-9]+(-[0-9]+)?`).
- 5 em `tests/integration/test_session_start_hook.py` cobrindo auxiliary dirs vs projeto real, via subprocess `node hooks/session-start.mjs`.

Suite full: 1060 passed.

### Fixed — CI ruff format + env Windows no hook test

- `ruff format` quebrou a tupla `cols=[…]` em `query.py` em 8 linhas (uma por item) — padrão do projeto.
- `_run_hook` em integration tests passava `env={CLAUDE_PROJECT_DIR, PATH}` apenas. Windows precisa de `SYSTEMROOT`/`USERPROFILE`/`APPDATA` pra node inicializar. Sem essas, `node` retorna stdout vazio silenciosamente. Agora herda `os.environ` inteiro.

### Bumped

- `uvx plugadvpl@0.15.0` → `uvx plugadvpl@0.16.0` nas 26 skills.
- `plugin.json` / `marketplace.json` → 0.16.0.

## [0.15.0] - 2026-05-27

### Added — `--confirm-prod` no `tq` + flag `is_prod` no `Server`

Guarda contra restart acidental em servers de produção. Fluxo:

```bash
plugadvpl compile --mark-prod prd-cliente-x         # marca uma vez
plugadvpl tq --use-server prd-cliente-x             # ERRO: pede --confirm-prod
plugadvpl tq --use-server prd-cliente-x --confirm-prod   # ok
plugadvpl compile --no-prod prd-cliente-x           # desmarca
```

- Campo novo `is_prod: bool = False` no `Server` dataclass. Default
  preserva backwards-compat com registry existente.
- `--dry-run` no `tq` continua funcionando sem `--confirm-prod` (preview
  não causa side-effect, então não precisa de guarda).
- `compile --list-servers` agora mostra marcador `PROD` ao lado do nome
  (junto com `*` de default).

Lock file pra prevenir concurrent runs foi descartado: lock local não
prevenia concurrent de 2 máquinas, e `--confirm-prod` cobre o caso real
(acidente, não corrida). Ver [comment de fechamento da issue #5](https://github.com/JoniPraia/plugadvpl/issues/5#issuecomment-4553802738).

### Added — 7 testes integration novos

- 4 em `TestTqConfirmProd`: PROD sem flag erra; `--dry-run` ignora PROD;
  non-PROD não pede flag; `--confirm-prod` libera execução real.
- 3 em `TestMarkProd`: `--mark-prod` seta True; `--no-prod` reseta;
  server inexistente erra com hint.

Suite full: 1051 passed (1044 → 1051).

### Bumped

- `uvx plugadvpl@0.14.1` → `uvx plugadvpl@0.15.0` nas 26 skills
- `plugin.json` / `marketplace.json` → 0.15.0

## [0.14.1] - 2026-05-27

### Changed — Hints acionáveis quando `tq` falha

Antes, falha de healthcheck mostrava só `healthcheck timeout após 60s (12
tentativas)` na coluna `error`. Agora o `next_steps` lista o que verificar:

```
healthcheck timeout em 127.0.0.1:8019 após 60s
verifique console.log do AppServer — build pode estar demorando ou erro de boot
--port 8019 aponta pra porta REST correta? (server.port=1234)
build lento? aumente --timeout 60 → --timeout 120
```

Mesmo padrão pra `restart_cmd` que retorna exit non-zero: aponta que o
usuário deve rodar manual + cita o cmd configurado. Reduz pingback quando
o tq falha em ambiente novo (porta REST diferente do TCP do advpls, build
7.00.x que demora >60s pra subir REST).

### Added — Skill `/plugadvpl:deploy`

Wrapper orquestrador que encadeia [`/plugadvpl:compile`](skills/compile)
→ [`/plugadvpl:tq`](skills/tq) → smoke opcional. Sem subcomando CLI novo
— é o agente seguindo o playbook do `compile --all-envs <fonte> && tq
--use-server <srv>` com pre-flight, hints de erro e tabela de
troubleshoot.

Caso de uso: depois de editar `.tlpp`/`.prw`, o agente roda `/plugadvpl:deploy
<fonte>` e tem o ciclo completo (compile com erro aborta antes do
restart; `&&` garante isso).

### Bumped

- `uvx plugadvpl@0.13.x` → `uvx plugadvpl@0.14.1` nas 26 skills
- `plugin.json` / `marketplace.json` → 0.14.1

## [0.14.0] - 2026-05-27

### Added — `plugadvpl tq` (Troca Quente MVP local)

Restart do AppServer Protheus + healthcheck HTTP, automatizando o passo
manual que ainda existia depois do `compile --all-envs` (`restart-totvs.bat`
+ curl loop até voltar). Tipicamente usado encadeado:

```bash
plugadvpl compile --use-server Local --all-envs <fonte> && \
plugadvpl tq --use-server Local
```

Componentes:

- Campo novo `restart_cmd` no `Server` dataclass do registry global. Default
  `""`, backwards-compat com servers existentes.
- `plugadvpl compile --set-restart-cmd <server> --cmd "<cmd>"` — flag nova
  pra configurar o cmd no registry. Validação: `--set-restart-cmd` sem
  `--cmd` erra com mensagem clara.
- `plugadvpl tq` — novo subcomando. Flags: `--use-server`, `--timeout`
  (default 60s), `--no-healthcheck`, `--dry-run`.
- Healthcheck via `http.client.HTTPConnection` (GET `/`) considera AppServer
  up só quando responde HTTP 200/401/404. TCP-only daria false positive
  cedo demais (porta abre antes do REST estar pronto na build 7.00.x).
- 5xx no healthcheck NÃO conta como up — continua tentando até timeout.

16 testes novos (8 unit no `tq.py` + 5 integration do subcomando + 3
integration do `--set-restart-cmd` no `test_cli_compile.py`). Spec e plano
em `docs/superpowers/specs/` e `docs/superpowers/plans/`.

Escopo MVP cortou versionamento de RPO, edição de `appserver.ini` e
rollback automático — fica pra issue [#5](https://github.com/JoniPraia/plugadvpl/issues/5)
quando precisar da versão robusta pra produção.

### Added — `plugadvpl compile --all-envs`

Compila o(s) fonte(s) pra **todos** os environments cadastrados no
`--use-server <nome>`, em sequência, com saída anotada por env.

Caso real: durante o smoke do `coletadb.tlpp` v1.0.3 contra Protheus
local, descobri que `plugadvpl compile --use-server Local` mandava o
RPO pro env padrão (`protheus` → `apo/custom.rpo`), mas o REST do
AppServer roda no env `protheus_rest` (`apo_rest/custom.rpo`). RPO
ficava desatualizado e o smoke continuava executando código antigo
até eu copiar `apo/custom.rpo` → `apo_rest/custom.rpo` manualmente.

Agora:

```bash
plugadvpl compile --use-server Local --all-envs docs/reference-impl/coletadb.tlpp
# compila pra cada env do server.environments
# saida tem coluna "env" pra ver onde foi
```

Validações:
- `--all-envs` requer `--use-server <nome>`.
- `--all-envs` é mutuamente exclusivo com `--use-environment`.
- Server com 1 env emite warning ("degenera pra compile único") mas roda.
- Exit code = max(exit_code de cada env) — falha em qualquer env quebra
  a invocação inteira.

3 testes integration novos cobrindo as 3 validações.

## [0.13.1] - 2026-05-24

Release de docs + skills + hash_algo no cliente REST. Sem mudanças no
schema do índice — `uv tool upgrade plugadvpl` é seguro.

### Added — Cliente `coletadb_client.py` suporta `hash_algo` + `hash_partial`

Servidor `coletadb.tlpp` v1.0.3 passou a emitir `hash` + `hash_algo` +
`hash_partial` no manifest (porque algumas builds Protheus não têm
`Sha2_256`). Cliente Python agora:

- Lê os 3 campos novos em `BundleFile`.
- Escolhe `hashlib.new(algo)` (sha256 | sha1 | md5) na verificação do
  download.
- Quando `hash_partial=True`, hasheia só os **primeiros 65535 bytes** pra
  casar com `MemoRead` truncado do server (sem streaming).
- Mantém fallback pro campo legado `sha256` (servers v1.0.x).
- Se nenhum hash vier, pula validação silenciosamente.

6 testes unitários novos cobrindo sha1/md5/partial/legacy/empty.

### Fixed — Docs desatualizadas pós-v0.13.0

- `skills/ingest-protheus/SKILL.md`: tabela "11 SX padrão (MVP)" virou
  "21 tabelas (cobertura 100%)". Roadmap marcou Fase 4b como completed.
- `docs/reference-impl/README.md`: seção "O que extrai" expandida pros
  21/21 + nova seção "Hash do bundle (v1.0.3+)" documentando os campos
  novos do manifest.

### Fixed — `docs/reference-impl/coletadb.tlpp` v1.0.3 (issue #9, 3 bugs)

Três bugs reportados pela IA da fábrica @tbarbito após smoke ponta-a-ponta
contra Protheus 7.00.240223P. Versão do reference-impl: **1.0.1 → 1.0.3**
(v1.0.2 intermediário trocou Sha2_256 por MemoRead+Sha2_256, mas smoke
local provou que essa build não tem `Sha2_256`/`HashStr`/`tHash` —
v1.0.3 adicionou fallback ordenado pra `Sha1`/`MD5` + metadata `hash_algo`).

- **`HashSha256Arquivo` → `HashArquivo` (bug #3):** v1.0.1 passava `cPath`
  literal pro `Sha2_256(cStr, nFmt)` que espera **conteúdo** como input.
  Smoke local revelou problema mais profundo: build 7.00.240223P **não
  tem `Sha2_256`** (nem `HashStr`/`tHash`) — só `Sha1`/`MD5`/`CRC32`.
  v1.0.3 trocou função pra `HashArquivo(cPath)` retornando
  `{ hash_hex, algo }` com fallback ordenado: Sha2_256 → Sha1 → MD5.
  Manifest agora emite `hash` + `hash_algo` + `hash_partial` (flag pra
  arquivos > 64KB onde `MemoRead` trunca). Campo legado `sha256` mantido
  por compat: vazio se algo != sha256, populado caso contrário.
  Validado em smoke: 21/21 arquivos com `hash` sha1 (40 chars hex) +
  `hash_partial=true` nos 11 arquivos maiores que 64KB.
- **`DiretorioBundle` (bug #4):** path separator hardcoded `\` em qualquer
  SO. Em AppServer Linux o `bundle_dir` saía `\temp\xxx\` e o cliente
  Python tinha que normalizar. Fix: detecta SO via `IsSrvUnix()`, usa `/`
  em Linux + normaliza separadores misturados no `cBase` passado pelo
  caller.
- **`InventarioCarregar` (bug #5):** false positive quando `threshold`
  alto (ex: 999999 em healthcheck) filtrava todas as tabelas — mensagem
  enganosa "Falha ao carregar inventario. Verifique acesso ao banco"
  apesar do DB estar OK. Fix: distinção `Nil` (falha real de TOPCONN/DBMS)
  vs `{}` (carregou ok mas threshold filtrou tudo). `ColetaCoreExecutar`
  só aborta no `Nil`; no `{}` apenas avisa "bundle será parcial" e segue.
  Adicionado `ErrorBlock + BEGIN SEQUENCE` na query do catálogo pra
  capturar exceptions de TOPCONN (catálogo sem permissão, conexão caiu).

**Bug "Postgres ENCODE syntax inválida"** (issue #9 item 2) era falso
alarme — código usa `substring(... FROM N FOR M)` (Postgres tem sintaxe
`FROM/FOR` sem vírgulas internas) + `encode(blob, 'escape')` com vírgula
correta. Reporter leu errado a sintaxe.

### Fixed — Gotchas reais do smoke COLETADB.tlpp incorporados nas skills

Quatro lições do smoke ponta-a-ponta contra Protheus 7.00.240223P (Docker
oficial 2025) que custaram horas de debug e que estavam ausentes (ou erradas)
nas skills. Code generation futura agora alerta sobre cada uma:

- **`SetHeaderResponse` → `SetKeyHeaderResponse`** (`advpl-webservice`):
  build 7.00.240223P retorna erro críptico "expected J->C" e HTTP 500 sem
  stack ao usar `oRest:SetHeaderResponse(k,v)` / `::SetHeaderResponse(k,v)`.
  Correta é a variante **com `Key` no meio** (`SetKeyHeaderResponse`).
  SKILL.md tabela + seção CORS + `reference-rest.md` exemplos corrigidos.
- **`@Post`/`@Get` só funciona com `User Function`** (`advpl-webservice`):
  decorar `Static Function` registra o endpoint mas `oRest` chega `Nil` →
  HTTP 500 silencioso. `Method` de classe nem registra (404). Workaround
  documentado: User Function thin wrapper delega pra Static.
- **`Begin Sequence / Recover` precisa de `ErrorBlock({|e| Break(e)})`**
  (`advpl-debugging`): exceptions nativas (TOPCONN, REST tlpp, MemoRead
  Linux) **não disparam Recover sozinhas** — borbulham acima dele e
  derrubam a thread. Pattern correto com guard/restore documentado na nova
  seção 13. Alerta também sobre `RECOVERY USING` (erro de sintaxe — o
  correto é `RECOVER USING` sem o Y).
- **`function` lowercase rejeitado em build 7.00.x** (`advpl-tlpp`):
  compilador antigo só aceita `Function`/`User Function`/`Static Function`
  capitalizados, mesmo com `tlpp-core.th` incluído. Tabela de compat por
  build adicionada.

### Added — Skill `advpl-tlpp-named-params`

- Nova skill dedicada documentando **named arguments** em chamadas TLPP via
  operador **`=`** (igualdade). Inclui requisitos de versão (AppServer
  20.3.2.0+ para funções/métodos, 24.3.1.0+ para `Classe():New()`), regras
  de mistura posicional + nomeado, fronteira TLPP→ADVPL, e diretrizes de
  refactor de `Static Function` legada.
- Cross-ref recíproca com [[advpl-tlpp]] e seção 2.3 de `reference.md`.

### Fixed — Documentação TLPP

- `skills/advpl-tlpp/SKILL.md`: separa "tipagem opcional e defaults na
  assinatura" (`numeric n := 0`) de "named args na chamada" (`f(n=10)`) —
  antes a seção misturava os dois conceitos.
- `skills/advpl-tlpp/reference.md` seção 2.3: corrige operador errado
  (`:` virou `=`), adiciona versões mínimas de AppServer, exemplos de
  mistura posicional + nomeado, construtor de classe, fronteira `.tlpp`/
  `.prw`, comparativo e integração REST tlppCore.

## [0.13.0] - 2026-05-24

### Added — Universo 6 (Workflow) + Universo 8 (Menus): cobertura final 21/21 CSVs

Fecha a absorção completa do bundle COLETADB.tlpp v1.0.1. Plugin agora
ingere **TODOS** os 21 CSVs (v0.11.0: 11; v0.12.0: 15; **v0.13.0: 21**).

#### Universo 6 — Workflow (migration 014)

- **`schedules`** (16 cols): agendamentos do scheduler interno
  (XX0/XX1/XX2, com recorrência decodificada pelo COLETADB). PK `codigo`.
  Campos humanos: `tipo_recorrencia` (Diario/Semanal/Mensal/...),
  `detalhe_recorrencia`, `intervalo_hh_mm`, `recorrencia_raw` (debug).
- **`jobs`** (5 cols): parse recursivo de `appserver*.ini`. PK composta
  `(arquivo, sessao)`. Index em `rotina_main`.

#### Universo 8 — Menus (migration 015, 6 tabelas relacionais)

- `mpmenu_menu`: menus raiz (SIGAFAT, SIGAEST, ...)
- `mpmenu_function`: funções ADVPL referenciadas
- `mpmenu_item`: items hierárquicos (FK menu + self-FK pai)
- `mpmenu_i18n`: descrições traduzidas (PT/ES/EN)
- `mpmenu_key_words`: palavras-chave de busca
- `mpmenu_rw`: leitura/escrita por idioma

`SCHEMA_VERSION` bumped 13 → 15.

CSVs MPMENU usam `R_E_C_D_E_L_` (vs `D_E_L_E_T_` das SX) — helper
`_row_is_deleted_recnod()` adicionado.

### Validation

Smoke real contra Protheus 7.00.240223P:
- SX padrão: **461.956 rows**
- SX extras: 5.181
- Workflow: 0 (base sem agendamentos)
- **Menus: 66.098 rows** (12.589 items + 7.549 funcs + 37.767 i18n)

JOIN cross-table validado — top funções por items: EDAPP (58), WFC002 (38), MATA020 (32).

Suite full: 1015 passed.

### Use cases destravados

```sql
-- Em qual menu aparece a função X?
SELECT m.nome, mi.item_id_legado
FROM mpmenu_function mf JOIN mpmenu_item mi ON mi.id_funcao = mf.id
JOIN mpmenu_menu m ON m.id = mi.id_menu WHERE mf.funcao = 'MATA020';

-- Qual rotina está agendada pra rodar diariamente?
SELECT codigo, rotina, hora_inicio FROM schedules
WHERE tipo_recorrencia = 'Diario' AND status = '1';

-- Quais jobs chamam HTTP_START?
SELECT arquivo, sessao FROM jobs WHERE rotina_main = 'HTTP_START';
```

### Cobertura final 21/21 CSVs do bundle COLETADB

| | v0.11.0 | v0.12.0 | **v0.13.0** |
|---|---|---|---|
| SX padrão (11) | ✅ | ✅ | ✅ |
| SX extras (3) + RECORD_COUNTS | ❌ | ✅ | ✅ |
| SCHEDULES + JOBS | ❌ | ❌ | ✅ |
| MPMENU (6) | ❌ | ❌ | ✅ |
| **Total** | **52%** | **71%** | **100%** ✓ |

## [0.12.0] - 2026-05-24

### Added — U5b: XXA/XAL/XAM + RECORD_COUNTS do bundle COLETADB

Estende o `ingest-protheus` pra absorver 4 dos 10 CSVs extras que o
`COLETADB.tlpp` v1.0.1 emite além dos 11 SX padrão. Cobertura sobe de
**11/21 → 15/21 CSVs** do bundle. Resta MPMENU (6) + SCHEDULES + JOBS
pra Universos 6/8 (releases futuras).

Migration nova `013_universo2_extras.sql` cria 3 tabelas SQLite com
chave composta `WITHOUT ROWID`:

- **`dominios`** (de XXA.csv) — Tabela de Domínios hierárquicos
  (DOM/CDOM com 3 idiomas + tipo). PK `(dominio, cod_dominio, sequencia)`.
  Diferente do SX5 (genéricas), XXA tem domínios estruturados —
  cada DOM pode ter N CDOM com descrição em PT/ES/EN.
- **`classificacoes_lgpd`** (de XAL.csv) — Catálogo master LGPD de
  tipos de dado sensível. Ex: id=501 desc="Nome", id=502 desc="CPF".
  PK `(filial, classificacao_id)`.
- **`anonimizacao_campos`** (de XAM.csv) — Mapa de campos a anonimizar
  com FK pra `classificacoes_lgpd` via `classificacao_id`. Inclui
  justificativa, módulo, alias, flag `em_uso`. PK `(filial, alias, campo)`.

**`RECORD_COUNTS.csv`** não cria tabela nova — popula `tabelas.num_rows`
(coluna placeholder existente desde migration 002). Match por prefix
de 3 chars do nome físico (ex: `SA1010` → alias `SA1`), agregando
multi-empresa. Tabelas non-Protheus (TOP_/SYS_/MP_/TPH) filtradas.

### Changed

- `_SX_INGEST_PLAN` (CSV path) ganha 3 entries: xxa.csv, xal.csv, xam.csv
- `_PARSER_BY_FILE`, `_PK_COLS_BY_TABLE`, `_META_KEY_BY_TABLE` estendidos
- `_MVP_TABLES` (REST path) inclui XXA, XAL, XAM, RECORD_COUNTS
- `SCHEMA_VERSION` bumped 12 → 13

### Validation

Smoke real contra Protheus 7.00.240223P (base local com Docker MSSQL,
COLETADB.tlpp v1.0.1 deployed):

- `ingest-protheus --modo completo --threshold 0` → **395.858 SX rows**
- `dominios`: 49 rows
- `classificacoes_lgpd`: 20 rows
- `anonimizacao_campos`: **5.112 rows**
- `tabelas.num_rows` populado em 69 tabelas (top: SX5=11.682, SYD=10.338, CC2=5.507)

Suite full: **1017 passed**, 2 skipped (real-advpls smoke), zero regressão.

### Use cases destravados

- Queries de LGPD: "quais campos da SA1 estão marcados pra anonimizar?"
- Queries de domínio: "que valores aceita o campo X que tem XXA_DOM='Y'?"
- Priorização por volume: "top 20 tabelas com mais rows pra revisar primeiro"

### Pendente pra Universos futuros

- **U6 (Workflow):** SCHEDULES (agendamentos + recorrência decodificada)
  + JOBS (parse recursivo de `appserver*.ini`)
- **U8 (Menus):** MPMENU completo (6 tabelas: MENU/FUNCTION/ITEM/I18N/
  KEY_WORDS/RW), cross-link com fontes e PEs

## [0.11.0] - 2026-05-22

### Added — U5 Live Protheus Inspector — `ingest-protheus` via REST

Novo comando `plugadvpl ingest-protheus` que substitui o workflow CSV manual do
`ingest-sx` por **dump ao vivo via REST API** do `COLETADB.tlpp` instalado no
AppServer. Convive com `ingest-sx` — quem não tem COLETADB continua usando CSV.

Workflow do extrator (bundle pattern):

1. `POST /coletadb/run` — servidor gera CSVs locais em `\temp\<ts>_<uuid>\` e
   retorna manifest com paths, sizes, sha256 de cada arquivo
2. `POST /coletadb/file` — cliente baixa cada CSV em chunks de 4MB
   (binário via `octet-stream`, com `X-Total-Size`/`X-Chunk-Range` headers)
3. Cliente reassembly + verifica sha256 + chama `ingest_sx` no tmp local
   (reusa machinery existente — paridade funcional total com CSV path)

Auth via HTTP Basic (`[HTTPURI] Security=1` do AppServer) — mesmas credenciais
do `compile`, sem token separado. Resolução: `--user`/`--password` > env vars
`PROTHEUS_USER`/`PROTHEUS_PASS`.

Módulos novos:

- **`cli/plugadvpl/coletadb_client.py`** — cliente HTTP stdlib (urllib),
  retry exponencial em 5xx, paginação automática, sha256 verification,
  erros tipados (`ColetaDBError` com hint pro usuário)
- **`cli/plugadvpl/ingest_rest.py`** — adapter trivial reusando `ingest_sx`
  direto (~150 linhas, em vez das 340 da versão especulativa anterior).
  Filtra `_MVP_TABLES` (11 SX padrão); XXA/XAM/XAL + MPMENU/SCHEDULES/JOBS/
  RECORD_COUNTS ficam pra Fase 4
- **`cli/plugadvpl/parsing/sx_csv.py`** — refactor: extraídas 11 funções
  `normalize_sxN_rows` como API pública reutilizável (CSV path e REST path
  chamam o mesmo normalizer). Output bit-identico ao anterior — zero regressão

Reference impl em [`docs/reference-impl/coletadb.tlpp`](docs/reference-impl/coletadb.tlpp)
(1772 linhas, MIT, contribuição do @tbarbito via discussion #2 / issue #3).

Comando + flags:

```bash
plugadvpl ingest-protheus --endpoint http://protheus:8181/rest \
  --user admin --password "$PASS" \
  [--modo enxuto|completo] [--threshold 10] \
  [--base-dir \\temp\\] [--ini-dir <path>] \
  [--dry-run] [--timeout-run 300] [--timeout-file 60]
```

Skill `/plugadvpl:ingest-protheus` (wrapper Claude Code). Suite: +20 testes
(11 unit do client + 9 integration incluindo paridade funcional com `ingest_sx`).

### Documentation

- **`docs/coletadb-contract.md`** — contract canônico público, agnóstico de
  impl (qualquer servidor conforme funciona, não só o `.tlpp` específico)
- **`docs/reference-impl/README.md`** — guia de instalação do `coletadb.tlpp`
  no AppServer + config `[HTTPV11]`/`[HTTPURI]` + inventário do que extrai
- **`docs/superpowers/specs/2026-05-21-u5-ingest-protheus.md`** — spec
  aprovada antes da implementação (workflow research → spec → approval → code).
  Inclui Seção 5-bis com contract real validado contra `COLETADB.tlpp` real.

### Pendente para v0.12.0+ (Fase 4)

- `sx-drift` — compara DB local vs estado atual via REST, reporta mudanças
  em prod sem commit
- Suporte a XXA/XAM/XAL (migration 003) + MPMENU/SCHEDULES/JOBS/RECORD_COUNTS
- Auto-install do COLETADB via `plugadvpl compile --install-server-component`
- Smoke test contra AppServer real com COLETADB compilado

## [0.10.0] - 2026-05-22

### Added — Auditoria de ambiente Protheus (PR #6 do @tbarbito)

- **`log-diagnose` — Monitor de log Protheus**: novo comando que ingere
  e diagnostica arquivos de log Protheus (console.log, error.log, profile.log,
  compila.log) contra **19 alert rules** + **93 correction tips** vindas da
  KB TDN oficial. Pipeline em 2 estágios: Stage 1 tokeniza eventos por 1 dos
  4 formatos de header reconhecidos (ISO+thread / THREAD ERROR PT-BR /
  `[DD/MM HH:MM:SS]` / `[SEVERITY]`); Stage 2 aplica rules em ordem reversa
  (eventos MAIS RECENTES primeiro) com short-circuit (1 finding por evento)
  e enriquece com correction tip cruzada de `log_tips`. Janela `--since` é
  relativa ao último timestamp do log (não wall clock). Categorias: database,
  thread_error, rpo, network, connection, service, rest_api, compilation,
  authentication, shutdown, lifecycle, application. Migration `012_log_diagnose.sql`
  adiciona 6 tabelas (`log_files`, `log_events`, `log_findings`, `log_rules`,
  `log_tips`, `log_categories`). Catálogos declarativos em
  `lookups/log_rules.json` (19 entries), `lookups/log_tips.json` (93 tips com
  URL TDN), `lookups/log_categories.json` (12 fallback tips). Enrichment:
  captura `ora_code`, `username`, `host` quando aparecem em Thread finished /
  Error ending thread. Skill `/plugadvpl:log-diagnose` + agent
  `advpl-log-investigator` + 66 testes unit (parser + ingest + diagnose).
- **`ini-audit` — Auditor de INI Protheus**: novo comando que ingere
  e audita arquivos `.ini` do ambiente Protheus (appserver, dbaccess,
  smartclient, tss, broker) contra **487 regras TDN-oficiais** filtradas por
  `tipo` + `role`. Pipeline `parse → ingest → audit` num único comando, cache
  via hash+mtime. Catálogo declarativo em `lookups/ini_rules.json` + 14 roles
  em `lookups/ini_roles.json`. Migration `011_ini_audit.sql` adiciona 6 tabelas
  (`ini_files`, `ini_sections`, `ini_keys`, `ini_audit_findings`, `ini_rules`,
  `ini_roles`). Detection kinds suportados: `value_eq` (com equivalência booleana),
  `value_in`, `value_neq`, `range_check`, `key_present`, `key_missing`, `regex`.
  Status `ok_with_note` quando o cliente documenta justificativa em comentários
  (`; intencional: ...`, `; cliente exige ...`). Skill `/plugadvpl:ini-audit` +
  agent `advpl-ini-auditor` + 69 testes unit (parser + audit engine).

Schema bump: 10 → 12 (migrations 011 + 012).

### Fixed — code review do PR #6 (commit b17b648)

6 fixes prioritários endereçados antes do merge:

- **Filtro `--severity` no log-diagnose** descartava o evento inteiro em vez
  de pular a rule de severidade não-pedida — rules de severidade alta com
  prioridade maior ficavam invisíveis. Fix: pré-filtra rules em
  `_load_rules` via SQL `AND severidade IN (?)` quando `severity_filter`
  está setado; `break` problemático removido. Teste de regressão
  `test_severity_filter_does_not_swallow_higher_priority_match`.
- **`print()` poluía stdout JSON** em warning de regex inválida no catálogo
  log_rules — `--format json` ficava com texto antes do JSON, quebrando
  parsers. Fix: `print(..., file=sys.stderr)`.
- **Body cap de eventos de log subido de 8KB → 32KB**: `THREAD ERROR` +
  call stack em produção passa de 8KB com 50-100 frames; truncar perdia
  a stack final. Constantes `_HEADER_MAX_CHARS=2000` e
  `_BODY_MAX_CHARS=32_000` no topo de `ingest_log.py`.
- **`max_lines=1M` cutoff silencioso** virou warning visível:
  `tokenize_events_with_meta()` retorna `(events, truncated_at_line)`,
  propagado via `ParsedLog.truncated_at_line` → `LogIngestResult.warnings`
  (separado de errors; ingest teve sucesso parcial). CLI mostra em amarelo
  no stderr.
- **`analyze_encoding` skip pra entrada str**: evita round-trip
  `encode('utf-8')` que sempre detecta utf-8/ascii em texto já decodificado.
  Retorna `IniEncodingInfo(detected="str")` direto.
- **`_format_message` reescrito com `re.sub` callback** em passada única:
  substituição sequencial de `{N}` corrompia se o capture group contivesse
  literalmente `{K}`. Teste cobre caso patológico.

## [0.9.5] - 2026-05-21

### Fixed - 5 itens pendentes do QA PERF 2026-05-18 (3 P1 + 2 P2)

Fechamento dos pendentes técnicos da auditoria de performance/robustez. Suite
continua em 853 passed; nenhum break de comportamento existente. Pega ao final
3 fixes factuais nas skills do dicionário SX que estavam em `[Unreleased]`.

- **#5 — Extensões inconsistentes entre scan/hook/docs**
  ([scan.py:11](cli/plugadvpl/scan.py#L11), [session-start.mjs:10](hooks/session-start.mjs#L10)):
  hook ignorava `.apw` (web ADVPL) e docs listavam `.ptm`/`.aph`/`.ch` que
  nunca foram indexados (patch binário e includes). Alinhado tudo ao set
  canônico `.prw, .prx, .tlpp, .apw` (cli-reference, architecture, schema,
  README, skill ingest, hook).
- **#1 — `pool.map` materializava `list(...)` antes do primeiro write**
  ([ingest.py:843](cli/plugadvpl/ingest.py#L843)): em monorepos com 5-10k
  fontes, todo o resultado do parsing paralelo segurava em RAM antes do
  writer single-thread começar. Agora itera direto sobre o `pool.map`
  (preserva ordem, ao contrário de `as_completed`) — cada chunk é escrito
  enquanto outros workers continuam parseando. Teste de regressão smoking-gun
  detecta se alguém reintroduzir `list()` no futuro
  ([test_ingest.py](cli/tests/integration/test_ingest.py)).
- **#2 — `scan_sources` perdia silenciosamente fontes com basename duplicado**
  ([scan.py:65-71](cli/plugadvpl/scan.py#L65)): schema usa basename como PK; sem
  aviso, `mod1/MATA010.prw` × `mod2/MATA010.prw` resultava em um dos dois
  silenciosamente descartado. Adicionado `scan_sources_full()` retornando
  `(files, collisions)`; ingest emite stderr WARN com contagem, persiste em
  `meta.basename_collisions`, e `doctor` ganha check `basename_collisions`
  que reporta `warn` com exemplos. Filtra falso positivo de Windows FS
  case-insensitive (mesma pasta, casing diferente = mesmo arquivo).
- **#3 — `validate_plugin.py` não cobria comandos novos**
  ([scripts/validate_plugin.py](scripts/validate_plugin.py)): validador
  hardcoded 13 comandos antigos (init/ingest/find/...) e deixava CI passar
  com wrapper faltando pros 12 comandos novos (workflow/execauto/trace/
  metrics/hotspots/cobertura-doc/gatilho/impacto/sx-status/ingest-sx/compile/
  edit-prw). Refatorado pra introspecção do Typer (`app.registered_commands`
  + `app.registered_groups`) — qualquer comando novo entra no escopo
  automaticamente. Adicionado check de drift de versão: pin `uvx
  plugadvpl@X.Y.Z` nos skills bate com `plugin.json:version`; `marketplace.json:
  plugins[0].version` bate com `plugin.json:version`; hook não tem pin
  hardcoded em chamada real (regressão do fix v0.9.2). Validador
  imediatamente detectou e corrigiu drift de 22 skills pinadas em
  `0.6.1` enquanto plugin está em `0.9.5`.
- **#4 — `impacto` em fontes sem boundary check**
  ([query.py:701-749](cli/plugadvpl/query.py#L701)): SQL `LIKE '%A1_COD%'`
  retornava substring FP como `BA1_CODEMP`, `A1_CODFAT`, `DA1_CODPRO`.
  Output ficava >100KB em campos de nome curto/comum (#3 do QA V3 já tinha
  corrigido em SX3/SX7 mas fontes ficou de fora). Fix: SQL LIKE prefiltra
  (cheap), Python `_word_boundary_re` descarta FP, snippet é construído ao
  redor do match REAL (não da primeira ocorrência substring), output marca
  `match_kind: "boundary"`.

### Skills (dicionário SX — factuais vs schema real)

Validações cruzadas com [Terminal de Informação](https://terminaldeinformacao.com/wp-content/tabelas/sx3.php)
e TDN TOTVS.

- **`advpl-dicionario-sx/reference.md`** — 14 bugs corrigidos:
  - **SX1**: `X1_PRESEL` é numérico (não CHAR); `X1_GSC` aceita `R` (Range/Radio); `X1_TIPO` aceita `M` (Memo). +5 colunas (`X1_HELP`/`PICTURE`/`GRPSXG`/`IDFIL`/`PYME`).
  - **SX2**: `X2_PREF` **não existe** — prefixo é derivado de `X2_CHAVE`. `X2_DELET` é NUMERIC (contador), não CHAR. +13 colunas físicas (`X2_MODOUN`/`MODOEMP`/`UNICO`/`DISPLAY`/`MODULO`/`TAMFIL`/`TAMUN`/`TAMEMP`/...).
  - **SX3**: `X3_USADO` é bitmap `varchar(120)` de **módulos do ERP**, não empresas/filiais (use `X3_CONDSQL` p/ isso). `X3_OBRIGAT` é bitmap `varchar(8)` controlado por API (`"S"` direto via SQL é ignorado em v12.1.7+; use `X3_VALID := "!Empty(M->CAMPO)"`). `X3_TRIGGER` é `varchar(1)`, valor `"S"` ou vazio (não lógico no banco). `X3_GRPSXG` (não `X3_GRUPO`) é a coluna física do grupo SXG. Documentadas funções `X3TreatUso()`/`X3TreatObrigat()`/`X3TreatReserv()`.
  - **SX6**: `X6_ACTIVE` documentado (parâmetro inativo é silenciosamente ignorado em releases recentes). +`X6_VALID`/`X6_INIT`/`X6_DEFPOR`/`X6_EXPDEST`.
  - **SX7**: `X7_SEQUENC` com C final (não `X7_SEQUEN`). `X7_CONDIC` única (não `X7_CONDIN` + `X7_CONDOUT` separadas). Tipo `"E"` (Estrangeiro) **não existe** no padrão atual — só `P`/vazio (Primário) e `X` (Posicionamento). `X7_ARQUIVO` não existe — alias é derivado do prefixo de `X7_CAMPO`.
  - **SX9**: `X9_IDENT` documentado (parte da chave, essencial pra múltiplos laços entre as mesmas tabelas). `X9_ENABLE` documentado (relacionamento desabilitado é ignorado sem warning). +`X9_PROPRI`/`USEFIL`/`CONDSQL`.
  - **SXA**: campos da SX3 vinculam à pasta via `X3_FOLDER` (casa com `XA_ORDEM`), não `X3_GRUPO`.
  - **SXB**: tipos `6`/`7`/`8`/`9` mencionados; `XB_WCONTEM` documentado; nota sobre `XB_ALIAS` ser `CHAR(6)` (alias `"ZPROD01"` seria truncado).
  - **SXG**: colunas reais `XG_SIZE`/`XG_SIZEMAX`/`XG_SIZEMIN` (não `XG_TAMANHO`/`XG_DECIMAL`/`XG_TIPO`). `XG_DESCRI` no banco físico — `XG_DESCRIC` aparece só em CSV export do Configurador (dualidade documentada).
  - **SIX**: coluna real é `DESCRICAO` (não `DESCR`). +`PROPRI`/`F3`/`NICKNAME`/`IX_VIRTUAL`/`IX_VIRCUST`.
- **`advpl-dicionario-sx/SKILL.md`** — bloco de campos SX3 reescrito com tipos/tamanhos reais; seção "Customizando campo sem mexer no fonte" reflete bitmap controlado por API; `X7_TIPO` removida menção a tipo `S`/`E` inexistentes.
- **`advpl-dicionario-sx-validacoes/SKILL.md`** — regra SX-009 reformulada removendo `X3_OBRIGAT='X'` (uppercase incorreto) com disclaimer do bitmap moderno.
- **`advpl-debugging/SKILL.md`** — "campo não aparece" reformulado: bitmap `varchar(120)`, não 18 chars; menciona `X3_CONDSQL` como local de empresa/filial; aponta `FwPutSX3()`/clonagem como caminho seguro.

### Added

- **`advpl-dicionario-sx/reference.md` §15 — Cookbook SQL pra criar campo customizado**:
  regra de ouro (clonar `X3_USADO`/`X3_RESERV` via `INSERT...SELECT`, nunca
  inventar bitmap), workflow 3 fases (`ALTER TABLE` + `INSERT` + invalidar
  cache), checklist pré-INSERT (15 itens), armadilhas frequentes (7 sintomas →
  causa → fix), template de QA visual via `UNION ALL` comparando NOVO vs TPLT.
  Generalizado (sem detalhes de ambiente específico); banner inicial reforça
  que `FwPutSX3()`/Configurador continuam sendo o caminho oficial TOTVS.

### Technical

- 22 skills bumpados de `uvx plugadvpl@0.6.1` → `@0.9.5` (drift caçado pelo
  validador novo).
- +5 testes de regressão: `test_ingest_parallel_streams_results_v0_9_5`
  (smoking-gun streaming), `test_doctor_basename_collision_warn_v0_9_5`,
  `TestScanSourcesFullCollisions` (4 testes), `test_impacto_fontes_boundary_
  no_substring_v0_9_5`. Suite total: 853 passed.

## [0.9.4] - 2026-05-20

### Fixed - Install do plugin Claude Code falhava com "Permission denied (publickey)"

Bug reportado por usuário: `/plugin install plugadvpl` falhava com
`git@github.com: Permission denied (publickey)` mesmo com `~/.gitconfig`
limpo (sem `insteadOf`), `gh` configurado pra HTTPS e clone manual via
HTTPS funcionando do mesmo path de destino.

**Causa raiz:** `marketplace.json` usava `source.source = "github"` +
`source.repo = "JoniPraia/plugadvpl"`. Claude Code v2.1.x está deduzindo
URL `git@github.com:...` (SSH) ao invés de `https://github.com/...` desse
formato. Bug do Claude Code, mas dá pra contornar do nosso lado.

**Fix:** trocado pra `source.source = "url"` com URL HTTPS explícita —
mesmo padrão que outros marketplaces que funcionam (ex: superpowers):

```json
"source": {
  "source": "url",
  "url": "https://github.com/JoniPraia/plugadvpl.git"
}
```

Adicionado `"strict": true` também (mesmo padrão dos marketplaces que
funcionam — força validação no install).

Sem isso, qualquer usuário sem SSH key configurada no GitHub não consegue
instalar o plugin Claude Code, mesmo o repo sendo público.

### Note

Apenas mudança em `marketplace.json` — sem alteração em CLI, skills,
agents ou hooks. Bump pra forçar Claude Code detectar e oferecer
re-instalação com a config corrigida.

## [0.9.3] - 2026-05-20

### Changed

- Skill `advpl-webservice` reescrita e expandida (380 → 587 linhas) cobrindo
  WSRESTFUL vs notation (`@Get/@Post/...`) com benchmark de performance
  (~3× speedup do notation via accept layer C++ do Lobo-Guará), tabela de
  decisão "quando escolher cada", migration path 10 passos, requisitos
  precisos de versão (notation precisa AppServer 20+, REST-DOC precisa
  tlppCore 01.04.02 + AppServer 20.3.1.10) e pegadinhas separadas por
  abordagem.
- Novo `skills/advpl-webservice/reference-rest.md` (819 linhas, foco 100%
  em REST moderno): CRUD completo em ambas abordagens (Cliente/SA1),
  catálogos `oRest:*` e `::Self`, multi-tenancy detalhado, JWT/OAuth2 +
  endpoint built-in `/api/oauth2/v1/token`, REST-DOC/Swagger com
  `TLPP COMPONENT`, FWAdapterBaseV2, endpoints aninhados, paginação
  cursor-based, upload/download binário, consumo de APIs externas
  (`FwRest`/`HttpPost`/`TWsdlManager`), 22 pegadinhas testadas.
- `skills/advpl-webservice/reference.md` (SOAP/WSDL/UDDI legado) preservado
  intacto.

### Note

Bump só pra `marketplace.json` detectar versão nova e oferecer update do
plugin Claude Code (`/plugin update plugadvpl`). CLI Python continua igual
à v0.9.2 — sem mudanças de código, só docs/skills.

## [0.9.2] - 2026-05-19

### Fixed - 3 bugs HIGH descobertos na triagem de gaps/ antigos

Auditoria dos 6 docs antigos em `gaps/` (versões 0.4.3 → 0.7) contra v0.9.1
fechou 23/36 bugs já resolvidos (arquivados em `gaps/archived/`). Restavam 3
bugs HIGH ainda válidos, todos endereçados nesta release.

- **QA PERF #3 — métricas corrompidas silenciosamente em `--no-content`**
  ([cli/plugadvpl/ingest.py:319](cli/plugadvpl/ingest.py)): no modo privacy,
  `chunk_content=""` ia vazio pro DB E também era usado pra calcular
  CC/nesting → toda função tinha CC=1, nesting=0. Fix: separar
  `body_for_metrics` (sempre real) de `chunk_content` (vazio em --no-content).
  Métricas voltam a ser corretas mesmo escondendo o source do DB.
- **QA PERF #5 — Hook SessionStart pinned em `plugadvpl@0.3.1`**
  ([hooks/session-start.mjs:79](hooks/session-start.mjs)): plugin está em
  v0.9.x / schema v10, hook chamava CLI 3 schemas atrás → check-stale podia
  reportar incorreto ou falhar silenciosamente em queries novas. Fix: prefere
  `plugadvpl` do PATH (usuário instalou via `uv tool install`), fallback pro
  `uvx plugadvpl` sem pin (latest).
- **QA PERF #1 — `grep --mode literal` ignorava índice trigram FTS**
  ([cli/plugadvpl/query.py:558](cli/plugadvpl/query.py)): migration 001 cria
  `fonte_chunks_fts_tri` (FTS5 trigram), ingest popula, mas `grep_fts(mode=
  "literal")` fazia full table scan via `LIKE`. Fix: pattern ≥3 chars usa
  trigram MATCH como pré-filtro + `LIKE` confirmador (preserva
  case-sensitivity). Pattern <3 chars cai no LIKE puro (trigram não cobre).
  Fallback gracioso se trigram indisponível.

### Maintenance

- 6 docs `gaps/*.md` arquivados em `gaps/archived/` com README explicativo
  (bugs já resolvidos confirmados via grep + CHANGELOG + testes existentes).
- `gaps/PLUGADVPL_QA_TECNICO_PERFORMANCE_2026-05-18.md` agora é o roadmap
  natural da v0.10.0 (10/10 itens válidos: 3 HIGH endereçados aqui + 4 MED +
  4 LOW pendentes).

### Technical

- Testes: +3 regressão (`test_ingest_no_content_metrics_still_correct_v0_9_2`,
  `test_grep_literal_uses_trigram_v0_9_2`,
  `test_grep_literal_short_pattern_fallback_v0_9_2`). Suite total: 812
  passed.

## [0.9.1] - 2026-05-19

### Fixed - `--use-server + --mode appre` parou de exigir credencial

Fechando o último ⚪ do veredito v0.9.0 do usuário: "appre tecnicamente
exige cred mesmo a UX da mensagem tendo amortecido". appre é
pré-processador local, nunca conecta no AppServer — não tem razão pra
validar user/pass.

Agora:

```bash
# Funciona sem env var, sem keyring, sem nada:
plugadvpl compile --use-server local --mode appre fonte.prw
```

Validação de credencial mantida em `--mode cli` e `--mode auto`
(conservador: auto pode resolver pra cli se AppServer reachable).

### Technical

- `_apply_server_override` aceita `requested_mode: str = "auto"` e pula
  o bloco `resolve_credentials` quando mode explícito é `"appre"`.
- Injeção em `os.environ` (creds vindas do keyring) ganhou guard
  contra strings vazias.
- Teste regressão: `TestAppreSkipsCredentials.test_use_server_appre_runs_without_credentials`.

## [0.9.0] - 2026-05-19

### Added - Cofre nativo do OS pra credenciais (sem senha em env var toda sessão)

Usuário levantou gap: "como o cara informa senha de forma segura sem TDS
instalado, sem perder, mantendo segurança?". TDS-VSCode guarda token base64
no JSON dele — não é grande coisa. Indústria (`gh`, `az`, `git-credential-
manager`) usa cofre nativo do OS, é mais seguro. Adotado.

**Resolução em camadas (primeira encontrada vence):**

1. **Env var** (`$PROTHEUS_USER` / `$PROTHEUS_PASS`) — máximo controle,
   CI/CD-friendly, integra com 1Password CLI / vault / etc.
2. **Cofre do OS** — Win Credential Manager (DPAPI por usuário), macOS
   Keychain, Linux Secret Service (gnome-keyring / kwallet). Senha cifrada
   pelo OS, descriptografada on-demand pelo user logado.
3. **Erro com 2 caminhos didáticos** se nada achou.

Plugin **nunca grava senha em arquivo** — só o cofre nativo toca o byte.

### Comandos novos

- **`plugadvpl compile --set-credentials <server>`** — prompt seguro
  (`getpass`, sem ecoar), salva no cofre do OS. Service name:
  `"plugadvpl"`. Keys: `<server>:user` e `<server>:password`. Confirma a
  senha pra evitar typo.
- **`plugadvpl compile --clear-credentials <server>`** — remove do cofre,
  idempotente.
- **`plugadvpl compile --explain-config`** — JSON estruturado mostrando:
  - Ordem de precedência completa (resolve gap "sem doc explícita" da
    tabela de feedback do user)
  - De onde veio runtime.toml, server, credenciais (env vs keyring vs none)
  - Senha **redacted** (`<set>` / `<unset>`) — nunca vaza valor

### Changed

- `_apply_server_override` (cli.py) — substituiu `os.environ.get(...)` direto
  por `resolve_credentials()` com fallback ordenado. Quando creds vêm do
  keyring, são injetadas em `os.environ` só pro processo CLI (não vazam pra
  shell pai).
- Mensagem de erro quando faltam credenciais agora mostra **ambas as opções
  lado a lado** (`--set-credentials` E `export VAR`), com hint se keyring
  está indisponível no sistema.

### Technical

- Nova dependência: `keyring >=24` (~50KB, sem deps nativas obrigatórias,
  fallback gracioso em ambiente sem cofre — Linux server sem D-Bus retorna
  `keyring_available=False` em vez de crashear).
- Novo módulo `credentials.py`:
  - `CredentialResolution` dataclass imutável com `to_safe_dict()`
    (password redacted).
  - `resolve_credentials(server_name, user_env, password_env)` — função
    central, sempre retorna dataclass, nunca lança.
  - `set/get/clear_credentials_in_keyring` — wrappers que tratam backend
    instável (`Linux server sem D-Bus`) com `_try_import_keyring` defensivo.
  - `keyring_available()` — check público, detecta `NullBackend`/`FailKeyring`.
- Testes: +17 unit (`test_credentials.py` com `FakeKeyring` in-memory) +
  3 integration (`set→use→clear` cycle + `--explain-config` JSON shape).

### Migration

100% retrocompatível. Quem usa env var hoje continua igual. Pra migrar
pro cofre:

```bash
plugadvpl compile --set-credentials dev-local
# remove a env var do shell profile (~/.bashrc, $PROFILE)
plugadvpl compile --use-server dev-local <fonte.prw>  # ainda funciona
```

## [0.8.12] - 2026-05-19

### Added - `--probe-appserver host:port` (network mode, igual TDS-VSCode)

Usuário perguntou: "como o TDS-VSCode descobre a build só com host+port?".
Pesquisa em [totvs/tds-vscode](https://github.com/totvs/tds-vscode) revelou
que ele invoca o `advpls cli` (que o plugadvpl já chama!) com action
`validate`, mecanismo público documentado em
[tds-ls/TDS-cli-script.md](https://github.com/totvs/tds-ls/blob/master/TDS-cli-script.md).
Sem autenticação. Retorna build + flag SSL.

Antes (v0.8.11): `--probe-appserver` só aceitava path pra `protheus.log` —
inútil pra AppServer remoto ou usuário sem acesso ao filesystem do servidor.

Agora (v0.8.12): mesmo flag auto-detecta entre 2 modos:

- **`plugadvpl compile --probe-appserver 127.0.0.1:1234`** → network mode
  (novo, recomendado). Gera INI `[validate]` em tempdir, invoca `advpls cli`,
  parseia "Appserver detected with build version: X and secure: Y", limpa
  tempdir. Funciona via SSH tunnel, VPN, host remoto. Detecta SSL/TLS.
- **`plugadvpl compile --probe-appserver D:/TOTVS/protheus`** → log mode
  (v0.8.11, agora fallback). Útil quando AppServer está down ou versão Lobo
  Guara antiga não responde ao validate (issue tds-vscode#390).

Detecção via regex `^[\w.\-]+:\d+$` — paths Windows tipo `D:\TOTVS\...`
continuam casando o modo log (último `:` em path tem letras, não dígitos).
Edge case `host:1234` que também existe como path no FS → log mode ganha.

### Changed

- Output do `--probe-appserver` reescrito com passo-a-passo didático
  (`[1/3]` localizando binário → `[2/3]` invocando advpls → `[3/3]`
  parseando). Em falha, troubleshooting com comandos `Test-NetConnection` /
  `nc` + sugestão de fallback pro modo log.
- Na sucesso, output mostra comando pronto pra cadastrar o server (com
  build e secure já preenchidos pra colar no prompt do `--add-server` ou
  no JSON do `~/.plugadvpl/servers.json`).

### Technical

- Novo módulo `compile_probe.py`:
  - `NetworkProbeResult` (dataclass: host/port/build/secure/error/raw_output).
  - `probe_appserver_network(host, port, advpls_binary, timeout=20)` — sempre
    retorna dataclass, nunca lança exceção (composição amigável).
  - `is_host_port(target)` — detecção tolerante a paths Windows (FS check).
  - `_parse_validate_output` — regex pública pra build + secure.
- Testes: +18 unit (is_host_port, parse, build_ini, network probe com
  subprocess mockado incluindo timeout/FileNotFound/tempdir cleanup).

## [0.8.11] - 2026-05-19

### Fixed - 4 gaps reportados em uso real (v0.8.10)

Usuário rodou v0.8.10 em projeto real e mandou 4 bugs prioritizados.
Todos endereçados, com regressão.

- **Bug 1 (HIGH) — `--import-tds-servers` lia 0 campos úteis**:
  TDS-VSCode `~/.totvsls/servers.json` usa `buildVersion` (não `build`)
  e tem lista `includes` por server. Plugadvpl ignorava ambos →
  `--use-server` quebrava silenciosamente com build vazio. Corrigido
  em `compile_servers.import_from_tds_vscode`: aceita ambos os nomes
  de campo + persiste `includes` no novo `Server.includes`. Em
  `_apply_server_override`, includes do server são passados pra
  `CompileConfig` quando não há runtime.toml — permite zero-config
  total (sem TOML, sem variáveis hardcoded).
- **Bug 2 (MED) — `--probe-appserver` descobre build sem TDS-VSCode**:
  novo módulo `compile_probe.py` parseia `protheus.log` à procura da
  linha de boot (`* TOTVS - Build 7.00.240223P - Oct 3 2025`).
  Aceita path direto pro `.log` ou raiz Protheus (procura em
  `log/`, `bin/Appserver/log/`, etc). Imprime build pronto pra colar
  no `--add-server` ou em `[appserver].build` do runtime.toml.
- **Bug 3 (MED) — `[auth]` agora opcional no runtime.toml**:
  modo `appre` não conecta no AppServer → não precisa user/pass.
  Antes, `runtime_config.load` exigia a seção + validava env vars
  (mesmo quem só fosse rodar appre). Validação migrou pra
  `compile._build_ini_script` (chamado só em `mode=cli`). Seção
  pode ser omitida inteira; defaults `PROTHEUS_USER` / `PROTHEUS_PASS`
  preenchidos automaticamente. Template do `--init-config` agora
  documenta `[auth]` como opcional.
- **Bug 4 (LOW) — `edit-prw clean` pra limpar `.bak` acumulado**:
  ciclo stage→edit→commit cria 2 `.bak` por fonte. Em refactor
  grande viram dezenas. Novo subcomando varre pasta (ou arquivo
  único) e remove `.bak` correspondentes a fontes ADVPL (`.prw`,
  `.prx`, `.tlpp`, `.tlpp.ch`, `.ch`). Default exige confirmação;
  `--yes` skipa; `--dry-run` lista sem deletar. `.bak` de outros
  arquivos (ex: `.txt.bak`) preservados — escopo intencional.

### Added

- `plugadvpl compile --probe-appserver <path>` — discovery de build
  via log (bug 2).
- `plugadvpl edit-prw clean [target] [--yes] [--dry-run]` — limpeza
  em lote de `.bak` (bug 4).
- `Server.includes` no registry global de servers (bug 1) — inclui
  no JSON via `~/.plugadvpl/servers.json` quando vem do TDS-VSCode.

### Changed

- `runtime_config.load`: seção `[auth]` virou opcional. Env vars
  PROTHEUS_USER/PASS deixaram de ser validadas no load — validação
  agora em `compile._build_ini_script` com mensagem clara apontando
  o uso (`cli mode needs env vars set: X, Y`).
- Template do `--init-config` (`runtime.toml`) ganhou comentário
  explicando que `[auth]` só é necessário em `mode = "cli"`.

## [0.8.10] - 2026-05-19

### 🛡️ Warnings de Edit-PRW espalhados nos 5 pontos críticos

User questionou: "atualizou as skills e onde precisa? ou precisa refinar
mais?". Auditoria honesta achou 5 lugares que ainda não tinham o warning
sobre stage/commit. Todos corrigidos.

### Changed

- **Fragment CLAUDE.md do `plugadvpl init`** (`cli.py` §Encoding) reescrito
  de 4 linhas superficiais pra warning destacado + workflow stage/commit
  + quando NÃO precisa. Próximas instalações de plugadvpl em projeto novo
  já saem com o aviso no `CLAUDE.md` (lido pelo Claude em toda sessão).
- **Skill-chefe `plugadvpl-index-usage`** ganhou seção "Edit/Write em
  `.prw` cp1252 — ⚠️ OBRIGATORIO" com workflow 3 passos. Como é skill
  carregada antes de QUALQUER consulta, agente vê isso cedo.
- **Skill `advpl-refactoring`** §Workflow agora tem passo 2 explicitando
  stage/commit antes de Edit em massa (refactor envolve muito Edit por
  natureza — alto risco de corrupção).
- **README** ganhou callout `⚠️` no header (logo abaixo do tagline) +
  bullet pra `edit-prw` na tabela de skills.
- **`compile --doctor`** agora roda sample de até 20 `.prw` no `--root` e
  reporta quantos parecem cp1252. Quando encontra, adiciona check
  `edit_prw_safety` (informativo, não bloqueia) com hint pra usar
  stage/commit antes de Edit. Novo helper `_count_prw_cp1252()`.

### Notes

- 5 pontos atualizados nesta release. Resumo dos canais por onde o
  Claude descobre o workflow agora:
  1. **Memory automática** (`feedback_edit_prw_workflow.md`) — minha
     pessoa em qualquer sessão
  2. **Fragment CLAUDE.md** — qualquer agente em projeto que rodou `init`
  3. **Skill `plugadvpl-index-usage`** — skill-chefe carregada cedo
  4. **Skill `edit-prw`** — slash command operacional
  5. **Skill `advpl-encoding`** — política geral
  6. **Skill `advpl-refactoring`** — refactor envolve Edit pesado
  7. **`--doctor` proativo** — detecta `.prw` cp1252 no root e avisa
  8. **README** — callout visual logo no topo
- Suite continua **787 PASS** (mudanças foram textos + função
  informativa que não afeta exit code do doctor).

## [0.8.9] - 2026-05-19

### ✍️ `edit-prw stage/commit` + skill explícita pro workflow seguro de Edit em .prw cp1252

Reporter levantou problema crítico do workflow Edit do Claude Code em
`.prw` cp1252: Read/Edit tools são UTF-8 only → bytes acentuados (0x80-0xFF)
viram `�` no Read → Edit regrava arquivo inteiro em UTF-8 com `�` no lugar
dos acentos não-editados → **acentos não-editados ficam corrompidos**.

### Added

- **`plugadvpl edit-prw stage <arq>`** — atalho de
  `edit-prw save --from cp1252 --to utf-8`. Converte `.prw` cp1252 → utf-8
  ANTES do agente usar Read/Edit. Cria `.bak` automático com bytes
  cp1252 originais.
- **`plugadvpl edit-prw commit <arq>`** — atalho de
  `edit-prw save --from utf-8 --to cp1252`. Reverte a conversão DEPOIS das
  edições. Acentos novos digitados durante edição viram bytes cp1252
  corretamente.
- **Skill nova `/plugadvpl:edit-prw`** — slash command operacional que
  documenta o workflow obrigatório de 3 passos (stage → editar → commit),
  alternativas (PowerShell nativo) e quando NÃO precisa.
- **Memory persistida** `feedback_edit_prw_workflow.md` pro Claude seguir
  automaticamente em sessões futuras: detectar `.prw` no path antes de
  Read/Edit, rodar `stage`, editar, `commit`. Listado em `MEMORY.md`.

### Changed

- **Skill `advpl-encoding` §"Workflow correto antes de Edit"** reescrita
  com:
  - Warning visual destacando o PERIGO do Edit em cp1252 não-staged
  - Caminho A (stage/commit) como recomendado
  - Caminho B (PowerShell nativo) como alternativa pra mudanças mecânicas
  - Caminho C (restringir Edit a ASCII) explicitamente marcado como
    NÃO RECOMENDADO com motivo

### Tests

- **+2 testes integration** `TestEditPrwStageCommit`:
  - Round-trip stage→commit preserva bytes exatos (cp1252 → utf-8 → cp1252)
  - Stage cria backup `.bak` com bytes cp1252 originais
- **787 testes total** (era 785, +2).

### Notes

- Validado smoke real:
  - Bytes originais: `E7 E3 E7 E3` (cp1252)
  - Pós-stage: `C3 A7 C3 A3 C3 A7 C3 A3` (utf-8)
  - Pós-commit: `E7 E3 E7 E3` (cp1252 — idêntico)
- `save --from X --to Y` continua disponível pra conversões manuais
  genéricas. Stage/commit são apenas wrappers convenientes pro caso de
  uso mais frequente (cp1252↔utf-8 antes/depois de Edit).
- Memory feedback ativada — próximas sessões do Claude vão aplicar
  automaticamente quando user pedir Edit em `.prw`.

## [0.8.8] - 2026-05-19

### 🐛 4 bugs achados em smoke real de uso real (reporter externo)

Reporter testou v0.8.7 em uso real e reportou 4 bugs/quirks. Todos
reproduzidos e corrigidos com testes de regressão.

### Fixed

- **Bug 1 (CRITICAL silencioso) — ordem das flags**: typer com positional
  variadic `files: list[Path]` consumia flags `--mode`/`--includes`/etc
  como nomes de arquivo quando vinham DEPOIS do positional. Resultado:
  `plugadvpl compile FOO.PRW --mode cli` caía silenciosamente em
  `--mode auto → appre` sem includes, sem aviso. **Fix**: detector
  pré-execução em `compile_callback` checa se algum item de `files` está
  na lista de flags conhecidas (~20 flags do compile) e erra com exit 2
  + mensagem mostrando `❌ ERRADO`/`✓ CERTO`.

- **Bug 2 — `--includes` em appre falhava com C2090**: era sintoma do
  Bug 1. Reporter rodava `compile FOO.PRW --mode appre --includes <dir>`,
  `--includes <dir>` era engolido como files, advpls rodava sem `-I`,
  falhava com `PRTOPDEF.CH not found`. Resolvido junto com Bug 1
  (agora o usuário recebe erro útil antes de chegar ao advpls).

- **Bug 3 (CRITICAL) — `compile` real não auto-detectava advpls**:
  `compile --doctor` detectava `~/.plugadvpl/advpls/bin/<os>/advpls.exe`
  (instalado por `--install-advpls`) mas o `compile` real falhava com
  "advpls not found in PATH". Causa: `compile._resolve_advpls` tinha sua
  própria lógica de busca (só env + runtime.toml + PATH), não delegava
  pra `compile_doctor._detect_advpls`. **Fix**: `_resolve_advpls` agora
  delega pra `_detect_advpls` quando não acha em env/runtime.toml.
  Mensagem de erro atualizada com 4 opções (`--install-advpls`, env var,
  runtime.toml, PATH).

- **Bug 4 — `--use-server` quebrava sem feedback útil**: server com
  `build=""` (ex: importado de TDS-VSCode antigo) ou env vars de auth
  não-setadas chegavam ao advpls quebrados, com mensagens cripticas.
  **Fix**: `_apply_server_override` agora valida **antes** de tentar
  compilar — checa server tem host/port/build/environments/default_env
  preenchidos, env vars `user_env`/`password_env` resolvem pra valores
  não-vazios. Erra com exit 2 + lista do que falta + comando pra setar.

### Tests

- **+5 testes de regressão** garantem que os 4 bugs não voltem:
  - `test_compile.py::TestResolveAdvplsChecksInstalledDir` (bug 3)
  - `test_cli_compile.py::TestBug1FlagAfterPositional` (2 testes — erro
    quando flag depois do positional, sucesso quando antes)
  - `test_cli_compile.py::TestBug4UseServerValidation` (2 testes — server
    com build vazio + env vars ausentes)
- **785 testes total** (era 780, +5).

### Notes

- Origem do report: smoke real do reporter — exatamente o tipo de
  validação que o spec da Fase 1 §11.5 previu. Loop "smoke → fixture
  → fix → teste" funcionou conforme esperado.
- Bug 1 era o MAIS perigoso porque era silencioso (CI passaria com
  `--mode auto` quando user pediu `--mode cli`). Detector agora também
  cobre flags de outros comandos (`--init-config`, `--doctor`, etc.)
  caso usuário misture.

## [0.8.7] - 2026-05-19

### 🖥️ Registry global de AppServers (`~/.plugadvpl/servers.json`)

User pediu: "onde fica as informações dos servers/ambientes que o cliente
pode compilar para ele não ter que te enviar toda hora?". Implementado um
registry **global per-user** estilo TDS-VSCode — cadastra uma vez,
usa em qualquer projeto via `--use-server <nome>`.

### Added

- **`~/.plugadvpl/servers.json`** — registry global de AppServers
  (host/port/build/environments/user_env/password_env). Permissão `0o600`
  em POSIX. **NUNCA grava senha** — só nomes das env vars.
- **`compile_servers.py`** módulo novo com:
  - `Server` / `ServersRegistry` dataclasses
  - `load_registry()` / `save_registry()` (funções puras)
  - `add_server()` / `remove_server()` / `get_server()` / `default_server()`
  - `import_from_tds_vscode()` — parsea `~/.totvsls/servers.json` e devolve
    lista de `Server` pronta pra adicionar
- **4 novas flags do `compile`**:
  - `--list-servers` — lista cadastrados (com indicação de default)
  - `--add-server` — cadastro interativo (pergunta name, host, port, build,
    environments, user_env, password_env, notes)
  - `--remove-server <nome>` — remove do registry
  - `--import-tds-servers` — importa do TDS-VSCode (`~/.totvsls/servers.json`)
    com confirmação prévia
- **`--use-server <nome>`** + **`--use-environment <env>`** — compila usando
  server do registry, sobrescreve `[appserver]` do `runtime.toml`. Funciona
  até **sem `runtime.toml`** (combinado com `--install-advpls`, agente IA
  pode compilar do zero conhecendo só o nome do server).

### Changed

- **`--doctor` agora detecta servers cadastrados** e sugere caminho rápido
  em vez de criar `runtime.toml` por projeto:
  - Se há servers no registry → próxima ação `use_server` com `candidates`
    populadas (agente mostra lista pro usuário)
  - Se há TDS-VSCode mas registry vazio → próxima ação `import_tds_servers`
    (agente sugere importação)
  - Senão → mantém ação `create_runtime_toml` como antes
- **`docs/compile-checklist.md` §3-4** ganhou seção "⚡ Atalho — cadastre
  servers UMA vez" com 5 comandos chave (import, add, list, use, use+env).
- **`skills/compile/SKILL.md`** atualizada com 2 novas actions
  (`use_server`, `import_tds_servers`) + nota que `create_runtime_toml`
  agora é fallback (não default) quando há atalho disponível.

### Tests

- **+17 testes** em `test_compile_servers.py`: paths, load/save round-trip,
  malformed JSON tratado, add/remove/get/default semantics, import TDS-VSCode
  formato real (2 servers + secure/insecure).
- **780 testes total** (era 763 + 17 servers).

### Notes

- Servers são per-user (em `~`, não em `<projeto>/.plugadvpl/`). Decisão do
  user: prefere global (estilo TDS-VSCode) — cobre 90% dos casos. Caso
  futuro de "servers compartilhados por equipe via repo" pode ser feature
  opcional num release posterior.
- Diferente de `runtime.toml`, registry **NÃO precisa de --init-config**.
  Existe quando o primeiro `--add-server` / `--import-tds-servers` roda.
- Fluxo zero-config para um novo projeto: `plugadvpl compile --use-server
  <nome> --mode cli FONTE.PRW` (mais `--includes <pasta>` se modo `appre`).

## [0.8.6] - 2026-05-19

### 🤝 `compile --install-advpls` — instalação gerenciada do binário

User pediu: agente deveria verificar pasta interna do plugin, e se não
tiver advpls, perguntar caminho local OU oferecer baixar — sempre com
autorização explícita e explicação. Implementado.

### Added

- **`plugadvpl compile --install-advpls`** — comando interativo que
  instala advpls em `~/.plugadvpl/advpls/bin/<os>/`. 2 modos:
  - **(1) Copiar de path local**: usuário informa onde está advpls
    existente (instalação antiga, máquina virtual, etc.) e o sistema
    copia a pasta `bin/<os>/` inteira (binário + DLLs companion).
  - **(2) Baixar do Marketplace VSCode**: baixa `.vsix` público
    da Microsoft (~118MB), extrai **apenas** o subdir `bin/<os>/`
    (~40MB), descarta o resto. Sem precisar do VSCode instalado.
  - SEMPRE mostra **plano de instalação** (paths, tamanho estimado,
    se precisa rede) + pede **confirmação explícita** antes de qualquer
    operação destrutiva ou pesada. UX safe-by-default.
- **`compile_installer.py`** módulo novo (~200 linhas) com:
  - `plan_copy()` / `plan_download()` — funções puras geram `InstallPlan`
    sem efeitos colaterais. Permite mostrar antes de executar.
  - `execute_copy()` / `execute_download()` — efeitos colaterais
    isolados, retornam `InstallResult` com ok/binary_path/bytes_written.
  - `installed_binary_path()` / `is_installed()` — helpers de detecção.

### Changed

- **`_detect_advpls()`** em `compile_doctor.py` agora checa a pasta
  interna `~/.plugadvpl/advpls/` com **prioridade alta** (depois de env
  var, antes do PATH). Resultado: após `--install-advpls`, próximas
  chamadas de `--doctor`/`compile` detectam advpls automaticamente,
  sem precisar configurar `PLUGADVPL_ADVPLS_BINARY` nem `runtime.toml`.
- **`--doctor` hint do `set_advpls_binary`** atualizado pra recomendar
  `--install-advpls` em vez de só listar opções manuais.
- **`docs/compile-checklist.md` §1** simplificado: "se não tem, roda
  `plugadvpl compile --install-advpls`" — uma linha em vez de 5 opções.
- **`skills/compile/SKILL.md`** atualizada: agente agora orienta
  `--install-advpls` como caminho preferido em vez de baixar manual.

### Tests

- **+8 testes** em `test_compile_installer.py`: paths internos, plan_copy
  com source dir multi-arquivo, plan_download (URL/tamanho/needs_network),
  execute_copy com binário + companion DLL, execute_copy fail quando
  binário falta na source, execute_download com .vsix fake (zipfile
  in-memory mockando layout real da tds-vscode), execute_download tratando
  .vsix corrompido.
- **763 testes total** (era 755, +8 installer).
- Validado smoke real: copy de 36MB executou em <1s, `--doctor` posterior
  auto-detectou `~/.plugadvpl/advpls/bin/windows/advpls.exe`.

### Notes

- Pasta interna `~/.plugadvpl/advpls/` é per-user (não per-projeto). Uma
  instalação serve pra todos os projetos plugadvpl da máquina.
- Limitação atual: `--install-advpls` é sempre interativo. CI/scripts
  precisam mockar stdin OU usar variantes manuais
  (`PLUGADVPL_ADVPLS_BINARY=<path>` ou `[tds_ls].binary` no runtime.toml).
  Flags non-interactive (`--install-source={copy|download}`) podem ser
  adicionadas em release futuro se demanda surgir.
- `--yes` reservada mas requer flag explícita de source pra ser útil —
  hoje só serve pra pular confirmação de SUBSTITUIR instalação existente.

## [0.8.5] - 2026-05-19

### 📋 Checklist conversacional + perguntas `--doctor` mais didáticas

User reportou que faltava um guia tipo "o que você precisa fornecer pra
compilar" — explicando os 5 dados (advpls, includes, host/port,
build/environment, credenciais) com contexto humano, não só comandos
técnicos.

### Added

- **[`docs/compile-checklist.md`](docs/compile-checklist.md)** — guia
  conversacional do que reunir antes de chamar o agente. Estrutura:
  - Pergunta inicial: `appre` ou `cli`?
  - Checklist `appre` (2 itens) + Checklist `cli` (+3 itens)
  - Para cada item: o que é, como saber se já tem (com comando), o que
    fazer se não tem
  - Tabela resumo dos 5 dados com exemplo + onde achar cada um
  - Cenário "começando do zero" + "tenho TDS-VSCode" (replicar config)
- **Links pro checklist** em README, `setup-compile.md` e
  `skills/compile/SKILL.md` (pro agente recomendar quando user não souber
  o que fornecer)

### Changed

- **`compile --doctor` agora retorna perguntas mais didáticas em
  `next_actions`**. Cada `question` começa com "PRECISO: ..." explicando
  o quê + lista de opções de como obter + link pra seção específica do
  `compile-checklist.md`. Exemplo do `set_advpls_binary`:
  ```
  PRECISO: caminho do binário advpls (compilador oficial TOTVS, ~38MB).
    Como obter:
      (a) Instale extensão TDS-VSCode no VSCode...
      (b) Sem VSCode? Posso baixar o .vsix (~118MB) e extrair
      (c) Já tem em outro lugar? Informe o path manual
    Mais info: docs/compile-checklist.md §1
  ```

### Notes

- Sem mudança de schema do JSON do `--doctor` — só conteúdo das
  perguntas. Agentes/scripts existentes continuam funcionando.
- 8 testes do doctor continuam verdes (perguntas validadas só pela
  presença das chaves, não pelo texto).

## [0.8.4] - 2026-05-19

### 🤖 `compile --doctor` + skill como workflow agente + CI verde

User reportou: "agente bate cabeça pra entender o que precisa pra compilar".
Era verdade — skill era só sintaxe, sem workflow decisório. Esta release
muda isso.

### Added

- **`plugadvpl compile --doctor`** — pre-flight check estruturado em JSON.
  Auto-detecta `advpls` (env var + PATH + paths comuns + extensão tds-vscode
  em qualquer versão) e includes Protheus (4 paths comuns + sentinel
  `PRTOPDEF.CH`). Retorna `status` (`ready`/`needs_setup`),
  `mode_supported` (`["appre"]`/`["appre","cli"]`/`[]`), `checks` (5 itens
  com `ok`/`detail`/`hint`) e `next_actions` (lista ordenada com `question`,
  `candidates`, `var_name`, `secret`). Exit 0 se ready, 1 se precisa setup.
- **Novo módulo `plugadvpl/compile_doctor.py`** — função pura
  `run_doctor(root, runtime_cfg) → DoctorResult`. ~180 linhas, 8 testes
  unit cobrindo cada cenário.
- **Skill `/plugadvpl:compile` reformulada como workflow agente** de 4 passos:
  diagnóstico → processar next_actions → re-rodar até ready → compilar.
  Cobertura completa de cada `action` (`set_advpls_binary`, `set_includes`,
  `create_runtime_toml`, `set_env_var`, `start_appserver`) com comandos
  prontos copy/paste por OS, instruções de segurança (NUNCA logar secrets).

### Fixed

- **CI estava falhando há 5+ runs** (desde v0.5.4) por 2 motivos não-relacionados
  ao código de produção:
  - `tests/unit/test_parser_snapshots.py` (15 testes) — schema do parser
    ganhou `pontos_entrada` e `ws_restfuls` durante Universo 3/4 e Fase 0,
    snapshots `.ambr` nunca foram regenerados. Localmente rodávamos com
    `--ignore` (workaround). Fix via `pytest --snapshot-update`
    (61 linhas adicionadas, 0 removidas — schema extension pura).
  - `tests/bench/test_ingest_perf.py` — hardcoded `assert == 17` mas fixtures
    cresceram pra 20. Trocado por `>= 17` (consistente com outro assert).
- **Release workflow não dispara em tags lightweight**: descoberto que
  `git tag <nome>` (sem `-a`) não dispara `on.push.tags` no GitHub Actions.
  Tags v0.7.0/v0.8.0/v0.8.1/v0.8.2 ficaram só como referência git, sem
  publicação PyPI. v0.8.3 foi re-criada como annotated (`git tag -a -m`) +
  force-push pra publicar. Doc/memory atualizada.

### Tests

- **755 testes verde** (era 747 + 8 do doctor). Suite full SEM `--ignore` —
  snapshots e bench rodam normalmente.
- **CI verde pela primeira vez desde v0.5.4** — todos 12 jobs OK
  (1 lint + 9 test-cli matrix + 1 bench + 1 smoke-uvx).

### Notes

- Para usar `--doctor`: `plugadvpl --format json compile --doctor` retorna
  JSON parseável pelo agente. Modo `table` também disponível pra humanos.
- Auto-detect cobre 4 paths Windows + extensão `~/.vscode/extensions/totvs.tds-vscode-*`
  em Linux/Win/Mac, com glob pra qualquer versão da extensão.
- Memory persistida em `reference_plugadvpl_release_gotchas.md` previne
  regressão dos bugs CI/release.

## [0.8.3] - 2026-05-19

### 📘 Docs onboarding + skill `compile` + hints contextuais

Release de polish pra fechar a Fase 1: tudo que o usuário precisa pra
botar o `compile` pra rodar do zero, sem ler código-fonte.

### Added

- **[`docs/setup-compile.md`](docs/setup-compile.md)** — guia definitivo de
  setup. Cobre Windows/Linux/macOS, como obter o binário `advpls` (extensão
  TDS-VSCode + comando para baixar `.vsix` sem instalar VSCode), como obter
  includes Protheus reais, setup CI (GitHub Actions completo), SSH tunnel
  pra AppServer remoto, troubleshooting dos 6 erros mais comuns.
- **[`skills/compile/SKILL.md`](skills/compile/SKILL.md)** — slash command
  `/plugadvpl:compile` no plugin Claude Code. Tabela de pré-requisitos por
  modo, schema do JSON, exit codes, troubleshooting rápido.
- **Hints contextuais no `next_steps`** do output JSON:
  - Detecta diagnostic com `codigo=C2090` → sugere `--includes <pasta>` +
    link pro guia
  - Modo `appre` → lembra que é só pré-processador, sugere `--mode cli` pra
    erros semânticos + link pra seção §cli do guia

### Changed

- **`docs/cli-reference.md`** §compile — link 📘 explícito pra
  `setup-compile.md` no header da seção
- **`README.md` §Documentação** — bullet novo apontando pro guia de setup

### Notes

- Validado com user real: smoke compilou fonte limpo em ~60ms +
  detectou erro `C2090` linha=1 corretamente após v0.8.2.
- Sem mudança funcional além dos hints — release de docs/UX puro.

## [0.8.2] - 2026-05-18

### 🐛 Mais 2 bugs achados no smoke real (compilação end-to-end funcional)

Continuação do smoke iniciado em v0.8.1. Após o fix dos 3 bugs anteriores,
tentamos compilar fontes reais com includes Protheus de verdade
(`D:\PrjProtheus\protheus\Include`, ~1130 `.ch`) e descobrimos:

### Fixed

- **`--includes` ignorado silenciosamente pelo typer**: declarar
  `includes: list[Path] | None = None` em sub-comando typer com `files: list[Path]`
  Argument variadic faz Click parsear `--includes <path>` como elemento da
  lista `files` (variadic consome tudo até EOF). Resultado: `--includes` virava
  silenciosamente `None` no `CompileRequest`.
  - Fix em `cli.py`: trocar default de `None` para `[]` e tipo de `list[Path] | None`
    para `list[Path]` (padrão typer pra optional list). Alias `-I` adicionado.
  - **Convenção UNIX preservada**: flags `--xxx` SEMPRE antes de positional
    variadic args. Documentado em `docs/cli-reference.md` §compile.
- **Ruído `connection_manager.cc ... has no valid content after precompiled`
  poluindo bucket `__unmatched__`**: advpls SEMPRE cospe esse log interno
  quando há erro estruturado em `.errprw` — é redundância de telemetria, não
  erro novo. Cada erro real gerava 2 rows (1 estruturada + 1 unknown ruído).
  - Fix em `compile_parser.py`: novo `_NOISE_PATTERNS` filtra linhas de log
    interno do advpls (timestamp loguru `YYYY-MM-DD HH:MM:SS.fff` + padrão
    `connection_manager.cc`) antes de virar `unknown`.

### Validação end-to-end (smoke real)

Compilação contra `advpls.exe` real (extensão `totvs.tds-vscode` v3.x.x) +
includes Protheus reais:

| Cenário | Antes (v0.8.1) | Depois (v0.8.2) |
|---|---|---|
| Fonte limpo (`User Function` + `#include "protheus.ch"`) | `ok=false`, `C2090 PRTOPDEF.CH` (`--includes` ignorado) | `ok=true`, `exit_code=0`, `.ppx_prw` gerado em ~60ms |
| Fonte com erro real (`#include "naoexiste.ch"`) | 2 rows: row estruturada + `__unmatched__` ruidoso | 1 row limpa: `error C2090 linha=1 "File not found naoexiste.ch"` |

### Notes

- Confirmado: pipeline `plugadvpl compile --mode appre` **funciona end-to-end**
  com binário advpls real + includes Protheus. Fase 1 oficialmente validada
  contra ambiente real (não só mock).
- `appre` é só pré-processador — detecta erros de include/macro/sintaxe básica,
  NÃO erros semânticos (`If` sem `EndIf`, tipo incompatível). Pra esses,
  necessário modo `cli` com AppServer rodando.
- Documentação atualizada em `docs/cli-reference.md` com pré-requisitos
  explícitos do modo `appre` (binário + includes reais).

## [0.8.1] - 2026-05-18

### 🐛 3 bugs achados no smoke real contra advpls

Validação manual contra binário `advpls` real (extensão tds-vscode v3.x.x)
revelou que o modo `appre` da v0.8.0 estava **silenciosamente perdendo erros
do compilador** — exatamente o caso que o smoke iterativo (§11.5 do spec) foi
desenhado pra pegar.

### Fixed

- **CRITICAL — modo `appre` perdia erros do compilador**:
  `advpls appre` escreve diagnostics estruturados em
  `<output_dir>/<basename>.errprw`, **não** stdout/stderr (que tem só log
  interno do `connection_manager`). v0.8.0 só lia stdout/stderr → usuário via
  `ok=true` mesmo quando havia erro real (falso negativo crítico em CI).
  - Fix: orchestrator passa `-O <tempdir>` ao advpls + novo helper
    `_collect_errprw_diagnostics()` lê os `.errprw` ANTES do cleanup do
    tempdir (antes do `shutil.rmtree` no `finally`).
  - Novo parâmetro `force_arquivo` em `parse_diagnostics()`: advpls reporta
    sempre `APPRE41.PRW` no arquivo do erro (compilador genérico), mas
    sabemos qual fonte gerou via nome do `.errprw` (`foo.errprw` ↔ `foo.prw`).
- **IMPORTANT — `exit_code` Windows ficava `4294967295`**: `proc.returncode`
  retornava `-1` em Windows, que virava `0xFFFFFFFF` (4294967295 unsigned)
  no JSON. Novo `_normalize_exit_code()` mapeia para faixa 0–255 (POSIX
  convention) — 0=sucesso, !=0=falha.
- **IMPORTANT — `ok=true` em subprocess crash silencioso**: lógica antiga
  `ok = (counts.error == 0)` ignorava advpls crash que não produzia
  diagnostic. Nova regra: `ok = (zero errors) AND (subprocess ok OR
  diagnostics estruturados)`. Plugin `exit_code` também propaga
  `failed_requested > 0`.

### Added

- **Pattern `appre_compiler_c_code`** em `lookups/compile_patterns.json`:
  reconhece formato real `APPRE41.PRW(N) Error CXXXX <mensagem>` (e variante
  lowercase `appre41(N) Error CXXXX...`). Captura `codigo` (códigos estáveis
  do compilador como C2090, C2006) que agora é populado no `Diagnostic`.
- 2 fixtures sanitizadas em `tests/fixtures/compile_outputs/`:
  `appre_errprw_c2090.txt` + `appre_errprw_c2006.txt`.
- 11 testes novos de regressão (5 `_normalize_exit_code` + 3 errprw collector
  + 3 parser C-code) — garante que os 3 bugs nunca voltem.

### Tests

- **716 testes verde** (era 705 no v0.8.0, +11).
- Validado contra `advpls.exe` real:
  - **Antes**: `ok=true`, `exit_code=4294967295`, `errors=0` (bug latente)
  - **Depois**: `ok=false`, `exit_code=1`, `errors=1` com
    `codigo=C2090`, `arquivo=<fonte real>`, `mensagem="File not found PRTOPDEF.CH"`

### Notes

- Smoke iterativo §11.5 do spec entregou exatamente o que prometia: bugs
  reais só visíveis com binário real. Valor do loop "smoke → fixture →
  pattern" confirmado.
- Reforça princípio "fail visivelmente" — `ok=false` mesmo sem diagnostic
  parseado quando subprocess crasha. CI nunca silencia.

## [0.8.0] - 2026-05-18

### 🚀 Fase 1 — `plugadvpl compile` (wrapper TDS-LS)

Novo subcomando que invoca o binário oficial `advpls` (TOTVS) como subprocess
e devolve resultado **estruturado em JSON**. Fecha o primeiro passo do ciclo
"indexar → compilar → executar → testar → deployar" sem precisar abrir TDS-VSCode.

Spec completa em [`docs/fase1/compile-design.md`](docs/fase1/compile-design.md).
Plano de implementação em [`docs/superpowers/plans/2026-05-18-fase1-compile.md`](docs/superpowers/plans/2026-05-18-fase1-compile.md).

### Added

- **`plugadvpl compile <fonte...>`** — compila fontes ADVPL via wrapper sobre `advpls`.
  - `--mode auto|appre|cli` — `appre` (pré-processador local, sem AppServer) ou
    `cli` (full compile via AppServer TCP). Auto detecta se AppServer responde.
  - `--changed-since <git-ref>` — filtra por `git diff --name-only` (CI-friendly).
  - `--no-warnings` filtra warnings no output. `--timeout <seg>` mata subprocess.
  - `--includes <path>` override. `--no-security-warning` suprime alerta de host remoto.
- **`plugadvpl compile --init-config`** — gera template `<root>/.plugadvpl/runtime.toml`
  + adiciona ao `.gitignore` automaticamente (`--force` sobrescreve).
- **Schema JSON estável** (`--format json`):
  ```json
  {"rows":[{"arquivo","ok","mode","duration_ms","exit_code",
   "counts":{"error","warning","info","unknown"},"diagnostics":[...]}]}
  ```
  Cada diagnostic tem 7 campos (severidade, arquivo, linha, coluna, mensagem,
  codigo, raw). Bucket `__unmatched__` para diagnostics com arquivo fora dos
  requested.
- **`runtime.toml` opt-in** com 5 seções (`[tds_ls]`, `[appserver]`, `[auth]`,
  `[compile]`, `[logging]`) mapeadas 1:1 ao `.ini` real do advpls. Credenciais
  via env var (nome no TOML, valor no ambiente).
- **Auto-detect de modo**: se `runtime.toml` ausente OU AppServer não responde,
  fallback transparente para `appre`. Mode `cli` explícito sem config → exit 2.
- **Security warning para host remoto**: imprime aviso + comando `ssh -L` no
  stderr quando `appserver.host` ≠ `127.0.0.1`. Sem sleep (princípio "fail
  visivelmente"). Suprime com `--no-security-warning`.
- **Encoding boundary robusta**:
  - Script `.ini` gerado sempre em CP1252 (reusa `edit_prw.encode_cp1252_bytes`).
  - Output do advpls: detecta BOM UTF-16 LE/BE + UTF-8 + fallback CP1252.
- **Lifecycle subprocess defensivo**: `stdin=DEVNULL`, captura bytes (não text),
  `TimeoutExpired` → terminate + wait(5) + kill + diagnostic sintético,
  `KeyboardInterrupt` → terminate + wait(5) + kill + re-raise (CLI converte em
  exit 130 POSIX). Tempfile `.ini` em tempdir `mkdtemp(prefix='plugadvpl-')`
  com permission 0o600 (POSIX) — limpo no `finally` em TODOS os caminhos.
- **`lookups/compile_patterns.json`** — 5 patterns iniciais (en + pt-BR + any)
  com schema `{id, lang, pattern, ordem, severidade_group|severidade_fixed}`.
  Tie-break determinístico: dois patterns com mesma `ordem` → vence primeiro
  do JSON. Extensível via PR de 1 linha.
- **`lookups/redact_patterns.json`** — 6 patterns de mascaramento de credencial
  (password/psw/senha/pwd/hex_keys/aut_file) aplicados em `diagnostic.raw` E
  `diagnostic.mensagem`. Garante zero leak no output estruturado.

### Tests

- **+140 testes** (run_config 14 + compile_parser 12 + compile 27 + edit_prw +2 +
  catalog 13 + integration CLI 8 + smoke scaffolding 2).
- **702+ testes verde** (era 562 no v0.7.0).
- 5 testes específicos de **no-credential-leak** confirmando regex
  `(?i)(password|psw|senha|pwd)\s*[:=]\s*\S+` ausente em stdout/stderr/
  diagnostic.raw em cenários típicos.
- Catalog consistency tests garantem que `compile_patterns.json` e
  `redact_patterns.json` mantêm schema estável (pattern compila, severidade
  XOR, ids únicos, groups válidos).
- Schema JSON contract test em integration.
- Smoke real scaffolding (`tests/smoke/test_compile_real.py`) — skip por
  default, ativa com `PLUGADVPL_SMOKE=1`. Loop iterativo documentado
  (rodar smoke → coletar output → sanitizar → fixture → ajustar patterns).

### Architecture

- **4 módulos novos**: `runtime_config.py` (config TOML, função pura),
  `compile_parser.py` (regex parser, função pura), `compile.py` (orchestrator
  — único módulo com side effects de subprocess + fs), `cli.py` (subcomando
  typer aninhado).
- **Isolamento estrito**: parser e config não tocam subprocess. Orchestrator
  recebe ambos como input. Cada módulo testável em isolamento.
- **Paridade conceitual com TDS-VSCode**: `--init-config` ≈ wizard de server,
  `runtime.toml` ≈ `servers.json`, env var ≈ SecretStorage, `compile foo.prw`
  ≈ F9, `--changed-since` ≈ Compile All, `--format json` ≈ tab Problems.

### Notes

- **Pavimenta Fase 2** (`plugadvpl exec` — cliente HTTP do contrato U_EXEC da
  Fase 0) e **Fase 3** (`plugadvpl deploy` — hot-swap RPO).
- Princípios mantidos: sem IP TOTVS, opt-in via runtime.toml, sem assumir
  Docker/Cloudflare, JSON estruturado, credenciais via env var, fail
  visivelmente sem retry mágico, sem sleep em warnings.
- Loop de revisão automatizada (spec + code quality reviewers) usado em todas
  as 7 tasks de implementação. Plano de spec + implementação documentados em
  `docs/fase1/`.

## [0.7.0] - 2026-05-18

### 🎁 Fase 0 — Quick Wins (Runtime/Encoding/Webservice)

Fase introdutória do roadmap de runtime ADVPL: 5 regras de lint, 1 comando
CLI e 1 contrato com reference implementation MIT. Zero dependência externa
(sem TDS-LS, sem Docker, sem RPO). Pavimenta as Fases 1+ (compile, exec,
deploy, smoke, hooks). Spec completa em
[`docs/fase0/quick-wins.md`](docs/fase0/quick-wins.md).

### Added

- **`WS-001` (error)** — `WSMETHOD <verb>` sem `WS(SERVICE|RESTFUL|REST) <Name>`.
  Sem o trailing, método não registra na rota e vira código morto silencioso.
  Também detecta colisão (warning): dois `WSMETHOD <verb>` no mesmo serviço
  sem subname distinto (last-wins).
- **`WS-002` (warning)** — em `WSRESTFUL`, padrão `cBody := ::GetContent()`
  seguido em ≤10 linhas de `oJson:FromJson(cBody)` sem `DecodeUtf8`
  interposto. Cliente sem header `charset=utf-8` envia body CP1252 cru →
  FromJson grava bytes UTF-8 como CP1252 e corrompe acentos no SXX.
  Fix guidance NÃO sugere `FwJsonDeserialize` (descontinuada pela TOTVS).
- **`WS-003` (warning)** — `::SetResponse(...)` em `WSRESTFUL` cujo argumento
  não passa por `EncodeUtf8` antes. Clients UTF-8 (browsers, fetch JS) vêem
  mojibake em chars ≥ 0x80. Padrão idiomático: `::SetResponse(EncodeUtf8(
  FwJsonSerialize(oResp, .F., .F., .T.)))`.
- **`XF-001` (error, cross-file)** — `MsSeek/DbSeek(xFilial("XX"))` em tabela
  com `x2_modo='E'` (exclusiva) dentro de WSRESTFUL/JOB sem `RpcSetEnv` ou
  `PREPARE ENVIRONMENT` precedente. `cFilAnt` vazia → xFilial retorna `""` →
  seek localiza primeiro registro de qualquer filial (corrupção cross-filial
  silenciosa). Fix sugere `RpcSetEnv` ou `FwxFilial("XX")` moderna.
- **`ENC-001` (error)** — `.prw`/`.prx` salvo em UTF-8 quebra compilador
  AppServer legado (lê byte-a-byte como CP1252; "á" UTF-8 vira "Ã¡"). Reusa
  detecção do `parser._decode_bytes`. `.tlpp`/`.ch` ficam de fora.
- **`plugadvpl edit-prw {check,open,save}`** — conversão CP1252↔UTF-8 in-place.
  - `check <file>` reporta detecção vs extensão esperada. Exit 1 se mismatch.
  - `open <file>` imprime conteúdo em UTF-8 (auto-detecta origem).
  - `save <file> [--from] [--to] [--no-backup]` converte in-place. Default
    infere ambos por extensão + detecção. Cria `<file>.bak` por padrão.
  - Estratégia determinística: BOM → ASCII → UTF-8 strict → CP1252 fallback.
- **`docs/exec-contract.md`** (CC-BY-4.0) — contrato HTTP/JSON canônico
  `POST /rest/uexec` para execução headless de função ADVPL em DEV/CI.
  Tabela de tipos JSON↔ADVPL, status codes, encoding boundary, anti-patterns
  e limitações conhecidas. Aviso forte: anti-pattern em produção.
- **`docs/examples/uexec.prw`** (MIT) — reference impl ~150 linhas. WSRESTFUL
  com `WSMETHOD POST exec`. Valida prefixo `U_`, captura exceção com
  Begin Sequence/Recover, mapeia tipos via `ValType`, aplica
  `DecodeUtf8`/`EncodeUtf8` nos dois lados (alinhado com WS-002/003).

### Tests

- **+47 testes** (6 WS-001 + 4 WS-002 + 4 WS-003 + 5 ENC-001 + 6 XF-001 +
  22 unit `edit_prw` + 7 integration `edit-prw` + 7 contract docs guard).
- **622 testes verde** (era 565 no v0.6.1).

### Notes

- Pavimenta **Fase 1** (`plugadvpl compile` — wrapper TDS-LS), **Fase 2**
  (`plugadvpl exec` — cliente do contrato U_EXEC), **Fase 3** (`deploy` —
  hot-swap RPO), **Fase 4** (`smoke` + `test`). Detalhes no spec.
- **Princípios mantidos**: sem IP TOTVS, opt-in via pipeline existente, sem
  assumir Docker/TDS, JSON estruturado, credenciais via env var.

## [0.6.1] - 2026-05-18

### 🎯 Feature B polish — 3 itens reportados em uso real (v0.6.0)

Reporter testou Feature B em corpus do Cliente X (~9.500 funções) e
identificou 3 issues:
- **#1** `hotspots --tipo method` duplica método de framework por nome de var
- **#2** `cobertura-doc` heurística de módulo só olha path (98% sem grupo em codebase flat)
- **UX #3** `cobertura-doc` vazio sem hint de próximo passo

v0.6.1 fecha todos os 3.

### Fixed
- **#2 — `infer_module` cobre prefixo no nome do arquivo**
  ([commit e1a091b](https://github.com/JoniPraia/plugadvpl/commit/e1a091b)).
  Antes: só `SIGA\w{3,4}` no path. Agora `_module_from_filename` testa:
  1. Prefixo TOTVS direto: `FINA050.prw` → SIGAFIN, `MATA125.prw` → SIGACOM
  2. Prefixo cliente (1-4 chars) + TOTVS: `ABCCOM01.prw` → SIGACOM
  Tabela hardcoded de **33 prefixos canônicos** (ordem importa — mais
  específico primeiro pra evitar match genérico errado).
  **Impacto medido no corpus real**: 27 fontes inferidos (0.3%) → **1.114
  (56.2%)**. Top módulos detectados: SIGAFIN 241, SIGAFAT 199, SIGACOM 149,
  SIGAEEC 119, SIGAEST 110, SIGAGFE 104, SIGAFIS 75, SIGACRM 63.

- **UX #3 — `cobertura-doc` next_steps quando vazio** (mesmo commit).
  Antes: silencioso. Agora hint padronizado (consistente com `metrics`):
  sugere `ingest --no-incremental` + `docs --orphans` + `lint --regra BP-007`.

### Added
- **#1 — Warning de método ambíguo em `hotspots --tipo method`**
  ([atual commit](https://github.com/JoniPraia/plugadvpl)). Detector
  `_warn_hotspot_method_dedup` agrupa rows por sufixo `:METODO`. Quando
  vê >= 2 rows compartilhando método (provável mesma classe via vars
  com nomes distintos — `oPrint:Say`/`oPrn:Say`/`oPrinter:Say` =
  `TPrinter:Say`), emite warning em stderr listando-os e somando
  `n_calls` combinado.
  Reporter aceitou explicitamente a **Opção C** (warning) como solução
  válida — type inference de OO ADVPL ficaria caro demais (não justifica
  pra esse escopo).

### Limitação conhecida — Bug #1 não resolve agregação
A solução é informativa, não agregadora. Pra ranking sem ambiguidade,
recomendação do reporter mantida: usar `--tipo user_func` (ranking limpo
de funções customizadas — o que tem real refactor priority).

### Tests
- **+2 testes unit** (`test_protheus_doc.py::TestModuleInference`):
  prefixo TOTVS no nome + prefixo cliente+TOTVS
- **+1 teste integration** (`test_cli.py::TestQualidadeMetricas`):
  hotspots warning de method dedup
- **565 testes verde** (era 562).

### Notes
- **Re-ingest recomendado** pra colher os módulos inferidos pelo novo
  `_module_from_filename`. Antes 98% dos fontes ficavam em `_sem_grupo`;
  agora ~44% (e dos remanescentes, maioria são utils/helpers sem
  convenção de prefixo).
- **3 itens do reporter fechados em 1 release** mantendo Princípio do
  ciclo curto bug-report → fix.

## [0.6.0] - 2026-05-18

### 🚀 Universo 4 — Qualidade & Métricas (Feature B)

**Killer feature do v0.6.0**: responde "**por onde começar num refactor?**"
via 3 comandos novos baseados em métricas pré-computadas.

### Added
- **`plugadvpl metrics [arquivo]`** — métricas por função:
  - `cc` (complexidade ciclomática McCabe — `If/ElseIf/While/For/Case/Catch/IIf`)
  - `loc` (linhas de código)
  - `nesting` (profundidade máxima de blocos)
  - `n_calls_out` (fan-out)
  - `params_count` (parâmetros da assinatura)
  - `has_doc` (tem header Protheus.doc)
  Filtros: `--min-cc N`, `--min-loc N`, `--sort cc|loc|nesting|calls|params`.

- **`plugadvpl hotspots`** — top-N funções mais chamadas (fan-IN):
  - Filtra nativas TOTVS por default (`--no-natives`) — sem filtro top-20
    vira `RecLock`/`ConOut`/`DbSelectArea`
  - `--n N` (default 20), `--tipo user_func|method|execauto|execblock`
  - Retorna `{destino, n_calls, n_arquivos, n_callsites}`

- **`plugadvpl cobertura-doc`** — % funções com Protheus.doc agregado:
  - `--groupby modulo` (default — usa `fontes.modulo` backfilled) ou `source_type`
  - Ordenado por `pct ASC` (pior cobertura primeiro = refactor priority)
  - Bucket `"_sem_grupo"` quando módulo não inferível

- **Backfill `fontes.modulo`** no ingest via `infer_module()` reaproveitado
  do `protheus_doc.py` (path-based + routine-prefix do catálogo execauto).
  Antes era hardcoded `""`; agora populado pra qualquer fonte com path
  TOTVS standard (SIGAFAT/SIGACOM/etc) OU prefixo de função no catálogo
  (`MATA*` → SIGAFAT, `FINA*` → SIGAFIN, etc).
  Benefício colateral: `workflow --kind`, `execauto --modulo`, `docs <modulo>`
  ganham agrupamento robusto.

- **3 skills MD**: `/plugadvpl:metrics`, `/plugadvpl:hotspots`, `/plugadvpl:cobertura-doc`.

### Migration
- **Schema v9 → v10** (`010_universo4_metrics.sql`):
  - Tabela nova `fonte_metrics` (cache 1 row por função)
  - 4 índices: arquivo, cc DESC, loc DESC, funcao
  - FK CASCADE com `fonte_chunks` (auto-cleanup em re-ingest)
- **Re-ingest recomendado** pra popular cache: `plugadvpl ingest --no-incremental`

### Extractors novos (`parsing/metrics.py`)
- `compute_cyclomatic_complexity(body)` — regex `\\b(If|ElseIf|While|For|(?<!Do\\s)Case|Catch|IIf)\\b`
  com lookbehind pra excluir `Case` em `Do Case` (header do switch, não é ramo).
- `compute_max_nesting(body)` — stack-based scan de openers vs closers.
- Roda sobre `strip_advpl()` pra ignorar keywords em strings/comments.

### Tests
- **+17 testes unit** (`test_metrics.py`):
  - CC baseline, If/ElseIf/Else (McCabe), While/For, Do Case, IIf, Catch
  - Nesting flat, single, nested, sequential, Do Case
  - Aggregator combinado
- **+5 testes integration** (`test_cli.py::TestQualidadeMetricas`):
  - metrics lista todas funções com cc/loc/nesting
  - `--min-cc 5` filtra
  - `--sort loc` ordena
  - hotspots ranking
  - cobertura-doc retorna pct
- **562 testes verde** (era 540, +22).

### Convenção McCabe
- ✅ Cada `If`/`ElseIf`/`While`/`For`/`Catch`/`IIf` = +1 path
- ✅ Cada `Case` (cláusula) = +1 (espelha elif)
- ❌ `Else` NÃO conta (não adiciona path)
- ❌ `OtherWise` NÃO conta (= else do Do Case)
- ❌ `Do Case` em si NÃO conta (é o switch base; só as cláusulas Case)
- Base mínima = 1 (função sem ramificação)

### Notes
- **Spec aprovado** em `docs/universo4/B-qualidade-metricas.md` antes do código.
- **Sem breaking change** em comandos existentes — todos continuam funcionando.
- Próximas Features candidatas pro Universo 4: ownership analytics (depende git
  history) e cross-cliente diff (nicho consultoria). Defer até demanda específica.

## [0.5.4] - 2026-05-18

### 🚨 Bug crítico pré-existente — `param` perdia params com prefixo custom

Reporter v0.5.3 descobriu (via `trace -t parametro`) que o índice
`parametros_uso` populava parcialmente: regex hardcoded `MV_\w+` só
capturava parâmetros TOTVS standard, **perdendo todos os customs** de
cliente. Bug **pré-existente desde a primeira versão do parser**, só
exposto agora porque o `trace` declarativamente promete cruzar U1+U2+U3
e ficou óbvio que U1 vinha vazio.

### Fixed
- **`_MV_READ_RE` / `_MV_WRITE_RE` aceitam qualquer prefixo de identifier
  uppercase** ([parser.py:55-75](cli/plugadvpl/parsing/parser.py)).
  Antes: `MV_\w+` (só TOTVS standard). Agora: `[A-Z][A-Z0-9_]{2,}` —
  qualquer convenção que cliente usar:
  - `MV_*` (TOTVS standard)
  - `ABC_*` (cliente A)
  - `MFG_*`, `ABC_*`, `XYZ_*`, `Z_*` (qualquer cliente)

  **Impacto medido em corpus real** (amostra 200 fontes):
  - Antes: 43 params (só `MV_*`)
  - Depois: 92 params (47 ABC_* + 43 MV_* + 2 MFG_*)
  - **+114%** params catalogados — quase metade era perdida.

- **Bug #2 do reporter (downstream)**: `trace -t parametro` agora retorna
  edges U1 (`used_read`/`used_write`) também — só faltava porque
  `parametros_uso` estava parcial. Auto-resolve após re-ingest.

### Changed (UX)
- **Help text de `trace --tipo`** atualizado pra listar os 6 valores
  aceitos com hint do que cada um faz. Antes mencionava só
  "campo|funcao|tabela" (lista de v0.5.0 — desatualizada desde v0.5.3
  que adicionou arquivo/parametro/pergunte).

### Não-bug (verificação)
- **`_PERGUNTE_RE`** já estava OK (aceita `\w+`). Reporter relatou
  `trace AGRR890 -t pergunte` faltando U1, mas verificação no corpus
  (`Pergunte("MTR110", ...)`, `Pergunte("DAMDFE", ...)` etc) confirmou
  que o regex captura corretamente. `AGRR890` específico provavelmente
  não tem callsite no codebase.

### Tests
- **+3 testes unit** (`test_parser.py::TestExtractParams`):
  - `test_custom_prefix_abc` (3 variantes ABC_*)
  - `test_custom_prefix_z_and_short` (ZX_FOO)
  - `test_putmv_custom_prefix` (PutMV com prefix custom)
- **540 testes verde** (era 537).

### Recomendação pro usuário
**Re-ingest necessário** pra colher os params que estavam perdidos:
```
plugadvpl ingest --no-incremental
plugadvpl param ABC_GFE83F   # deve retornar >= 1 hit agora
plugadvpl trace MV_RELT      # U1 com used_read/used_write
```

### Notes
- Bug aberto desde v0.1.x — só foi pego graças ao `trace` agregador
  expor a lacuna. Padrão a manter: features que cruzam universos
  acabam expondo gaps de cobertura nos índices individuais.

## [0.5.3] - 2026-05-18

### 🔌 Trace estendido — +3 tipos de entidade (Universo 4 Feature A.2)

`trace` ganha 3 tipos novos de entidade (`arquivo`, `parametro`, `pergunte`),
saindo de 3 → **6 tipos suportados**. Reaproveita 100% das queries existentes
(sem schema migration novo). Cobre os casos faltantes do MVP v0.5.0:
"trace um arquivo inteiro", "trace um MV_*", "trace um grupo SX1".

### Added
- **`arquivo:X.prw`** (auto-detect por extensão `.prw`/`.tlpp`/`.prx`/`.apw`).
  Edges:
  - **U1**: `arch_summary` (módulo + capabilities + LOC + namespace) |
    `defines_function` (cada função do fonte) | `lint_finding` (top severidade)
  - **U3**: `calls_execauto` (todas chamadas MsExecAuto do fonte) |
    `has_trigger` (workflow/schedule/job/mail) | `has_protheus_doc`
- **`parametro:MV_*`** (auto-detect por prefixo `MV_`).
  Edges:
  - **U1**: `used_read`/`used_write` (parametros_uso agrupado por fonte+modo)
  - **U2**: `param_definition` (SX6: tipo/default/descrição) |
    `in_pergunte_default` (SX1 que usa MV como conteúdo padrão)
- **`pergunte:GRUPO`** (auto-detect via lookup em `perguntas.grupo`).
  Edges:
  - **U1**: `uses_pergunte` (fontes que invocam o grupo via PutSx1)
  - **U2**: `pergunta_definition` (cada pergunta do grupo: variável/tipo/validação)
  - **U3**: `scheduled_with_pergunte` (schedule SX1 que dispara com esse grupo)

### Changed
- **`_detect_entity_type` ordem atualizada**: arquivo → parametro → campo →
  tabela → função (fallback). Padrões mais específicos primeiro.
- **`_detect_entity_type_db` extended** — lookup pra `perguntas.grupo` e
  `parametros.variavel` (sem prefixo MV_). Reordena pra checar regex
  arquivo/parametro PRIMEIRO (determinístico, dispensa DB hit).
- **`TraceTipo` enum** ganha 3 valores novos: `arquivo`, `parametro`, `pergunte`.
- **`_trace_next_steps`** sugere comandos contextualmente:
  - `arquivo` → sugere `arch` + `lint --arquivo`
  - `parametro` → sugere `param <MV>`
  - `pergunte` → sugere `impacto <campo>` (se cruza com SX3)

### Tests
- **+2 testes unit** (`test_trace.py::TestAutoDetect`):
  arquivo por extensão (5 cases) + parametro MV_ prefix (3 cases)
- **+2 testes integration** (`test_cli.py::TestTrace`):
  trace de arquivo agrega arch/doc/execauto + auto-detect por extensão
- **537 testes verde** (era 533).

### Notes
- **Zero schema migration** — reaproveita 100% das tabelas existentes
  (fontes, parametros_uso, perguntas_uso, parametros, perguntas, etc.).
- **Skill atualizada** com casos de uso pros 3 tipos novos.
- **Fecha o MVP-out do trace v0.5.0**: agora cobre os 6 tipos que eram
  candidatos no spec original (campo/funcao/tabela + arquivo/parametro/pergunte).
- **`rotina:MATA410` continua tratado como `funcao`** (já cobre — quem chama
  via MsExecAuto aparece em `via_execauto`).

## [0.5.2] - 2026-05-18

### 📦 `trace` ganha `contexto_dict` estruturado (fecha #4 do bug report)

Reporter v0.5.0 sugeriu (#4): coluna `contexto` carrega chave=valor não-
estruturado, exige parse manual em consumidores programáticos. v0.5.1
deferiu por ser decisão de design. v0.5.2 entrega a versão aditiva
(zero break em consumers existentes).

### Added
- **Campo `contexto_dict` em todas as rows de `trace_query`** — dict
  estruturado paralelo à string `contexto`. Não muda comportamento de
  table render (que mostra só `contexto` string), mas JSON ganha schema
  pra consumidor programático.

  Exemplos:
  | `edge` | `contexto` (string) | `contexto_dict` (novo) |
  |--------|---------------------|------------------------|
  | `field_definition` | `"tabela=EE7 tipo=C(3) ctx=R"` | `{"tabela": "EE7", "tipo": "C(3)", "ctx": "R"}` |
  | `indexed_by` | `"ord=2 nick=-"` | `{"ord": "2", "nick": "", "chave": "EE7_FILIAL"}` |
  | `reads`/`writes` | `"mode=read"` | `{"mode": "read"}` |
  | `called_by` | `"call type=user_func"` | `{"call_type": "user_func"}` |
  | `validates_field` | `"X3_VALID"` | `{"slot": "X3_VALID", "tabela": "EE7", "campo": "EE7_X"}` |
  | `via_execauto` | `"module=SIGAFAT op=inclusao"` | `{"module": "SIGAFAT", "op": "inclusao"}` |
  | `triggered_by_*` | `"kind=workflow"` | `{"kind": "workflow"}` |
  | `documented_in` | `"author=X since=Y"` | `{"author": "X", "since": "Y", "deprecated": true}` |
  | `table_definition` | `"modo=E custom=0"` | `{"modo": "E", "custom": 0}` |
  | `n_fields` | `"30 campos SX3"` | `{"n_campos": 30}` |
  | `in_relationship` | `"id=ZA01 expr_origem=ZA1_FIL->..."` | `{"id": "ZA01", "tabela_origem": "ZA1", ...}` |

### Backward compat
- **Zero break** — campo `contexto` (string) inalterado em valor e formato
- Table/MD render mostram apenas `contexto` (default), `contexto_dict`
  fica oculto (não está na lista de `columns` do render)
- JSON consumers existentes continuam funcionando (campo extra é ignorável)
- Auto-derive: se collector passa só `contexto_dict`, `_trace_hit` deriva
  string `"k1=v1 k2=v2"` automaticamente (não há regressão de display)

### Tests
- **+2 testes integration** (`test_cli.py::TestTrace`):
  - `test_trace_contexto_dict_structured_in_json` valida campo aparece em JSON
  - `test_trace_contexto_dict_table_render_unchanged` valida que table render
    NÃO mostra `contexto_dict` (mantém layout enxuto)
- **533 testes verde** (era 531).

### Notes
- Fecha o último item deferred do PLUGADVPL_BUGS_TRACE_AUTODETECT.md.
  Todos os 6 itens reportados pelo reporter v0.5.0 resolvidos em 2 releases
  (v0.5.1 com 5 itens, v0.5.2 com este).
- `contexto_dict` ganha alguns campos extras úteis (ex.: `tabela`/`campo`
  em `validates_field`, `tabela_origem`/`tabela_destino` em `in_relationship`)
  que a string não tinha — programaticamente mais útil.

## [0.5.1] - 2026-05-18

### 🎯 `trace` polish — 5 itens reportados em uso real

Reporter testou `trace` em corpus real do Cliente X e identificou bugs/UX
gaps. v0.5.1 fecha **5 dos 6** itens (defer apenas decisão de design do #4).

### Fixed
- **#1 — Auto-detect de campo aceita 3 chars antes do `_`**
  ([commit 6ddfd1e](https://github.com/JoniPraia/plugadvpl/commit/6ddfd1e)).
  Antes regex `^[A-Z]\d_...` exigia exatamente 2 chars (letra+dígito),
  perdendo campos de módulos Comex/GFE/custom (`EE7_ZSUBEX`, `DAI_NFISCA`,
  `EEC_PREEMB`, `GV4_XMEMB`). Agora `^[A-Z][A-Z0-9]{1,2}_...` aceita 2 ou 3.
- **#2 — Auto-detect de tabela cobre prefixos não-standard**
  (mesmo commit). Antes `[SZNQD]` hardcoded perdia Comex `EE*`, GFE `DA*`/
  `DAI`/`GV4`, auxiliares `CCH`/`C09`. Solução híbrida:
  1. **Lookup-first**: `_detect_entity_type_db` consulta `tabelas`/
     `fonte_chunks`/`campos`/`fonte_tabela` no índice (preferido quando
     conn disponível — sem falso-positivo, auto-adapta a tabelas custom)
  2. **Regex fallback** ampliado pra `[A-Z][A-Z0-9]{2}` (3 chars qualquer
     letra) — cobre entidades não-indexadas ainda
- **#6 — `defined_in.alvo` agora é nome do símbolo, não arquivo**
  ([commit 5afbedf](https://github.com/JoniPraia/plugadvpl/commit/5afbedf)).
  Antes `alvo == arquivo` (redundante com a coluna `arquivo`). Agora `alvo`
  carrega o nome da função definida, consistente com outras edges. Bonus:
  lookup mais robusto via variantes com/sem `U_` prefix (corrige
  inconsistência entre schema doc e dados reais em `fonte_chunks.funcao_norm`).

### Changed (UX)
- **#3 — Hint inteligente quando trace retorna vazio**
  ([commit dc614c7](https://github.com/JoniPraia/plugadvpl/commit/dc614c7)).
  Antes sempre sugeria `plugadvpl ingest --no-incremental`. Em índice
  populado (caso comum), isso induzia reingest caro de 2k+ fontes pra um
  típo. Agora `_trace_empty_hints` checa `COUNT(*) FROM fontes`:
  - Populado → sugere `find`/`grep -m identifier` (provável typo)
  - Vazio → mantém sugestão de reingest
- **#5 — Sort priority puxa edges informativos pro topo**
  ([commit 514ada3](https://github.com/JoniPraia/plugadvpl/commit/514ada3)).
  Antes `trace SC5 -t tabela` retornava 128 rows e `table_definition`
  (descrição oficial SX2) aparecia na **última** row. Agora `_EDGE_PRIORITY`:
  - Priority 0: `table_definition`, `field_definition`
  - Priority 1: `n_fields`, `defined_in`
  - Priority 50 (default): demais edges
  Sort: `(universo, edge_priority, edge_name, arquivo, linha)`.

### Tests
- **+9 testes novos**:
  - `test_trace.py::TestAutoDetect`: +2 (campo 3-char, tabela non-standard)
  - `test_trace.py::TestSortPriority`: +4 (table/field/n_fields/universo order)
  - `test_cli.py::TestTrace`: +3 (typo-vs-reingest, defined_in alvo, table_definition order)
- **531 testes verde** (era 522).

### Deferred (defer pra release dot futura)
- **#4 — `contexto` como dict estruturado em JSON** (mantém string em table).
  Decisão de design — pode quebrar compat de consumidores JSON. Avaliar em
  v0.5.2+ com mais feedback do reporter.

### Notes
- **Estado pós-v0.5.1 no corpus do reporter**: bugs #1 e #2 zerados — `trace EE7`
  e `trace EE7_ZSUBEX` agora funcionam sem precisar de `--tipo` explícito.
  Hint de typo (#3) já não induz reingest. `table_definition` no topo (#5)
  melhora UX de leitura humana. `defined_in.alvo` (#6) consistente com
  outras edges.

## [0.5.0] - 2026-05-18

### 🚀 Universo 4 — Trace Unificado (Feature A)

**Killer feature do v0.5.0**: novo comando `plugadvpl trace <entidade>` que
agrega TUDO que toca campo/função/tabela em uma única saída — atravessando
os 3 universos do plugin (fontes + SX + workflow/execauto/docs).

Substitui o workflow manual de 5 comandos (`impacto` + `gatilho` + `tables` +
`callers` + `execauto`) por **1 comando**. Útil pra responder "estou
alterando X, o que quebra?" sem correlação mental do output de 5 comandos.

### Added
- **Comando `plugadvpl trace <entidade>`** com auto-detect por regex:
  - `SA1`, `SC5`, `ZA1`, `ND0` (3 chars [SZNQD]+letra+alfanum) → tabela
  - `A1_COD`, `C5_NUM` (letra+dígito+_+nome) → campo
  - Demais → função
  Override via `--tipo campo|funcao|tabela`.
- **Flags**: `--depth 1..3` (BFS, default 2) | `--universo 1,2,3` (filtra
  universos) | `--max-per-edge N` (limita explosão em entidades comuns).
- **Skill `/plugadvpl:trace`** com casos de uso + edges por tipo.
- **Schema unificado de saída** (1 dict por aresta):
  `{universo, edge, arquivo, funcao, linha, alvo, contexto, snippet}`.
- **21 tipos de aresta (edges)** cobrindo:
  - **U1** (fontes): `defined_in`, `called_by`, `calls`, `reads`, `writes`,
    `reclock`, `references_field`
  - **U2** (SX): `field_definition`, `trigger_origin`, `trigger_target`,
    `in_pergunte`, `in_relationship`, `in_consulta`, `in_grupo_sxg`,
    `table_definition`, `n_fields`, `indexed_by`, `trigger_on_table`,
    `validates_field`
  - **U3** (rastreabilidade): `via_execauto`, `triggered_by_workflow`/
    `schedule`/`job`/`mail`/`callback`, `touched_via_execauto`,
    `documented_in`

### Implementation
- 70% reaproveita queries existentes (`_impacto_fontes` pattern, `callers`,
  `callees`, `tables_query`, `execauto_calls_query`, `execution_triggers_query`,
  `protheus_docs_query`).
- 30% SQL novo — filtros LIKE em colunas JSON (`tables_resolved_json`,
  `tables_json`) com pós-filtro Python pra word-boundary correto.
- **Sem schema migration** — usa o schema v9 atual.

### Tests
- **+4 testes unit** (`test_trace.py::TestAutoDetect`): cobre 4 padrões
  (tabela Protheus, campo SX3, função fallback, rotinas TOTVS uppercase 4+ chars).
- **+7 testes integration** (`test_cli.py::TestTrace`): fixture com fonte
  Protheus.doc + ExecAuto MATA410 + caller, valida edges cross-universo
  (called_by, documented_in, via_execauto, touched_via_execauto, reads/writes,
  --universo filter, --tipo override, --universo inválido rejeitado).
- **522 testes verde** (era 511).

### Sucesso vs antes
| KPI | Antes (5 cmds) | Depois (`trace`) |
|-----|----------------|-------------------|
| Comandos pra impacto completo | 5 | 1 |
| Tokens consumidos por Claude | ~3-5k | ~800 |
| Falsos negativos por esquecer comando | comum | zero |

### Notes
- **Spec aprovado** em `docs/universo4/A-trace-unificado.md` antes do código
  (workflow novo: research → spec MD → approval → code).
- **MVP** = 3 tipos (campo/função/tabela). Entidades bonus deferred pra
  release dot: `parametro:MV_*`, `pergunte:GRUPO`, `arquivo:X.prw`,
  `rotina:MATA410`.
- **Próximo passo natural**: feature B do Universo 4 (a definir — candidatos:
  qualidade & métricas, ownership analytics, cross-cliente diff).

## [0.4.9] - 2026-05-18

### 🎨 `doctor --check-funcs --detail` agora útil em render table

Reporter pegou cosmético no v0.4.8: as rows `funcs_detail` apareciam com
colunas `count`/`detail` vazias no render `table` (default) porque o renderer
só conhece schema `(check, status, count, detail)` — colunas estruturais
`arquivo/grep_raw/grep_code/parser/classificacao` só apareciam em JSON. Pra
ver no terminal humano o usuário precisava trocar pra `--format json`.

### Fixed
- **Rows `funcs_detail` preenchem `count` + `detail` string** pra render table
  mostrar info útil. Schema de doctor mantido consistente (todas rows têm
  `count/detail`), colunas estruturais continuam pra JSON.
  ```
  funcs_detail | info | 1 | FnA.prw: grep_raw=2 grep_code=1 parser=1 class=commented_out
  ```
  Onde:
  - `count = grep_raw - parser` (delta)
  - `detail` = string compacta com todas as métricas + classificação

### Tests
- **+1 teste integration**:
  `test_doctor_check_funcs_detail_table_friendly_fields` valida que rows
  `funcs_detail` têm count/detail preenchidos + colunas estruturais
  preservadas em JSON.
- **511 testes verde**.

### Notes
- Best-of-both: table view legível + JSON estruturado para consumo programático.
- Alternativa considerada (e descartada): renderer detectar sub-tipo e trocar
  esquema de colunas. Mais invasivo no `output.py`, abre precedente que cobra
  manutenção em features futuras.

## [0.4.8] - 2026-05-18

### 🔍 Detector `--check-funcs` aceita TLPP `Function` puro + lowercase

Adendo 2 da bug report do v0.4.7 identificou 2 `funcs_real_bug` remanescentes
no corpus do reporter — todos **falsos positivos do DETECTOR**, não do parser.
Causa: regex do detector exigia prefixo `(Static|User|Main)`, perdendo:
- TLPP-style `Function U_Foo(cArg as character)` (sem prefixo)
- Lowercase `static function`, `function` (ambos válidos no compilador AppServer)

O parser real (`parsing/parser.py::_FUNCTION_RE`) já tinha o prefixo opcional
e contava certo. Só o detector de validação (`query.py::_FN_RE_DOCTOR`) estava
descalibrado.

### Fixed
- **`_FN_RE_DOCTOR` agora alinha com `_FUNCTION_RE` do parser**.
  Antes: `^[ \t]*(?:Static|User|Main)[ \t]+Function[ \t]+\w+` (prefixo obrigatório).
  Agora: `^[ \t]*(?:(?:Static|User|Main)[ \t]+)?Function[ \t]+\w+` (prefixo opcional).
  Já era `re.IGNORECASE`, então lowercase também passa a casar.

### Impact (medido no corpus real do reporter)
- **`funcs_real_bug`**: 2 → **0**.
- **`funcs_commented_out`**: 36 (inalterado — segregação intencional do v0.4.7).
- Critério #2 do Adendo 2 (B6) ✅ atendido: ciclo bug-report → fix → reteste fecha
  com **0 funções perdidas pelo parser de indexação no codebase do Cliente X**.

### Tests
- **+1 teste integration**:
  `test_doctor_check_funcs_regex_matches_tlpp_bare_function` cobre 4 variantes
  (bare `Function`, lowercase `function`, lowercase `static function`,
  CamelCase `Static Function`).
- **510 testes verde**.

### Notes
- Boa pegada do reporter: parser estava correto desde v0.4.5, só o detector de
  validação tinha gap. Sem essa observação, falsos positivos ficariam reportados
  como warnings indefinidamente.
- **Estado final do ciclo deste bug** (4 releases, 2 adendos):
  | Versão | Marco |
  |--------|-------|
  | 0.4.4 | Bug original descoberto |
  | 0.4.5 | Fix parser (string mal-formada engolia funções) |
  | 0.4.6 | `doctor --check-funcs` adicionado (sugestão #5) |
  | 0.4.7 | Split em `funcs_real_bug` vs `funcs_commented_out` |
  | **0.4.8** | **Detector regex alinhado com parser → 0 false positives** |

## [0.4.7] - 2026-05-18

### 🩺 `doctor --check-funcs` refinado — separa real bug vs commented-out + sem truncagem

Adendo da bug report do v0.4.6 revelou 2 issues no `--check-funcs`:
1. Reportava 36 "warnings" no codebase real do reporter, mas **TODAS eram
   commenting-out intencional** (`/* Static Function X() ... */`) — não bug
   do parser. False alarm.
2. Detail truncado em 10 fontes ignorando `--limit 0` e `--format json`.

### Fixed
- **Classificação real_bug vs commented_out**. Estratégia: compara 3 contagens
  por arquivo:
  - `grep_raw`: regex no conteúdo cru (vê funções comentadas)
  - `grep_code`: regex no conteúdo stripado (só funções em código real)
  - `parser`: count em `fonte_chunks`
  Discrepância classificada:
  - `funcs_real_bug`: `grep_code > parser` → parser perdeu função em código
    (bug do plugin, status `warn`)
  - `funcs_commented_out`: `grep_raw > grep_code == parser` → função dentro
    de `/* */` (intencional, status `info`)

  No codebase real do reporter: **0 real_bug**, 36 commented_out.
  Mensagem clara em vez de false alarm.

### Added
- **`--detail` flag** ([sugerido pelo reporter como Opção #2]):
  `doctor --check-funcs --detail` expande pra row-per-file. Cada fonte com
  discrepância vira 1 row com colunas `arquivo`, `grep_raw`, `grep_code`,
  `parser`, `classificacao`. Sem truncagem — `--limit` global navega
  naturalmente.

### Tests
- **+2 testes integration**:
  - `test_doctor_check_funcs_classifies_commented_vs_real_bug`
  - `test_doctor_check_funcs_detail_returns_row_per_file`
- Test antigo `test_doctor_check_funcs_detects_discrepancy` substituído
  (mudou de assertion `warn` pra classificação `info`/`ok`).
- **509 testes verde**.

### Notes
- **Parser está correto**. Não havia bug remanescente em 0.4.5/0.4.6 — só
  UX confusa do `--check-funcs` que reportava false positives.
- **Critério #1 do adendo A2 zerado**: `funcs_real_bug.count == 0` no
  codebase real do reporter (0 falsos negativos do parser).

## [0.4.6] - 2026-05-18

### 🧹 Backlog cleanup — 11 itens fechados antes de Universo 4

Polish pack agregando todos os deferred desde v0.4.3 (code review pós-Universo 3)
e v0.4.4/v0.4.5 (QA de uso real). Tiers 1+2 (impacto real) + Tier 4 (feature) +
Tier 3 (cosmético). Cada fix em commit atômico com TDD red→green.

### Fixed (Tier 1 — impacto real)
- **A — block comment `/* */` não-fechado cap defensivo de 200 linhas**
  ([commit b6d5e6c](https://github.com/JoniPraia/plugadvpl/commit/b6d5e6c)).
  Complementa o fix v0.4.5 da string mal-formada. Stripper agora encerra
  block comment ao passar de 200 linhas (cap extremamente generoso pra qualquer
  uso legítimo — devs que comentam função inteira tipicamente em <100 linhas).
  Cap só dispara em casos patológicos (dev esqueceu `*/`).
- **C — `op_dynamic` flag separado em execauto** (schema v8→v9, migration 009)
  ([commit fc1435b](https://github.com/JoniPraia/plugadvpl/commit/fc1435b)).
  Antes `MsExecAuto(..., nVar)` ou `MsExecAuto(..., 3+nOpc)` gravava
  `op_code=NULL` indistinguível de "sem args". Agora coluna `op_dynamic`
  diferencia. Filtro CLI `--op-dynamic` pra revisão manual. Display mostra
  `(var)` em vez de vazio na coluna op.
- **F — WFPrepEnv emite `kind=wf_callback` separado de `workflow`**
  ([commit dd10dfc](https://github.com/JoniPraia/plugadvpl/commit/dd10dfc)).
  Antes ambos compartilhavam `kind=workflow`, queries por kind contavam
  duplicado em fontes com instanciação + callback. WorkflowKind enum
  atualizada (aceita `--kind wf_callback`).

### Added (Tier 1+2)
- **B — `doctor --check-funcs`** ([commit 53d6c53](https://github.com/JoniPraia/plugadvpl/commit/53d6c53)).
  Opt-in. Re-lê fontes em runtime, compara grep (`^[ \t]*(?:Static|User|Main)\s+Function\s+\w+`)
  vs count no DB por arquivo. Status warn quando discrepância (lista até 10 arquivos
  com counts). Surface tanto bugs de parser quanto commenting-out intencional —
  usuário decide caso-a-caso.
- **D — `caminho` (relativo) no JSON output de workflow/execauto/docs**
  ([commit 77f02ee](https://github.com/JoniPraia/plugadvpl/commit/77f02ee)).
  Antes filtro `--arquivo` casava basename mas display mostrava só basename.
  Em projetos com fontes homônimos em subdirs diferentes, usuário não via qual
  path foi indexado. Helper `_augment_with_caminho` injeta coluna `caminho` no
  display dict; em table mode não aparece (mantém layout enxuto), em JSON aparece
  sempre.
- **E — Sugestão de módulos disponíveis quando `--modulo X` não casa**
  ([commit 7aff67b](https://github.com/JoniPraia/plugadvpl/commit/7aff67b)).
  `execauto --modulo SIGAINEXISTENTE` agora lista top-5 módulos reais no índice
  via next_steps. Mesmo pra `docs [modulo]`. Queries novas:
  `execauto_top_modulos` / `protheus_docs_top_modulos`.
- **K — `workflow --duplicates`** ([commit 2824a82](https://github.com/JoniPraia/plugadvpl/commit/2824a82)).
  Feature derivada de uso real: o usuário descobriu por acidente que tinha 2
  TWFProcess para workflows diferentes com mesmo Process ID. Agora explícito:
  `workflow --duplicates` lista targets compartilhados entre 2+ fontes,
  agrupando por `(kind, target)` com `count >= 2`. Detecta erros de design
  (Process ID reusado, Main name colidindo, pergunte SX1 duplicada).

### Refactored (Tier 3)
- **G — `_split_top_level_commas` unificado em `parsing/_split.py`**
  ([commit 2848469](https://github.com/JoniPraia/plugadvpl/commit/2848469)).
  Antes: 3 implementações divergentes (triggers/execauto/protheus_doc) com
  pequenas diferenças (strings respeitadas ou não, `max_parts` ou não).
  Agora versão única, mais conservadora. Pure refactor.

### Polish (Tier 3 cosmético)
- **H — `serialize_json([])` grava `'[]'` em vez de `NULL`**
  ([commit dcd60c0](https://github.com/JoniPraia/plugadvpl/commit/dcd60c0)).
  Inspeção via sqlite3 cli fica clara. End-to-end equivalente.
- **I — `dict.fromkeys()` preservando ordem em next_steps** (mesmo commit).
  Substitui set comprehensions não-determinísticas — evita flake em snapshot
  tests futuros.
- **J — Regex SemVer/PEP440 estrita em fragment-version marker** (mesmo commit).
  Antes `[\d.+-]\S*` permitia qualquer non-whitespace. Agora exige
  `\d+\.\d+\.\d+[\w.+-]*` (aceita dev/rc/pre/build).

### Migration
- **Schema 8 → 9** (ADD COLUMN, não-breaking). DBs antigos populam `op_dynamic`
  com 0 default; re-ingest opcional pra colher valores corretos.

### Tests
- **+9 testes novos** (1 por item substantivo):
  - `test_parser.py::test_unclosed_block_comment_does_not_swallow_distant_function`
  - `test_parser.py::test_block_comment_short_legit_still_respected`
  - `test_doctor_check_funcs_detects_discrepancy`
  - `test_execauto_json_includes_caminho_relativo`
  - `test_workflow_duplicates_detects_shared_target`
  - `test_execauto_empty_modulo_suggests_available_modules`
  - `test_op_dynamic_variable` / `test_op_dynamic_expression` / `test_op_literal_not_dynamic`
- **508 testes verde** (era 499).

### Notes
- **Pronto pra Universo 4**: backlog deferred zerado. Próximo grande tema
  pode ser tackled sem dívida técnica pendente.

## [0.4.5] - 2026-05-18

### 🚨 Bug crítico — stripper engolia declarações Function após string mal-formada

Usuário em produção reportou que `Static Function` declarada não aparecia
no índice (`arch.funcoes` listava 4 de 5 funções declaradas no source).
Investigação revelou que o problema afetava **~9% dos fontes reais**
inspecionados (182 de ~2000), com perda silenciosa de funções inteiras
do índice.

### Fixed
- **Stripper agora encerra string ao encontrar `\n`** ([parsing/stripper.py:121-143](cli/plugadvpl/parsing/stripper.py)).
  Antes: ao encontrar string não-fechada na mesma linha (ex.: SQL
  concatenação com aspas duplas faltando o close), o stripper entrava em
  state `str_dq`/`str_sq` e consumia caracteres incluindo `\n` até achar
  o próximo `"`/`'` no arquivo — engolindo dezenas ou centenas de linhas,
  incluindo declarações `User/Static/Main Function` do meio.

  ADVPL não permite strings multi-linha. O fix encerra a string ao
  encontrar `\n` (volta a `code` state), preservando declarações
  subsequentes.

  Aplicado em ambos os modos do stripper:
  - `strip_strings=True` (default — comportamento padrão)
  - `strip_strings=False` (mode keep — usado por extratores de strings literais)

### Impact (medido em corpus real)
- **80.2% de redução** em fontes com discrepância: de 182 → 36 fontes.
- Comandos afetados que agora veem funções antes perdidas: `arch`, `find`,
  `callers`, `callees`, `docs --orphans`, lint cross-file (BP-007), todos
  que dependem do índice de funções.
- Sem necessidade de schema migration. Reindex (`plugadvpl ingest
  --no-incremental`) é recomendado pra colher as funções antes perdidas.

### Tests
- **+3 testes novos**:
  - `test_stripper.py::TestStrings::test_unclosed_double_quote_does_not_cross_newline`
  - `test_stripper.py::TestStrings::test_unclosed_single_quote_does_not_cross_newline`
  - `test_parser.py::TestExtractFunctions::test_unclosed_string_does_not_swallow_subsequent_functions`
- **499 testes verde** (era 498 — note que test_stripper.py exige `hypothesis`
  como dep dev e fica fora do CI padrão; os 2 novos rodam via test_parser).

### Limitações conhecidas (defer pra release dot futura)
- **Block comment `/* ... */` não-fechado** ainda pode engolir funções
  (~36 fontes remanescentes na corpus real). Diferente do caso string,
  ADVPL permite block comment multi-linha legitimamente (devs comentam
  funções inteiras dessa forma) — não dá pra fechar agressivamente sem
  quebrar uso intencional. Heurística defensiva (cap de N linhas, ou
  detectar `Function` em linha-própria dentro de comment) candidato pra
  v0.4.6.
- **Doctor check de discrepância func-count** (sugerido como defesa em
  profundidade na issue): defer pra v0.4.6. Implementação requer ou novo
  schema (coluna `funcoes_raw` em `fontes`) ou root path acessível ao
  comando `doctor`. Escopo maior — fica pra release dedicada.

### Notes
- Bug aberto desde v0.1.x — sempre esteve lá, só foi pego agora porque
  usuário com corpus real cross-referenciou docs manualmente com saída do
  `arch`.
- Padrão a manter: dogfooding com usuário em produção pega bugs que
  fixtures sintéticas não cobrem.

## [0.4.4] - 2026-05-18

### 🛡️ QA pack — fecha 2 bugs médios + 2 UX reportados em uso real

Usuário em produção (~2k fontes ADVPL, encoding cp1252) reportou 4 issues
com repro confirmado contra v0.4.3. Esta release corrige todos os 4 em
commits atômicos com TDD red→green.

### Fixed
- **BUG #1 — `grep` com padrão FTS5-inválido crashava com traceback**
  ([commit 2fde446](https://github.com/JoniPraia/plugadvpl/commit/2fde446)).
  Antes: `plugadvpl grep '//.*MsExecAuto' -m fts` propagava
  `OperationalError` cru → Typer/Rich imprimia traceback de ~30 linhas
  com paths internos vazando estrutura do plugin. Agora: catch
  `sqlite3.OperationalError` no comando `grep` quando `mode==fts` + mensagem
  amigável em stderr com sugestão de modo alternativo (`literal`/`identifier`).
  Operadores FTS5 válidos (`+`, `*`, `"frase"`, `OR`, `AND`, `NEAR`)
  continuam funcionando. Bug aberto desde v0.4.0.

- **BUG #2 — `docs --funcao`/`--show` falhava em WSSTRUCT/WSSERVICE/WSRESTFUL/WSMETHOD**
  ([commit b936616](https://github.com/JoniPraia/plugadvpl/commit/b936616)).
  Antes: `_NEXT_DECL_RE` só matchava `Function name(` e `Method name(`.
  Construtos de Web Service (sem parens) ficavam órfãos → coluna `funcao`
  ficava NULL → `--funcao <nome>` e `--show <nome>` retornavam vazio
  mesmo o doc estando indexado. Fix duplo:
  1. Regex estendida com grupo capturando `WS(STRUCT|SERVICE|RESTFUL|METHOD)`
  2. `protheus_docs_query`/`protheus_doc_show`/`protheus_doc_homonyms` agora
     matcham via `funcao OR funcao_id` — cobre DBs antigos sem reingest e
     blocos órfãos.
  4 testes unit + 1 integration end-to-end. Bug novo na v0.4.3
  (comando `docs` foi adicionado nessa versão).

### Changed (UX)
- **UX #3 — sugestão genérica de reingest em todo resultado vazio**
  ([commit 84149b4](https://github.com/JoniPraia/plugadvpl/commit/84149b4)).
  Antes: `workflow`/`execauto`/`docs` sempre sugeriam
  `plugadvpl ingest --no-incremental` quando retorno era vazio — mesmo quando
  o filtro com valor inexistente era a causa (não a tabela vazia). Usuário
  podia re-rodar ingest caro de 2k+ fontes sem necessidade. Agora: helper
  `_empty_result_hints(filters_applied, ...)` diferencia 2 cenários:
  1. filtro aplicado + vazio → sugere verificar argumentos (`find`/`status`)
  2. sem filtro + tabela vazia → sugere reingest

- **UX #4 — filtros enumeráveis inválidos retornavam vazio silenciosamente**
  ([commit 8550796](https://github.com/JoniPraia/plugadvpl/commit/8550796)).
  Antes: `execauto --op invalida` e `workflow -k tipoinexistente` retornavam
  vazio sem aviso. Agora: 2 Enums novos (`WorkflowKind`, `ExecAutoOp`) com
  `case_sensitive=False` — Typer rejeita valores fora do enum antes de chegar
  na query, com mensagem clara listando opções válidas.

### Tests
- **+8 testes novos** (1 integration pra cada fix + 4 unit pra cobertura
  WSSTRUCT/WSSERVICE/WSRESTFUL/WSMETHOD):
  - `TestGrep::test_grep_fts_invalid_syntax_friendly_error`
  - `TestDocs::test_docs_show_ws_constructs_end_to_end`
  - `TestExecauto::test_execauto_empty_with_filter_does_not_suggest_ingest`
  - `TestExecauto::test_execauto_rejects_invalid_op`
  - `TestWorkflow::test_workflow_rejects_invalid_kind`
  - `TestFunctionResolution::test_funcao_resolved_for_wsstruct` (+ wsservice/wsrestful/wsmethod)
- **498 testes verde** (era 489).

### Notes
- **Sem schema migration** — fix do BUG #2 inclui fallback na query (matcha
  `funcao OR funcao_id`), permitindo que DBs antigos funcionem sem reingest.
  Novos ingests via v0.4.4+ populam `funcao` corretamente pra WS constructs.
- **Padrão a manter**: code review pós-feature + dogfooding com usuário real
  + commits atômicos com TDD por fix continuam pegando bugs que tests sintéticos
  não viam (caso WS constructs reportado por usuário em produção).
- **Próximo grande tema**: pivot pra Universo 4 (a definir).

## [0.4.3] - 2026-05-15

### 🛡️ Polish pack — fecha 5 críticos + 4 importantes do code review pós-Universo 3

Code review independente identificou 5 bugs críticos com repro confirmado nas
3 features novas (v0.4.0/0.4.1/0.4.2) gerando dados errados em produção, mais
4 melhorias importantes de UX/cobertura. Esta release corrige todos os 9.

### Fixed
- **C1 (CRÍTICO) — workflow callbacks misturados entre TWFProcess vizinhos**.
  Antes (`triggers.py:142-152`): scope_end fixo de 5000 chars capturava
  callback do segundo `TWFProcess` e atribuía ao primeiro em fontes com
  múltiplos workflows. Agora: scope é limitado pela próxima instanciação
  `TWFProcess():New(`. Test de regressão `test_two_twfprocess_distinct_callbacks`.
- **C2 (CRÍTICO) — Protheus.doc fechava prematuramente em `/*/` literal dentro
  de `@example`**. Antes (`protheus_doc.py:28-35`): regex non-greedy
  `(?P<body>.*?)/\*/` casava qualquer `/*/`, mesmo em meio a comentário do
  exemplo. Agora: fechamento ANCORADO a start-of-line (`^[ \t]*/\*/[ \t]*$`),
  conforme padrão oficial TOTVS (fechamento fica sozinho na própria linha).
  Test `test_example_with_inline_close_marker_does_not_close`.
- **C3 (CRÍTICO) — RpcSetEnv perdia módulo com 6 args literais consecutivos**.
  Antes (`triggers.py:79-85`): regex única falhava quando
  `RpcSetEnv("01","01","","","FAT","J")` (sem vírgulas vazias) — o módulo
  ficava `''`. Agora: helper `_parse_rpcsetenv_args` usa paren-balanced split
  pra extrair args posicionais (5º arg = módulo). Test
  `test_rpcsetenv_six_literal_args_extracts_modulo`.
- **C4 (CRÍTICO) — bloco órfão de Protheus.doc "puxava" função 200+ linhas adiante**.
  Antes: `_resolve_next_decl` sem cap de proximidade — função distante ganhava
  doc errada e perdia sinal de "órfão". Agora: cap de 80 linhas; acima disso
  `funcao=None, linha_funcao=None` (preserva BP-007). Test
  `test_orphan_block_with_distant_function_treated_as_orphan`.
- **C5 (CRÍTICO) — `infer_module` retornava SIGAEST silenciosamente para `MATA999`**.
  Antes: prefix-match alfabético favorecia SIGAEST (porque MATA010-180 são
  SIGAEST). Agora: ambiguidade real (prefix casa múltiplos módulos) → `None`
  em vez de inventar. Prefixo `FINA` (100% SIGAFIN) ainda resolve. Test
  `test_module_ambiguous_prefix_returns_none`.

### Added
- **I1 — TMailManager solo (sem TMailMessage) detection**. Fontes legados
  com `TMailManager():New() + :SendMail()` (anteriores ao TMailMessage)
  agora viram trigger `mail_send` corretamente. Test
  `test_positive_tmailmanager_solo_without_tmailmessage`.
- **I2 — `docs --show` com homônimos**. Antes: pegava o primeiro silenciosamente.
  Agora: avisa em stderr quantos fontes têm a função, lista os basenames, e
  aceita `--arquivo <nome>` pra desambiguar. Integration test
  `test_docs_show_homonym_warns_and_supports_arquivo`.
- **I5 — catálogo execauto ganha 6 rotinas comuns + dup test**:
  - `MATA020` (SA2 — Cadastro Fornecedores SIGACOM)
  - `MATA040` (SA6 — Cadastro Bancos SIGAFIN)
  - `MATA112` (SE4 — Plano de Pagamento SIGAFIN)
  - `FATA010` (AE1 — Bandeiras de Cartão SIGAFAT)
  - `FATA050` (SC9 — Liberação de Pedidos SIGAFAT)
  - Catálogo agora tem 31 rotinas (era 25)
  - Test `test_catalog_no_duplicate_routines` previne sobrescrita silenciosa.
- **I6 — índices em `funcao` nas tabelas Universo 3** (migration 008).
  `idx_exec_funcao` em `execution_triggers`, `idx_execauto_funcao` em
  `execauto_calls`. `protheus_docs` já tinha. Queries cross-ref
  ("quais funções no fonte X chamam ExecAuto?") agora usam índice.

### Migration
- **Schema 7 → 8** (não-breaking; só adiciona índices em colunas existentes).

### Tests
- **+11 tests novos** (5 unit pra C1/C2/C3/C4/C5 + 1 unit pra I1 + 2 unit
  pra I5 + 1 integration pra I2 + 2 sanity pra C4/C5 contornos):
  - `test_triggers.py`: +3 (C1, C3, I1)
  - `test_protheus_doc.py`: +5 (C2, C4×2, C5×2)
  - `test_execauto.py`: +2 (I5×2)
  - `test_cli.py::TestDocs`: +1 (I2)
- **489 testes verde** (era 478). Cobertura GREEN end-to-end.

### Deferred (próxima release polish)
- I3 (WFPrepEnv standalone duplica trigger) — semântica ambígua, precisa
  decisão de design separada
- I4 (`op_code = nVar` sem flag dedicado) — adicionar coluna `op_dynamic`
  em release dot futura
- I7 (ambiguidade `--arquivo` quando 2 fontes mesmo basename) — JOIN com
  `caminho_relativo` em release de polish UX
- N1-N5 (refactors e doc) — backlog

### Notes
- **5 críticos com repro confirmado**: revisão pós-feature evitou que dados
  errados ficassem em produção. Padrão a manter: `code-reviewer` agente
  pós-grandes-features.
- **Próximo grande tema**: pivot pra **Universo 4** (a definir — candidatos:
  qualidade & métricas, complexidade ciclomática, hot-paths, ownership).

## [0.4.2] - 2026-05-15

### 🎉 Universo 3 — fechamento (Feature C: Protheus.doc agregada)

**Última feature do Universo 3 (Rastreabilidade).** Indexa blocos
`/*/{Protheus.doc} ... /*/` com 16 tags canônicas TOTVS, agrega por
módulo/autor/tipo/deprecation, e oferece modo `--show <funcao>` que renderiza
doc completo em Markdown estruturado — agente IA copia direto pro contexto
sem abrir o fonte.

**Universo 3 completo:**
- ✅ **A (v0.4.0)** — execução não-direta (workflow/schedule/job/mail)
- ✅ **B (v0.4.1)** — chamada indireta (ExecAuto chain → tabelas)
- ✅ **C (v0.4.2)** — documentação inline (Protheus.doc)

### Added
- **Detector `parsing/protheus_doc.py`** — `extract_protheus_docs(content,
  arquivo=...)` extrai blocos completos com 16 tags estruturadas:
  - Single: `@type`, `@author`, `@since`, `@version`, `@description`,
    `@language`, `@deprecated` (+ reason)
  - Multi: `@param` (name+type+desc+optional), `@return` (type+desc),
    `@example`/`@sample`, `@history` (date+user+desc), `@see`, `@table`,
    `@todo`, `@obs`, `@link`
  - Tags fora do whitelist vão pro `raw_tags` catch-all (zero perda)
- **Tabela `protheus_docs`** (schema v6→v7, migration 007) — 26 colunas:
  6 quentes estruturadas (module/author/tipo/since/deprecated/funcao),
  10 JSON arrays pra multi-valor, `raw_tags_json` catch-all. 5 índices.
- **Inferência de módulo** — algoritmo dual:
  1. Path-based: regex `SIGA\w{3,4}` no caminho relativo
  2. Routine-prefix: reaproveita catálogo da Feature B (`MATA*` → SIGAFAT)
     com exact match prioritário e fallback alfabético determinístico
  3. Fallback: `null` (sem invenção)
- **Comando `plugadvpl docs [modulo]`** com 3 modos + 5 filtros:
  - **Lista**: `docs SIGAFAT` ou `docs --author X --deprecated`
  - **Show**: `docs --show MT460FIM` → Markdown estruturado (cabeçalho +
    tabela params + sections retorno/exemplos/histórico)
  - **Orphans**: `docs --orphans` → cross-ref BP-007 do lint (funções sem header)
  - Filtros: `--author` (LIKE), `--funcao` (exact), `--arquivo`,
    `--deprecated/--no-deprecated`, `--tipo`
- **Skill `/plugadvpl:docs`** — documentação completa com 6 casos de uso.
- **Counter** `protheus_docs` no contador de ingest + meta `total_protheus_docs`.

### Tests
- **28 testes unit** (`tests/unit/test_protheus_doc.py`):
  TestBlockParsing (5), TestTagExtraction (8), TestModuleInference (6),
  TestEdgeCases (6), TestFunctionResolution (3).
- **8 testes integration** (`tests/integration/test_cli.py::TestDocs`):
  fixture com 3 fontes (doc completo SIGAFAT, deprecated, órfão); cobre
  todos os modos + filtros + sanity DB.
- **470 testes verde** (era 442).

### Migration
- **Schema 6 → 7** (não-breaking; só adiciona tabela).

### Padrão TOTVS
- Spec oficial: [tds-vscode/docs/protheus-doc.md](https://github.com/totvs/tds-vscode/blob/master/docs/protheus-doc.md)
- Reaproveita o catálogo `execauto_routines.json` da Feature B pra inferência
  de módulo via prefixo de rotina (MATA*/FINA*/CTBA*/EECAP*/TMSA* → módulo).

### Casos de uso
1. *"Catálogo do módulo Faturamento"* → `/plugadvpl:docs SIGAFAT`
2. *"Quem escreveu o quê?"* → `/plugadvpl:docs --author "Fernando"`
3. *"O que está deprecated?"* → `/plugadvpl:docs --deprecated`
4. *"Doc completa sem abrir o fonte"* → `/plugadvpl:docs --show MT460FIM`
5. *"Cobertura de documentação"* → `/plugadvpl:docs --orphans`

### Notes
- **Spec aprovado** em `docs/universo3/C-protheus-doc.md` antes do código.
- **Fechamento Universo 3**: A (workflow) + B (execauto) + C (docs) entregues
  em 3 dot-releases consecutivos (v0.4.0 → v0.4.1 → v0.4.2).
- **Próximo grande tema natural**: pivot pra **Universo 4** (a definir —
  candidatos: qualidade & métricas, complexidade ciclomática, hot-paths,
  ownership analytics).
- **Limitações conhecidas** (em `skills/docs/SKILL.md`):
  - Headers legados pré-Protheus.doc (ASCII art `+--+`) não detectados
  - Inline `//{pdoc}` (associado a próxima variável) fora do MVP
  - Bloco sem `/*/` fechamento ignorado (BP-007b candidato futuro)
  - Cross-validação `@param` vs assinatura real fora do MVP (BP-009 candidato)

## [0.4.1] - 2026-05-15

### 🚀 Universo 3 — Rastreabilidade Feature B (ExecAuto chain expansion)

Resolve a indireção do `MsExecAuto({|x,y,z| MATA410(x,y,z)}, ...)` e cruza
com catálogo TOTVS (25 rotinas) pra **inferir tabelas tocadas indiretamente**.
Antes: `arch` mostrava `tabelas: []` mesmo o fonte chamando `MATA410` (que
toca SC5/SC6) via ExecAuto. Agora: `tabelas_via_execauto_resolvidas: ["SC5","SC6","SF4","SB1"]`.

### Added
- **Catálogo `lookups/execauto_routines.json`** — 25 rotinas TOTVS canônicas
  (MATA010/030/050/075/103/110/120/125/150/180/220/242/261/310/311/410/460/461,
  FINA040/050/070/080, CTBA102, EECAP100, TMSA500) com `routine`, `module`,
  `type`, `tables_primary`, `tables_secondary`, `source_url`, `verified`.
  Rotinas faltantes ainda são detectadas (com `module=null`); expansão via PR.
- **Detector `parsing/execauto.py`** — `extract_execauto_calls(content)` extrai
  chamadas `MsExecAuto`/`ExecAuto` (case-insensitive), parseia codeblock pra
  achar a rotina, detecta `op_code` (3/4/5 → inclusao/alteracao/exclusao),
  flag `dynamic_call` pra `&(cVar)` ou codeblock vazio.
- **Tabela `execauto_calls`** (schema v5→v6, migration 006) — 1 row por chamada
  com `arquivo, funcao, linha, routine, module, routine_type, op_code,
  op_label, tables_resolved_json, dynamic_call, arg_count, snippet`. 3 índices.
- **Comando `plugadvpl execauto`** com filtros `--routine`/`--modulo`/
  `--arquivo`/`--op` (inc/alt/exc)/`--dynamic`. Skill `/plugadvpl:execauto`.
- **Enrichment de `arch`** — campo novo `tabelas_via_execauto_resolvidas:
  list[str]` agregando tabelas inferidas. Campo bool antigo
  `tabelas_via_execauto` continua (não-breaking).
- **Counter** `execauto_calls` no contador de ingest + meta `total_execauto_calls`.

### Tests
- **26 testes unit** (`tests/unit/test_execauto.py`):
  TestRoutineResolution (6), TestOpCodeDetection (5), TestDynamicCall (2),
  TestEdgeCases (6), TestCatalog (3), TestMetadataFields (4).
  Cobre todas as 8 sintaxes documentadas no spec + 11 edge cases.
- **8 testes integration** (`tests/integration/test_cli.py::TestExecauto`):
  fixture com 3 fontes (MATA410 inc, FINA050 inc, dynamic), exercita
  `--routine`/`--modulo`/`--dynamic`/`--op` + arch enrichment + DB sanity.
- **434 testes verde** (era 408).

### Migration
- **Schema 5 → 6** (não-breaking; só adiciona tabela). DBs v0.4.0 são reindexados
  automaticamente no próximo `init`.

### Casos de uso
1. *"Quem inclui Pedido de Venda automaticamente?"* →
   `/plugadvpl:execauto --routine MATA410 --op inc`
2. *"Quais fontes integram com SIGAFIN via ExecAuto?"* →
   `/plugadvpl:execauto --modulo SIGAFIN`
3. *"Cobertura real de tabelas deste fonte?"* →
   `arch X.prw` agora mostra `tabelas_via_execauto_resolvidas`
4. *"Auditar exclusões automáticas"* →
   `/plugadvpl:execauto --op exc`
5. *"Calls não-resolvíveis (precisam revisão manual)?"* →
   `/plugadvpl:execauto --dynamic`

### Notes
- **Spec aprovado** em `docs/universo3/B-execauto-chain.md` antes do código
  (workflow research → spec MD → approval → code).
- **Próximo passo Universo 3**: Feature C (Protheus.doc agregada por módulo —
  `/plugadvpl:docs <modulo>`).
- **Limitações conhecidas** (em `skills/execauto/SKILL.md`):
  - Variável armazenada (`bExec := {...}; MsExecAuto(bExec, ...)`) → flag dynamic
    (precisaria data-flow analysis, fora do MVP)
  - Macro-substituição `&(cRot)` → flag dynamic (raro)
  - Rotinas fora do catálogo → detectadas com `module=null` (PR-friendly)
  - `op_code` por convenção (último arg numérico literal); `nOpc` em variável
    fica `null`

## [0.4.0] - 2026-05-15

### 🚀 Universo 3 — Rastreabilidade (Feature A: Workflow + Schedule + Job + Mail)

**Killer feature do v0.4.x**: indexação dos 4 mecanismos canônicos TOTVS de
**execução não-direta**. Antes do v0.4.0 era impossível responder via plugin
"essa rotina é alvo de workflow ou helper?", "que jobs do AppServer existem
nesse projeto?", "qual schedule dispara `FATR020`?", "onde envio email com
anexo?". Agora 1 comando responde tudo: `/plugadvpl:workflow`.

### Added
- **Tabela `execution_triggers`** (schema v5, migration `005_universo3_execution_triggers.sql`)
  com colunas `id, arquivo, funcao, linha, kind, target, metadata_json, snippet`.
  3 índices: `idx_exec_arquivo`, `idx_exec_kind`, `idx_exec_target`.
- **Detector `parsing/triggers.py`** com 4 detectores:
  - `workflow` — `TWFProcess():New(...)`, `MsWorkflow(`, `WFPrepEnv(` em callbacks.
    Metadata: `process_id`, `description`, `template`, `to`, `subject`,
    `return_callback`, `timeout_callback`, `is_legacy`.
  - `schedule` — `Static Function SchedDef()` retornando array
    `{cTipo, cPergunte, cAlias, aOrdem, cTitulo}`. Metadata: `sched_type` (P/R),
    `pergunte` (referência SX1), `alias`, `ordens`, `titulo`.
  - `job_standalone` — `Main Function` + `RpcSetEnv` + `Sleep` loop (daemon
    ONSTART). Metadata: `main_name`, `empresa`, `filial`, `modulo`,
    `sleep_seconds`, `stop_flag`, `no_license`.
  - `mail_send` — `MailAuto(`, `SEND MAIL` UDC, `TMailManager`/`TMailMessage`.
    Metadata: `variant`, `has_attachment`, `uses_mv_rel` (cross-ref com SEC-004).
- **Comando `plugadvpl workflow`** (e skill `/plugadvpl:workflow`) com filtros
  `--kind`, `--target`, `--arquivo`. Usa metadata JSON pra detalhe por tipo.
- **Resolução de `funcao`** — usa o índice de chunks (v0.3.15+) pra mapear
  cada trigger à função-pai onde foi declarado.
- **Idempotência** — DELETE+INSERT no `_clear_for_arquivo` (padrão v0.3.28).
- **Counter** `execution_triggers` no contador de ingest + `total_execution_triggers`
  em `meta` (visível via `plugadvpl status`).

### Tests
- **14 testes unit** (`tests/unit/test_triggers.py`):
  5 classes (TestWorkflowTrigger, TestScheduleTrigger, TestJobStandaloneTrigger,
  TestMailSendTrigger, TestMultiTriggerSource), positivos + negativos por kind.
- **5 testes integration** (`tests/integration/test_cli.py::TestWorkflow`):
  fixture `triggers_project` com 3 fontes (1 workflow, 1 schedule, 1 job+mail
  multi-trigger), exercita todos os filtros + sanity check no DB.
- **408 testes verde** (era 389).

### Migration
- **Schema 4 → 5** (breaking; `plugadvpl init` em DBs existentes força reindex).
  Nenhum dado de v0.3.x perdido — `chunks`, `lint_findings`, `simbolos`, etc
  continuam intactos. Apenas a tabela nova é criada.

### Casos de uso
1. *"Esta User Function `XYZAprov` é alvo de workflow?"* →
   `/plugadvpl:workflow --target XYZAprov` (se aparecer com `kind=workflow`, é callback).
2. *"Que Main Functions deste projeto são jobs daemon?"* →
   `/plugadvpl:workflow --kind job_standalone`.
3. *"Esse `FATR020.prw` é agendável?"* →
   `/plugadvpl:workflow --arquivo FATR020.prw --kind schedule`
   (metadata.pergunte aponta o grupo SX1 — cruzar com `/plugadvpl:param`).
4. *"Onde envio email com anexo?"* →
   `/plugadvpl:workflow --kind mail_send` + filtrar `metadata.has_attachment=True`.
5. *"Esse fonte usa SX6 ou hardcoded?"* →
   `mail_send` com `metadata.uses_mv_rel=True` (correto) ou `False`
   (cruzar com SEC-004 do lint).

### Notes
- **Spec aprovado** em `docs/universo3/A-workflow-schedule.md` antes do código
  (workflow novo: research → spec MD → approval → code).
- **Próximo passo Universo 3**: Feature B (ExecAuto chain expansion — primeiro
  arg do `MsExecAuto` resolvido pra alvo + tabelas) e Feature C (Protheus.doc
  agregada por módulo).
- **Limitações conhecidas** (documentadas em `skills/workflow/SKILL.md`):
  frequência de schedule (`SCHTSK`/`SCHFIL`/`SCHSERV`), AppServer.ini
  (`[ONSTART]`), e `TWebChannel` workflow webview ficam fora do MVP.

## [0.3.30] - 2026-05-15

### 🎉 Audit V4 closeout — fecha 3 dos 4 últimos itens. Sobra apenas #14 (SX-005 carrega 50-250MB corpus em monorepo gigante) que o próprio auditor classificou como "tradeoff aceitável, comment já justifica". **Backlog técnico zerado para uso prático.** 14 dos 15 achados de Audit V4 endereçados em 3 releases (v0.3.28, v0.3.29, v0.3.30).

### Fixed
- **#8 (BAIXA) — PERF-006 cross-table determinismo**. Antes iterava
  `dict.items()` (ordem não-determinística) e parava no primeiro match —
  em projeto com prefixo de coluna compartilhado entre tabelas (raro mas
  existe: `SR8` + extension `SR8XYZ`), a coluna podia ser reportada como
  não-indexada apenas porque a primeira tabela visitada não tinha o
  índice. Agora coleta TODAS as tabelas candidatas (sorted = determinístico),
  decide "indexada se em qualquer uma", reporta contra a primeira candidata
  alfabética caso negativa.
- **#9 (BAIXA) — SEC-005 ignora função homônima local**. Antes, se o
  fonte definia `User Function StaticCall(cArg)` (homônima a TOTVS-restrita
  catalogada), as chamadas a `StaticCall(...)` no mesmo fonte disparavam
  SEC-005 erroneamente. Cenário improvável mas possível em PEs canônicas
  (`MT100LOK`, `ANCTB102GR`, etc — clientes podem criar User Function
  homônima). Agora coleta nomes definidos localmente (kinds: `user_function`/
  `static_function`/`main_function`/`function`/`method`) e skipa.

### Added
- **#10 (BAIXA) — PERF-006 emite warning quando `indices` SX vazia**.
  Antes retornava `findings = []` silenciosamente — usuário rodava
  `lint --cross-file --regra PERF-006`, recebia 0 findings, e não sabia se
  era "sem problema" ou "sem dado SX ingerido". Agora detector imprime
  amarelo em stderr explicando: "WARN: PERF-006 ha N SQL com WHERE/ORDER BY
  pra avaliar, mas tabela `indices` (SIX) esta vazia. Cobertura limitada —
  rode `plugadvpl ingest-sx <pasta-csv>` com SX dictionary completo
  (incluindo six.csv) pra habilitar deteccao de coluna sem indice."
- `import sys` em `lint.py` (era ausente — necessário pro print stderr).

### Tests
- 3 testes RED→GREEN:
  - `tests/unit/test_lint.py::TestSec005LocallyDefinedFunction::test_negative_local_user_function_homonyma` (#9 negativo)
  - `tests/unit/test_lint.py::TestSec005LocallyDefinedFunction::test_positive_external_call_still_fires` (#9 positivo regressão)
  - `tests/integration/test_ingest_sx.py::TestLintCrossFile::test_lint_cross_file_perf006_warns_when_indices_empty` (#10 stderr warning)
- 389 testes verde (era 386).

### Notes
- **Audit V4 closeout — 14/15 endereçados, 1 documented tradeoff**:
  - #1, #2, #3, #5, #6, #11, #15 → v0.3.28 (lint robustness pack 1)
  - #4, #7, #12, #13 → v0.3.29 (lint robustness pack 2)
  - #8, #9, #10 → v0.3.30 (este release)
  - #14 (SX-005 corpus 50-250MB) → tradeoff documentado (auditor classificou
    como "atual eh aceitavel; nao otimizar prematuramente")
- **Total ciclo QA do projeto** (rounds 1+2+3 + audit técnico V4 = 51 achados,
  50 endereçados em 17 releases, v0.3.14 → v0.3.30). 1 deferido (não-bug).
- **Próximo grande tema natural**: pivot pra **v0.4.0 Universo 3** — workflows,
  schedules, integrações cross-fonte. Catálogo lint fechado, robustness
  fechada, ciclo QA fechado.

## [0.3.29] - 2026-05-15

### Lint robustness pack 2 — fecha mais 4 dos 8 restantes do `gaps/PLUGADVPL_LINT_AUDIT_V4.md`. Foco em precision/recall: PERF-004 hungarian estrito, BP-005 paren balance, BP-001 RecLock variável/físico, SEC-003 sufixo CamelCase. Sobram 4 de severidade média/baixa (PERF-006 determinismo, SEC-005 homônima local, PERF-006 fallback, SX-005 corpus 50-250MB).

### Fixed
- **#4 (MÉDIA) — PERF-004 hungarian estrito (`c[A-Z]\\w*`)**. Antes
  `c[A-Za-z_]\\w*` casava `cnt` (counter), `csv`, `cmd`, `crm` — siglas 3
  letras lowercase comuns em ADVPL legado. Estrito exige segunda letra
  MAIÚSCULA, eliminando FP sem perder casos hungarianos válidos
  (`cBuffer`, `cMsg`, `cAcc`, etc).
- **#13 (BAIXA) — BP-005 paren balance em params**. Antes
  `params_text.count(",") + 1` inflava contagem em defaults com array
  literal `{1,2,3}` ou função aninhada `MyFn(1,2,3)`. Função com 5 params
  reais + `cD := {1,2,3}` virava 7 params apparent → BP-005 falso
  positivo. Helper novo `_count_top_level_commas(text)` ignora vírgulas
  dentro de `()`/`{}`/`[]`.
- **#7 (MÉDIA) — BP-001 detecta RecLock com físico/variável**. Antes
  `\\w{2,3}` perdia alias físico (`SA1010`, 6 chars) e variável (`cTab`,
  sem aspas). Agora:
  - `_RECLOCK_OPEN_RE` aceita literal 2-7 chars (cobre alias lógico SA1
    + físico SA1010).
  - `_RECLOCK_OPEN_VAR_RE` (novo) captura `RecLock(<identifier>, ...)`
    sem aspas — cenário comum em scripts de migração e rotinas reuse.
  - `_RECLOCK_VIA_ALIAS_RE` também 2-7 chars.
- **#12 (BAIXA) — SEC-003 forma curta aceita sufixo CamelCase**. Antes
  `\\bc(?:Pwd|Rg|Pin|Card|Pass)\\b` exigia boundary após o termo —
  perdia variantes legítimas como `cPwdHash` (hash de senha continua
  PII), `cRgEmissor` (info do RG), `cCardNumber`, `cPinAtual`. Agora
  `\\bc(?:Pwd|Rg|Pin|Card|Pass)(?:[A-Z]\\w*)?\\b` aceita sufixo iniciado
  em maiúscula. Continua não-pegando `cPassagem`/`cCardapio` (próxima
  letra é minúscula = parte de palavra PT-BR).

### Tests
- 11 testes RED→GREEN em `test_lint.py`:
  - `TestPerf004HungarianStrict` — 4 testes (2 negativos `cnt`/`csv` +
    2 positivos `cBuffer`/`cAcc`).
  - `TestBp005ParenBalance` — 3 testes (2 negativos com `{1,2,3}` +
    `MyFn(1,2,3)` defaults + 1 positivo regressão 7 params reais).
  - `TestBp001RecLockExtended` — 2 testes (físico `SA1010` + variável
    `cTab`).
  - `TestSec003ShortFormSuffix` — 2 testes (`cPwdHash` + `cRgEmissor`).
- 386 testes verde (era 375).

### Notes
- **Backlog Audit V4 restante (4 itens, todos baixos)**:
  - #8 (PERF-006 cross-table match não-determinístico — depende de ordem
    de `dict.items()`).
  - #9 (SEC-005 não distingue função homônima custom local — improvável
    mas possível em PEs canônicos).
  - #10 (PERF-006 sem aviso quando `indices` SX vazia — UX, não bug).
  - #14 (SX-005 carrega 50-250MB corpus em memória — só problema em
    monorepo gigante; comment já justifica como aceitável).
- **Quase fim do backlog técnico**. Continuar com #8 + #9 fecharia 100%
  do Audit V4. #10 é UX simples. #14 é trade-off documentado.

## [0.3.28] - 2026-05-15

### Lint robustness pack — fecha 7 dos 15 achados de `gaps/PLUGADVPL_LINT_AUDIT_V4.md`. Foco em correctness técnica: persist cross-file, SQL truncation, regex frágeis. Sobram 8 médios/baixos no backlog (PERF-004 hungarian estrito, BP-001 RecLock variável, PERF-006 cross-table determinismo, etc).

### Fixed
- **#1 (CRÍTICO) — `persist_cross_file_findings` apagava só `LIKE 'SX-%'`**.
  MOD-003 (v0.3.26) e PERF-006 (v0.3.27) acumulavam findings duplicados a
  cada execução de `lint --cross-file`. Fix: deriva lista de regra_ids
  diretamente de `_CROSS_FILE_RULES` e usa `DELETE WHERE regra_id IN (...)`.
- **#2 (ALTA) — `_SQL_SNIPPET_MAX` bumpado 300 → 8000**. Antes, queries
  MVC com 2+ JOINs ultrapassavam 300 chars e tinham `%notDel%`/`%xfilial%`
  truncados pra fora do snippet → PERF-002/003/006 disparavam falso
  positivo massivo em código real Protheus de faturamento/financeiro.
  8000 cobre 99% de SQL ADVPL real; custo DB <1MB extra em projeto grande.
- **#3 (ALTA) — `_CLIENT_PREFIX_RE` removeu prefixos PT-BR ambíguos**.
  Antes incluía `FAT|FIN|COM|EST|CTB|FIS|PCP|MNT` (módulos Protheus, mas
  casavam palavras PT-BR comuns como `FATURA`, `COMPRA`, `FINALIZA`,
  `ESTOQUE`) → SEC-002 escapava o caso canônico (User Function PT-BR sem
  prefix). Removidos também `U_` (dead code: parser extrai nome SEM `U_`)
  e `MT[A-Z]/MA\\d` (já cobertos por `_PE_NAME_RE`). Sobram apenas iniciais
  genuinamente "de empresa": `ABC|MZF|ZZF|ZF|XX|XYZ|CLI`.
- **#5 (MÉDIA) — SX-009 `\\b\\.F\\.\\b` nunca casava**. `.` é non-word, então
  `\\b` antes de `.` exige um word-char à esquerda — impossível em `init=.F.`
  (`=` também é non-word). Drift catálogo×impl silencioso desde criação da
  regra. Fix: trocou por lookarounds `(?<![A-Za-z0-9_])\\.F\\.(?![A-Za-z0-9_])`.
- **#5 bonus — `inicializador` lia de `X3_RELACAO` em vez de `X3_INIT`**.
  Bug de mapping no `parse_sx3` causava SX-009 ler o campo errado. X3_INIT
  é o initializer canônico TOTVS (valor padrão); X3_RELACAO é autofill por
  expressão. Fix: lê X3_INIT prioritariamente, fallback X3_RELACAO pra
  compat com fixtures legadas.
- **#6 (BAIXA) — Mensagem SX-009 citava `X3_RELACAO` em vez de `X3_INIT`**.
  Texto do fix_guidance corrigido pra refletir o campo correto.
- **#11 (BAIXA) — BP-007 skipava `kind="mvc_hook"` que não existe**. Parser
  emite kinds `user_function/static_function/main_function/function/ws_method/method`
  — nenhum `mvc_hook`. Branch removido (dead code + comentário enganoso).
- **#15 (BAIXA) — BP-002 `fix_guidance` tinha frase de BP-006**. Última
  frase falava "NUNCA misture funções de manutenção AdvPL básicas com
  Framework dentro do mesmo bloco" — copy-paste do BP-006. Substituída
  por dica MVC apropriada (`oModel:CommitData()` em vez de Begin/End
  manual).

### Tests
- 6 testes RED→GREEN em `test_lint.py` + `test_ingest_sx.py`:
  - `TestLintCrossFile::test_lint_cross_file_persist_does_not_accumulate_mod003` (#1)
  - `TestPerf002NoNotDel::test_negative_long_sql_with_notdel_after_300_chars` (#2)
  - `TestSec002UserFunctionNoPrefix::test_positive_pt_br_word_FATURA` (#3)
  - `TestSec002UserFunctionNoPrefix::test_positive_pt_br_word_COMPRA` (#3)
  - `TestSec002UserFunctionNoPrefix::test_positive_pt_br_word_FINALIZA` (#3)
  - `TestLintCrossFile::test_lint_cross_file_sx009_detects_dot_F_dot_init` (#5+#6)
- 375 testes verde (era 369).

### Notes
- **Backlog Audit V4**: dos 15 achados, 7 fechados nesta release. Continuam
  pendentes (todos médios/baixos, sem urgência):
  - #4 (PERF-004 dispara em `cnt`/`csv` — solução exigir `c[A-Z]\\w*` estrito)
  - #7 (BP-001 perde RecLock com físico/variável — recall vs precision)
  - #8 (PERF-006 cross-table match não-determinístico)
  - #9 (SEC-005 não distingue função homônima local)
  - #10 (PERF-006 sem fallback gracioso `indices` vazia)
  - #12 (SEC-003 forma curta `\\b...\\b` ignora `cPwdHash` etc)
  - #13 (BP-005 conta vírgula naive em default `{1,2}`)
  - #14 (SX-005 carrega 50-250MB corpus em memória)
- **Re-ingest recomendado**: `plugadvpl ingest --no-incremental` aplica fix
  #2 (snippet 8000) em fontes já indexados. Sem isso, snippets antigos
  continuam truncados a 300 e PERF-002/003/006 vão continuar com FP.

## [0.3.27] - 2026-05-15

### 🎉 Catálogo lint 100% ativo. Última regra `planned` (PERF-006) implementada — fecha o ciclo iniciado em v0.3.4 (catálogo × impl alignment) com **35/35 regras detectáveis automaticamente**.

### Added
- **PERF-006 (info, cross-file) — WHERE/ORDER BY em coluna sem índice SIX**.
  Detector cross-file que requer `ingest-sx` (precisa da `indices` SIX).
  Skipa graciosamente quando ausente. Heurística:
  1. Lê `sql_embedado` rows com `WHERE` ou `ORDER BY` no snippet.
  2. Extrai colunas estilo `<TBL>_<NOME>` (regex `[A-Z][A-Z0-9]{1,2}_<NOME>`
     — cobre `A1_COD`, `B1_DESC`, `RA_CIC`, `R8_TIPO`, etc).
  3. Filtra pseudo-colunas Protheus (`D_E_L_E_T_`, `R_E_C_N_O_`,
     `R_E_C_D_E_L_`) e `*_FILIAL` (sempre primeira chave em qualquer
     composto, nunca causa scan).
  4. Cruza com cache `{tabela: {colunas em qualquer chave}}` derivado
     de `indices.chave`.
  5. Coluna NÃO em nenhum índice → emite finding com `tabela.coluna`.
  
  Heurísticas conservadoras (severidade `info`, baixo FP):
  - Skipa coluna sem prefixo claro de tabela (alias dinâmico no SQL).
  - Skipa quando tabela ausente em `indices` (provável standard, não custom).
  - Dedup por `(arquivo, linha, tabela, coluna)`.
- Helpers em `lint.py`:
  - `_PERF006_PSEUDO_COLS` — set com pseudo-colunas Protheus a ignorar.
  - `_PERF006_COLUMN_RE` — regex coluna estilo `A1_COD` (suporta dígito no prefix).
  - `_PERF006_WHERE_RE` / `_PERF006_ORDERBY_RE` — extração de cláusula
    com lookahead pra próximas keywords (GROUP BY/HAVING/EndSql/$).

### Changed
- Catálogo `lookups/lint_rules.json`: PERF-006 `status="planned"` → `"active"`
  + `impl_function="_check_perf006_where_orderby_no_index"` + descrição
  expandida com algoritmo completo + lista de exclusões.
- Skill `advpl-code-review`:
  - Frontmatter: `34 → 35` regras, `12 → 13` cross-file.
    **"100% do catálogo"** explícito.
  - Tabela cross-file: nova entrada PERF-006.
  - Nova seção "Catálogo 100% ativo (v0.3.27)" substitui "regras planned".
  - "Info / Checklist mental" reescrita pra "Catálogo 100% automatizado" —
    não há mais checklist humano residual.
- 18 skills bumpadas `@0.3.26` → `@0.3.27`.

### Tests
- `tests/integration/test_ingest_sx.py::TestLintCrossFile::test_lint_cross_file_perf006_where_orderby_no_index`:
  fixture com 2 fontes — `QrySemIdx.prw` (BeginSql `WHERE A1_NOME = ...`,
  não indexado) deve disparar PERF-006; `QryComIdx.prw` (`WHERE A1_COD = ...`,
  indexado em SA1#1) NÃO deve disparar.
- 369 testes verde (era 368).

### Notes
- **Marco do projeto**: catálogo iniciou em v0.3.0 com 35 regras (24 active +
  11 planned). Após 27 releases, fechamento total: **35 active + 0 planned**.
  Total de testes cresceu de ~252 (v0.3.13) → 369 (v0.3.27), +117 testes
  cobrindo novos detectores.
- **PERF-006 é conservadora por design**: severidade `info` significa que
  não bloqueia merge/CI. Em projetos com SX rico mas standard tables não
  ingeridas, FP é baixo (skipa quando tabela ausente em `indices`).
- **Próximo grande tema natural**: pivot pra **v0.4.0 Universo 3
  (Rastreabilidade)** — workflows, schedules, integrações cross-fonte —
  com tranquilidade. Catálogo lint fechado, ciclo QA fechado.

## [0.3.26] - 2026-05-15

### MOD-003 implementado — primeira regra cross-file que NÃO requer SX. Sobra apenas PERF-006 (a mais complexa) pra fechar 100% do catálogo.

### Added
- **MOD-003 (info, cross-file) — grupos de Static Function por prefixo**.
  Detector roda no orchestrator cross-file mas opera só sobre `fonte_chunks`
  (não exige `ingest-sx`). Heurística:
  - Agrupa Static Functions por **arquivo + prefixo**.
  - Testa lengths de prefixo de **6 → 3 chars**, escolhe o maior que ainda
    forma grupo de **>=3 funções**.
  - Suprime grupos cujo prefixo já foi capturado por um mais específico
    (ex: emitir `_AppCalc` evita re-emitir `_App` redundante).
  - 1 finding por grupo, na linha da primeira função.
  - Sugestão de fix orienta refatorar pra `Class T<Nome>` com `Data` +
    `Method` (TLPP `class` com `public/private/protected`).

### Changed
- **`_CROSS_FILE_RULES` agora é tupla de 3** `(regra_id, check_fn, requires_sx)`.
  - `requires_sx=True` (SX-001..SX-011) pula quando dicionário SX não foi
    ingerido (comportamento existente).
  - `requires_sx=False` (MOD-003) sempre roda.
  - `lint_cross_file()` checa o flag por regra em vez de gate global no início.
- Catálogo `lookups/lint_rules.json`: MOD-003 `status="planned"` → `"active"`
  + `impl_function="_check_mod003_static_funcs_to_class"` + título atualizado
  + descrição expandida com heurística.
- Skill `advpl-code-review`:
  - Frontmatter: `33 → 34` regras, `2 → 1` planned. Cita "12 cross-file
    (11 SX + MOD-003)" — explicita que MOD-003 não exige SX.
  - Tabela cross-file: entrada nova MOD-003 com nota "não requer ingest-sx".
  - Bloco "Info / Checklist mental": só PERF-006 sobra.
- `tests/unit/test_lint_catalog_consistency.py::test_all_check_functions_registered_in_orchestrator`
  ajustado pra suportar tanto formato tupla antigo `(id, fn),` quanto novo
  `(id, fn, requires_sx),`.
- 18 skills bumpadas `@0.3.25` → `@0.3.26`.

### Tests
- `tests/integration/test_ingest_sx.py::TestLintCrossFile::test_lint_cross_file_mod003_groups_static_functions_by_prefix`:
  fixture com 4 Static Functions `_AppCalc*` no mesmo arquivo (esperado:
  1 finding) + arquivo separado com só 2 fns mesmo prefixo (não atinge
  threshold, sem finding). Garantia de threshold=3 + supressão de
  prefixos curtos redundantes.
- 368 testes verde (era 367).

### Notes
- **Catalog status**: 34 active + 1 planned + 5 cross-file SX adicional
  já cobertos = 35 total. Sobra **apenas PERF-006** pra fechar o catálogo
  100%. PERF-006 é a mais complexa (cross-file SQL parser + cruzamento
  com índices SIX) — release dedicada (~4-6h) vai fechar v0.3.27.
- **Por que MOD-003 não usa SX**: opera sobre `fonte_chunks.tipo_simbolo
  = 'static_function'` que é populado pelo `ingest` regular. Decisão
  arquitetural: o grupo `cross-file` engloba qualquer regra que precise
  agregar dados ENTRE fontes, não só SX. PERF-006 também será cross-file
  sem SX (precisa de `indices` table do SX dictionary, mas pode skipar
  graciosamente quando ausente).
- **Threshold de 3 escolhido**: 2 funções mesmo prefixo é coincidência
  comum em ADVPL (helper privado + variante). 3+ indica padrão deliberado.
  Configurável no futuro via `--mod003-threshold N` se houver demanda.

## [0.3.25] - 2026-05-15

### BP-002b implementado — Private quando Local resolveria. Segunda das 4 lint planned originais (sobram MOD-003 + PERF-006). Detector com whitelist conservadora pra reduzir noise em código legacy ADVPL.

### Added
- **BP-002b (warning) — `Private <var>` em vez de `Local`**. Detector com
  whitelist pra padrões legítimos:
  - `MV_PAR01..MV_PAR99` — convenção `Pergunte()` (variáveis injetadas
    no escopo Private).
  - `lMsErroAuto`/`lMsHelpAuto` — convenção `MsExecAuto` (BP-003 cita).
  - 18 reservadas framework (`cFilAnt`, `cEmpAnt`, `dDataBase`, etc) —
    overlap com BP-008 aceito (categorias diferentes: best-practice vs
    critical, mensagens distintas).
  
  **Decisão de design:** foca em `Private` apenas. `Public` é coberto
  por MOD-002 — evitar duplo finding na mesma linha. BP-002b e MOD-002
  cobrem aspectos distintos do mesmo problema (escopo amplo desnecessário).
- Helpers em `lint.py`:
  - `_BP002B_PRIVATE_RE` — captura linha completa `Private ...` ate EOL,
    parser interno extrai nomes via split por `,` e remoção do `:= valor`.
  - `_BP002B_WHITELIST` — set com lMsErroAuto/lMsHelpAuto + 18 reservadas.
  - `_BP002B_MV_PAR_RE` — `^MV_PAR\\d{2}$` (case-insensitive).

### Changed
- Catálogo `lookups/lint_rules.json`: BP-002b `status="planned"` → `"active"`
  + `impl_function="_check_bp002b_private_when_local"` + título atualizado
  pra "Private quando Local resolveria" (antes mencionava também Public,
  agora desambiguado).
- Skill `advpl-code-review`:
  - Frontmatter: `32 → 33` regras, `21 → 22` single-file, `3 → 2` planned.
  - Tabela "Single-file": entrada nova BP-002b (warning, novo em v0.3.25)
    com whitelist citada.
  - Bloco "Info / Checklist mental": BP-002b sai (agora detectado);
    sobram só MOD-003 + PERF-006 (cross-file).
- 18 skills bumpadas `@0.3.24` → `@0.3.25`.

### Tests
- 9 testes em `TestBP002bPrivateWhenLocal` (3 positivos + 6 negativos):
  - `test_positive_private_simple_var`, `test_positive_private_multivar`,
    `test_positive_private_with_assign`.
  - `test_negative_private_mv_par`, `test_negative_private_msexecauto_state`,
    `test_negative_local_decl_not_flagged`, `test_negative_static_decl_not_flagged`,
    `test_negative_public_not_flagged_handled_by_mod002` (verifica que
    `Public` dispara MOD-002 mas NÃO BP-002b — separação clean),
    `test_negative_in_comment`.
- 367 testes verde (era 358).

### Notes
- **Catalog status**: 33 active + 2 planned + 5 cross-file SX = 40
  detectores efetivos. Fechamento total exige MOD-003 (cross-file
  semântica) + PERF-006 (cross-file SQL parser). Ambos são
  implementações maiores (~3-6h cada).
- **Whitelist "MV_PAR01..MV_PAR99"**: usa regex `^MV_PAR\\d{2}$`
  case-insensitive. Cobre o range típico TOTVS (Pergunte raramente
  passa de MV_PAR99). Se algum projeto usa MV_PAR100+, vão receber
  BP-002b — fix: trocar pra `Local`/`Static` ou adicionar à whitelist.
- **Whitelist com framework reservadas (18 nomes)**: redundante com
  BP-008 (que dispara `critical` no shadowing). Mantemos o overlap
  porque BP-008 é categoria `critical`/security e BP-002b é
  `warning`/best-practice — desligar uma das duas perde sinal.

## [0.3.24] - 2026-05-15

### BP-007 implementado — falta header Protheus.doc. Primeira das 4 lint planned restantes do catálogo (sobram BP-002b, MOD-003, PERF-006). User pediu "fechar lint antes de pivotar pra Universo 3".

### Added
- **BP-007 (info) — função sem header Protheus.doc**. Detector busca o
  opening `/*/{Protheus.doc}` (case-insensitive) nas **30 linhas anteriores**
  à declaração de cada `User Function`/`Static Function`/`Main Function`/
  `Method`. Match loose (presença do bloco já conta — não exigimos que o
  nome no header bata exatamente com o da função, equipes copiam-cola).
  Skipa MVC hooks (`kind="mvc_hook"` = anonymous, não são funções reais).
- Helpers em `lint.py`:
  - `_BP007_DOC_OPEN_RE` — regex pra `/*/{Protheus.doc}` flexível
    (espaços/case opcionais).
  - `_BP007_WINDOW_LINES = 30` — janela conservadora (header típico
    tem 10-20 linhas).

### Changed
- Catálogo `lookups/lint_rules.json`: BP-007 `status="planned"` → `"active"`
  + `impl_function="_check_bp007_no_protheus_doc"`. Descrição expandida
  com detalhes do detector (window, match loose, skip de mvc_hook).
- Skill `advpl-code-review`:
  - Frontmatter: `31 → 32` regras, `20 → 21` single-file, `4 → 3` planned.
  - Tabela "Single-file": entrada nova BP-007 (info, novo em v0.3.24).
  - Bloco "Info / Checklist mental": BP-007 sai (agora detectado);
    sobram só os 3 planned restantes (BP-002b, MOD-003, PERF-006).
- 18 skills bumpadas `@0.3.23` → `@0.3.24`.

### Tests
- 8 testes em `TestBP007NoProtheusDoc` (4 positivos + 4 negativos):
  - `test_positive_user_function_without_doc`
  - `test_positive_static_function_without_doc`
  - `test_positive_method_without_doc`
  - `test_positive_multiple_undocumented_functions`
  - `test_negative_protheus_doc_present` (header completo)
  - `test_negative_doc_is_minimal_but_present` (so opening + closing)
  - `test_negative_mvc_hook_skipped`
  - `test_negative_doc_for_each_of_multiple_functions`
- `test_clean_code_returns_empty` em `TestLintSourceIntegration`
  ajustado pra incluir Protheus.doc minimal — preserva contrato
  "clean code = zero findings" agora que BP-007 está ativa.
- 358 testes verde (era 350).

### Notes
- **Catalog status**: 32 active + 3 planned + 5 cross-file (3 + 2 das
  cross-file SX já cobrem) = 35 total. Falta apenas BP-002b/MOD-003/PERF-006
  pra fechar 100%. PERF-006 é a mais complexa (cross-file, requer parser
  SQL pra mapear coluna usada vs índice SIX).
- **Severidade `info`**: BP-007 não bloqueia nem alerta — é checklist
  pra cobertura de docs. Em projetos com >>milhões de findings legados,
  use `--severity warning` ou `--severity error` pra filtrar.
- **Match loose justificado**: docstring do detector explica decisão.
  Match estrito (com nome da função) gerava FPs em equipes que
  copiavam-colavam header de função similar e esqueciam de renomear.
  A presença do bloco já indica intenção de documentar — o nome errado
  é problema separado (eventual lint futuro).

## [0.3.23] - 2026-05-15

### Fragment versioning + V3 anonymization — fecha o **único** item ainda pendente do `gaps/PLUGADVPL_QA_REPORT_V3.md` (#1 do round 1, sobreviveu até round 3 porque exigia mecanismo de detecção de stale fragment). Com este release, **todos os 35 achados dos 3 rounds de QA estão endereçados**.

### Added
- **#1 — Fragment do CLAUDE.md tem marker de versionamento + warning em `status`**.
  Comportamento novo:
  - Toda execução de `init` injeta `<!-- plugadvpl-fragment-version: X.Y.Z -->`
    como primeira linha do bloco BEGIN/END plugadvpl, onde `X.Y.Z` é o
    `__version__` do binário no momento da injeção.
  - `status` lê CLAUDE.md, extrai o marker, compara com `runtime_version`.
    Quando difere (ou está ausente em fragments pré-v0.3.23), emite warning
    amarelo em stderr: `⚠ Fragment do CLAUDE.md foi gerado por plugadvpl X.Y.Z,
    binário atual é A.B.C. Rode 'plugadvpl init' para regenerar...`
  - `init` já era idempotente (sobrescreve a região BEGIN/END preservando
    o resto do CLAUDE.md) — só precisava do marker pra detecção funcionar.
- Helper novo `_check_fragment_staleness(root) → str | None` em `cli.py`.
  Retorna `None` se atualizado ou se CLAUDE.md sem fragment (caso fresh
  pre-init não polui status); mensagem descritiva caso contrário.
- Regex `_CLAUDE_FRAGMENT_VERSION_MARKER_RE` extrai o valor do marker.

### Changed
- `_CLAUDE_FRAGMENT_BODY` ganhou linha `<!-- plugadvpl-fragment-version: __VERSION__ -->`
  no topo. `_write_claude_md_fragment` substitui `__VERSION__` por
  `__version__` real na hora de gravar.
- `gaps/PLUGADVPL_QA_REPORT copy.md` (committed acidentalmente em v0.3.22)
  foi anonimizado (nome do cliente → `CLIENTE_X`/`cliente real`,
  paths locais → genéricos) e renomeado pra
  `gaps/PLUGADVPL_QA_REPORT_V3.md` — consistente com nomenclatura do
  V1 e V2.

### Tests
- 3 testes novos em `TestStatus`:
  - `test_status_warns_when_claude_md_fragment_is_stale` — fragment com
    marker `0.0.1-old` deve disparar warning citando esse valor + `init`.
  - `test_status_no_fragment_warning_when_marker_matches` — fragment fresh
    do `init` recente não polui stderr.
  - `test_status_warns_when_claude_md_has_no_fragment_marker` — fragment
    pré-v0.3.23 sem marker deve disparar warning genérico.
- 350 testes verde (era 347).

### Notes
- **Ciclo QA fechado**: 3 rounds de QA externo + 1 round automatizado (subagent),
  35 achados totais, **35 endereçados** ao longo de 10 releases (v0.3.14-v0.3.23).
  Backlog QA zerado. Próxima direção natural: pivot pra v0.4.0 Universo 3 ou
  fechar últimas 4 lint planned (BP-007/BP-002b/MOD-003/PERF-006).
- **Para usuários existentes**: o warning vai disparar na primeira `plugadvpl status`
  pós-upgrade (porque marker estará ausente). Solução em 1 linha:
  `plugadvpl init` regenera o fragment sobrescrevendo só a região BEGIN/END
  plugadvpl — qualquer conteúdo manual no CLAUDE.md é preservado.

## [0.3.22] - 2026-05-15

### Closeout pack — fecha 9 dos 11 itens baixos restantes do `gaps/PLUGADVPL_QA_REPORT_V2.md`. Backlog QA round 2 efetivamente zerado (sobram 2 polish maiores explicitamente deferidos). Categoria SEC mais completa, gatilho com BFS bidirecional, sx-status com schema estavel.

### Fixed
- **#3 — `_SEC004_PREPARE_ENV_RE` aceita continuacao multilinha `;`**.
  Antes `[^\\n]*?` parava no `\\n` real — `PREPARE ENVIRONMENT EMPRESA cEmp ;\\n
  USER 'admin' ;\\n PASSWORD 'totvs' ;\\n MODULO 'FAT'` escapava (caso comum em
  ADVPL). Agora `.*?` + `re.DOTALL` cobre multilinhas, `?` mantem nao-greedy.
- **#5 — `_SEC003_PII_FIELDS_RE` cobre A2_*/RH_***. Antes so A1_* (clientes)
  e RA_* (funcionarios). Adicionado A2_* (fornecedores: A2_CGC/A2_CPFRG/
  A2_NOME/A2_NREDUZ/A2_EMAIL/A2_TEL/A2_END/A2_DDD) e RH_* (folha-dependentes:
  RH_CPFDEP/RH_NOMEDEP/RH_RGDEP). Cobre cenarios de leak comuns em rotinas
  de compras (CFO, NFE) e folha (declaracao IRPF).
- **#6 — `gatilho` agora faz BFS bidirecional**. v0.3.15 expandiu OR
  campo_destino na query mas o frontier so seguia downstream. Cadeia inversa
  morria em level 1: `Z → Y → X` com query por `X` retornava so `Y → X`,
  ignorava `Z → Y` (upstream do upstream). Agora ambos `cd` e `co` viram
  frontier do proximo nivel; visited evita loops.
- **#8 — `_PARAMIXB_USAGE_RE` busca em stripped_strict** (sem strings/comentarios).
  Antes scaneava `content.splitlines()` raw — fonte com
  `cMsg := "Use PARAMIXB[1] na implementacao"` ou `// PARAMIXB[2]` em
  comentario classificava equivocadamente como PE. Probabilidade pratica
  baixa mas correctness ganhada sem custo.
- **#16 — `sx_status` schema sempre consistente**. Antes mudava de 2 keys
  (sx_ingerido + msg) pra 14 keys (com counts) — caller no `--format json`
  precisava branchear. Agora sempre o mesmo set de 15 keys; quando ainda
  nao foi rodado `ingest-sx`, counts=0 e `last_sx_ingest_at`/`sx_csv_dir`
  ficam `null`. `msg` continua presente quando aplicavel.

### Added
- **#18 — Hint pra flags subcomando-scoped misplaced**. Caso inverso do #2:
  `plugadvpl --workers 8 ingest` agora detecta que `--workers` eh flag de
  subcomando (nao global) e sugere posicionamento correto:
  ```
  Dica: '--workers' eh uma flag de SUBCOMANDO — vem DEPOIS do subcomando.
    Errado:  plugadvpl --workers ... ingest
    Correto: plugadvpl ingest --workers ...
  ```
  Set `_SUBCOMMAND_FLAGS` cobre 16 flags de subcomandos (ingest/status/lint/
  gatilho/impacto/tables). `_detect_misplaced_global_flag` virou
  `_detect_misplaced_flag` (alias retrocompat mantido) com retorno
  `(flag, subcmd, scope)`.
- **#19 — Test `test_callees_resolves_innermost_chunk_with_nested_methods`**.
  v0.3.15 docstring fala de "chunk MAIS INTERNO em caso de nesting (Class >
  Method > Static)" mas testes anteriores eram happy-path. Novo test usa
  Method + Static Function adjacentes pra validar isolamento mutuo dos
  callees. Test passa sem precisar mudar codigo (regression guard).

### Changed
- Skill `impacto`: nova secao "Precisao por tipo (v0.3.17+)" documenta que
  rows tipo `fonte` usam substring (intencional — codigo pode ter `"SA1->A1_COD"`
  como string), enquanto SX3/SX7/SX1 usam word boundary. Inclui dica pra
  rodar `grep -m identifier` quando suspeitar de FP.
- Skill `arch`: lista de campos do output ganhou `tabelas_via_execauto: bool`
  (v0.3.18+) explicando significado, e nota sobre WSRESTFUL methods agora
  nomeados como `<Class>.<VERB>` desde v0.3.21.
- Skill `callers`: secao "Saida" inclui `is_self_call: bool` com exemplo
  de filtragem via `jq`.

### Tests
- 8 testes novos:
  - `tests/unit/test_lint.py::TestSEC003PIIInLogs::test_positive_a2_fornecedor_field_in_log`
  - `tests/unit/test_lint.py::TestSEC003PIIInLogs::test_positive_rh_funcionario_field_in_log`
  - `tests/unit/test_lint.py::TestSEC004HardcodedCreds::test_positive_prepare_environment_multiline_continuation`
  - `tests/unit/test_parser.py::TestParseSource::test_pe_paramixb_in_string_or_comment_does_not_trigger`
  - `tests/integration/test_ingest_sx.py::TestGatilhoCommand::test_gatilho_bidirectional_traversal_depth2`
  - `tests/integration/test_ingest_sx.py::TestSxStatusCommand::test_sx_status_schema_consistent_before_and_after_ingest`
  - `tests/integration/test_cli.py::TestGlobalFlagPositioning::test_misplaced_subcommand_flag_shows_inverse_hint`
  - `tests/unit/test_query.py::TestCallees::test_callees_resolves_innermost_chunk_with_nested_methods`
- 347 testes verde (era 339).

### Deferred (continuam no backlog)
- **#17** — `fix_guidance` longo em terminal estreito. Fix proper exigiria
  schema change (`fix_guidance_short` + `fix_guidance_long`); usuarios podem
  contornar com `--format md` que nao trunca. Out-of-scope.
- **#20** — encoding misto nas skills (`execucao` vs `execução`). Mass edit
  cosmetico; legado de geracao via terminal Windows cp1252. Não bloqueia uso.

### Notes
- **Backlog QA round 2 reduzido de 11 → 2 deferidos**. Resto fechado em
  v0.3.21 + v0.3.22. Total: round 1 (15) + round 2 (20) = 35 achados,
  33 endereçados ao longo de 9 releases (v0.3.14-v0.3.22).
- Re-ingest recomendado pra usuarios existentes (`ingest --no-incremental`)
  pra ganhar SEC-003 expandido + #8 do PARAMIXB.

## [0.3.21] - 2026-05-14

### Bug pack — fecha 3 itens técnicos médios do `gaps/PLUGADVPL_QA_REPORT_V2.md` que sobraram após v0.3.20. Foco: corrigir false negatives em SEC-004 + numero correto no summary do `ingest-sx` + nomenclatura útil pros métodos REST do WSRESTFUL no call graph.

### Fixed
- **#15 — `ingest-sx` per_table mostra numero CORRETO (distinct, não inserted)**.
  Antes: `counters["per_table"][table] = inserted` (= len(rows) processadas
  do CSV). Agora: `= distinct` (= rows que sobreviveram após PK dedup). Caso
  real cliente: summary mostrava 58.796 consultas, sx-status mostrava 46.669
  — discrepância sumiu. WARN em stderr da v0.3.14 continua mostrando o
  numero CSV original (`{csv_rows} linhas CSV → {distinct} distintas`)
  pra rastreabilidade.
- **#4 — SEC-004 RpcSetEnv aceita variável nos slots emp/fil**. Antes o
  regex exigia string literal nos 4 slots (`RpcSetEnv("01","01","admin","totvs",...)`).
  O caso real mais comum é emp/fil virem de parâmetro/argv (`cEmp`, `cFil`)
  com user/pwd hardcoded — exatamente o leak crítico. Novo helper
  `_SEC004_ARG_RE = r"(?:\\w+|['\"][^'\"]*['\"])"` aceita variável OU literal
  nos slots 1+2; user/pwd continuam exigindo literal não-vazio.
- **#13/#14 — WSRESTFUL verb-only popula `funcoes` com nome qualificado**.
  Antes: `WSMETHOD GET WSSERVICE PortaldeViagem` virava `funcao={"nome":"GET"}` —
  nome ambíguo, colidia entre classes. Cascata: `find function GET` retornava
  todos GETs misturados; chunks indexados ficavam sem distinção; call graph
  dos métodos REST corrompia. Agora: novo cross-check com
  `_WSMETHOD_REST_BARE_RE` (já existia da v0.3.16) re-nomeia matches
  verb-only pra `<Classe>.<VERB>` (ex: `PortaldeViagem.GET`,
  `PortaldeViagem.POST`) + popula `classe`. Métodos com nome explícito
  (`WSMETHOD GET clientes WSSERVICE Vendas`) continuam intactos.

### Tests
- `tests/integration/test_ingest_sx.py::TestIngestSx::test_ingest_sx_per_table_reflects_db_count_not_csv_count` (#15 RED→GREEN).
- `tests/unit/test_lint.py::TestSEC004HardcodedCreds::test_positive_rpcsetenv_var_emp_fil_literal_user_pwd` (#4 RED→GREEN).
- `tests/unit/test_parser.py::TestParseSource::test_wsrestful_methods_appear_in_funcoes` (#13/#14 RED→GREEN).
- 339 testes verde (era 336).

### Notes
- **Backlog QA round 2 reduzido**: dos 15 itens menores que sobraram após
  v0.3.20, fechamos 4 (#4, #13, #14, #15). Continuam pendentes (todos baixos):
  #3 (SEC-004 PASSWORD com `;` continuação multiline), #5 (SEC-003 cobre só
  A1_*/RA_* — falta A2_*/RH_*), #6 (gatilho upstream traversal), #7 (impacto
  fontes sem boundary docs), #8 (PARAMIXB busca em raw), #11 (skills
  arch/callers não documentam novas flags), #16 (sx_status schema instável),
  #17 (fix_guidance longo), #18 (hint só globais), #19 (callees nesting test),
  #20 (encoding skills misto).
- **WSRESTFUL ricos**: `find function PortaldeViagem.GET` agora funciona,
  `callees PortaldeViagem.GET` retorna chamadas internas (resolvendo via
  v0.3.15 chunk parent), `callers PortaldeViagem.GET` mostra quem invoca
  (raro em REST puro — geralmente vazio, é endpoint exposto).
- **Re-ingest recomendado**: `plugadvpl ingest --no-incremental` aplica
  fix #15 (per_table correto) + fix #13/#14 (nomes WSRESTFUL ricos) em
  fontes ja indexados. SEC-004 #4 só dispara em ingest novo / re-ingest.

## [0.3.20] - 2026-05-14

### SEC-003 false positives + skill drift sync — fecha os 5 itens de maior prioridade do `gaps/PLUGADVPL_QA_REPORT_V2.md` (round 2 do QA externo). Trinca crítica: `Help` interpretado como log + regex de variável PII casando palavras PT-BR comuns + skills com contagens/recomendações desatualizadas.

### Fixed
- **#1 (alta) — `Help` removido de `_SEC003_LOG_FUNCS_RE`**. `Help()` em
  ADVPL é diálogo modal universal (validação de campo X3_VLDUSER, X7_REGRA),
  equivalente a `MsgInfo` que já era excluída. As próprias skills do plugin
  documentam Help como UI. Antes do fix, qualquer fonte MVC real com
  `Help( ,, 'Erro',, 'Cliente ' + cNome, 1, 0)` disparava SEC-003 — false
  positive massivo. +1 teste negativo `test_negative_help_is_ui_not_log`.
- **#2 (alta) — `_SEC003_PII_VAR_RE` não casa mais palavras PT-BR comuns**.
  As variantes curtas `Pass`/`Pin`/`Card`/`Pwd`/`Rg` casavam `cPassagem`
  (turismo), `cPintar` (manufatura), `cCardapio` (food-service), etc.
  Reescrita em duas alternations:
  - **Forma longa** (low FP): `Cpf|Cnpj|Senha|Password|Token|Cartao|Cvv|ApiKey|Api_Key|Secret`
    — match com prefixo Hungarian opcional + sufixo livre.
  - **Forma curta** (alta ambiguidade PT-BR): `cPwd|cRg|cPin|cCard|cPass`
    — exige prefixo `c` literal + boundary final (sem sufixo). Trade-off:
    `nPin` num projeto não dispara, mas preferimos miss a gritar massivamente.
  
  +3 testes negativos (`test_negative_var_passagem_not_password`,
  `test_negative_var_pintar_not_pin`, `test_negative_var_cardapio_not_card`)
  + 1 positivo de regressão (`test_positive_password_long_form_still_works`).

### Changed
- **#9 — Skill `advpl-code-review` sincronizada com v0.3.19**:
  - Frontmatter: `24 → 31` regras, `13 → 20` single-file.
  - Linha 7: `29 são detectadas → 31 são detectadas`.
  - Header tabela "Single-file (18) → (20)".
  - "lint roda as 13 → 20 regras single-file" (2 ocorrências).
  - Bloco "Info / Checklist mental (não detectadas automaticamente)" reescrito:
    estava listando 9 itens, mas 8 deles têm detector ativo (BP-006, BP-008,
    SEC-003, SEC-004, SEC-005, PERF-004, PERF-005, MOD-004). Reduzido para
    apenas os 4 genuinamente `planned` (BP-007, BP-002b, MOD-003, PERF-006)
    + nota explícita que os outros são automatizados pelo linter.
- **#10 — Skill `help` lista os 19 subcomandos** (antes listava 13).
  Reorganizada em "Universo 1 — fontes (14 cmds)" + "Universo 2 — Dicionário
  SX (5 cmds, v0.3.0+)". Cada subcomando ganha tag das features novas
  (`is_self_call` v0.3.18+, `tabelas_via_execauto` v0.3.18+, `--cross-file`,
  word boundary v0.3.17+, etc.).
- **#12 — Skill `status` recomenda `--no-incremental` pós-upgrade**, não
  `--incremental`. Estava conflitando diretamente com a "Pegadinha do
  --incremental" da skill `ingest`. Adicionada referência cruzada.
- 18 skills bumpadas `@0.3.19` → `@0.3.20`.

### Tests
- 5 testes novos em `TestSEC003PIIInLogs` (4 negativos + 1 positivo de
  regressão). Suite total: 336 verde (era 331).

### Notes
- **Backlog QA round 2**: ficaram 15 itens menores (severidade baixa-média)
  pra v0.3.21+. Top entre esses: #4 (RpcSetEnv com variável nos slots emp/fil),
  #6 (gatilho upstream traversal), #15 (ingest-sx per_table inflado),
  #13/#14 (WSRESTFUL verb-only não vira `funcoes`).
- **Para usuários existentes**: `plugadvpl ingest --no-incremental` recomendado
  pra reprocessar com SEC-003 ajustado. `lookup_bundle_hash` mudou (descrição
  do JSON inalterada mas regex do detector mudou — não dispara warning
  automático da v0.3.13). Re-ingest manual elimina FPs de `Help`/PT-BR words.

## [0.3.19] - 2026-05-14

### Security pack — fecha a categoria SEC. Implementa as 2 ultimas regras `planned` da categoria security: SEC-003 (PII em logs, LGPD) + SEC-004 (credenciais hardcoded). Pesquisa-first contra TDN + comunidade ADVPL (Terminal de Informação, BlackTDN, MasterAdvPL) confirmou padrões antes do detector — evita shipping de regra ruidosa.

### Added
- **SEC-004 (warning) — credenciais hardcoded em código fonte**. Detecta 4
  padrões canônicos de leak via git:
  - `RpcSetEnv("emp", "fil", "USER", "PWD", ...)` com user E pwd literais
    não-vazios (slots 3+4). Vazio = "usar admin default" por convenção,
    não é leak — não sinaliza.
  - `PREPARE ENVIRONMENT ... PASSWORD '<literal>'` (UDC `tbiconn.ch`).
  - `oMail:SMTPAuth("user","pwd")` ou `MailAuth("user","pwd")` literais.
  - `Encode64("user:pwd")` (Basic Auth construído inline).
  
  Não sinaliza leitura segura via `SuperGetMV`/`GetNewPar`/`GetMV` (padrão
  recomendado TOTVS). Comentários são limpos pelo `strip_advpl`.
  Sugestão de fix orienta MV_* em SX6 (e cita `MV_RELAUSR/MV_RELAPSW` para
  SMTP especificamente).
- **SEC-003 (warning) — PII / dados sensíveis em logs (LGPD)**. Detecta 4
  sinais em chamadas a `ConOut`/`FwLogMsg`/`MsgLog`/`LogMsg`/`UserException`/`Help`:
  - Variável com nome PII (`cCpf`, `cCnpj`, `cSenha`, `cPwd`, `cToken`,
    `cCard`, `cRg`, `cApiKey`, `cSecret`, ...).
  - Campo SX3 conhecido sensível: `A1_CGC`/`A1_CPF`/`A1_NOME`/`A1_NREDUZ`/
    `A1_EMAIL`/`A1_TEL`/`A1_END` (clientes), `RA_CIC`/`RA_RG`/`RA_NOMECMP`/
    `RA_EMAIL`/`RA_NUMCP` (funcionários).
  - CPF formatado literal (`999.999.999-99`).
  - CNPJ formatado literal (`99.999.999/9999-99`).
  
  **Não sinaliza** `MsgInfo`/`MsgAlert`/`MsgBox`/`Aviso` (UI modal, não vai
  pro log do servidor — exposição diferente, fora do escopo SEC-003). Detector
  usa 2 variantes do source: com strings (pra pegar literal CPF/CNPJ) e sem
  strings (pra pegar nome de variável sem confundir com label `"CPF inválido"`).
- Helpers em `lint.py`: `_SEC003_LOG_FUNCS_RE`, `_SEC003_PII_VAR_RE`,
  `_SEC003_PII_FIELDS_RE`, `_SEC003_CPF_LITERAL_RE`, `_SEC003_CNPJ_LITERAL_RE`,
  `_SEC004_RPCSETENV_LITERAL_RE`, `_SEC004_PREPARE_ENV_RE`,
  `_SEC004_SMTPAUTH_RE`, `_SEC004_BASIC_AUTH_RE`.

### Changed
- Catálogo `lookups/lint_rules.json`:
  - SEC-003: `status="planned"` → `"active"` + `impl_function="_check_sec003_pii_in_logs"`.
    Descrição expandida com lista completa dos 4 sinais detectados + regras
    de exclusão (não sinaliza UI).
  - SEC-004: `status="planned"` → `"active"` + `impl_function="_check_sec004_hardcoded_creds"`.
    Descrição expandida com 4 padrões canônicos detectados + casos
    explicitamente excluídos (SuperGetMV, vazio = admin default, comentários).
- Skill `advpl-code-review`:
  - Tabela "Single-file" ganhou linhas SEC-003 e SEC-004 com exemplos.
  - Lista "regras planned" reduzida de 6 → 4 (sobram BP-002b, BP-007,
    PERF-006, MOD-003).
- 18 skills bumpadas `@0.3.18` → `@0.3.19`.

### Tests
- `tests/unit/test_lint.py::TestSEC004HardcodedCreds`: 8 testes (5 positivos
  + 3 negativos cobrindo SuperGetMV, vazio, comentário).
- `tests/unit/test_lint.py::TestSEC003PIIInLogs`: 7 testes (4 positivos
  + 3 negativos cobrindo log seguro, MsgBox UI, label literal).
- `test_active_count_matches_impl` (catalog consistency) detectou o gap
  durante o release — exatamente o propósito do guard.
- 331 testes verde (era 316).

### Notes
- **Categoria SEC do catálogo agora 100% ativa**: SEC-001..SEC-005 todas
  com detector. Sobram 4 planned (BP-002b, BP-007, PERF-006, MOD-003) —
  todas info/warning de menor impacto.
- Pesquisa-first metodologia (mesmo padrão da v0.3.8 MOD-004): subagent
  consultou TDN oficial + 15 fontes da comunidade ADVPL antes do detector.
  Isso evitou shipping de regra over-aggressive (ex: marcar
  `Authorization: Bearer xxx` em todo header REST literal — ficou de fora
  por gerar muitos false positives em código de teste).
- **Para usuários existentes**: `plugadvpl ingest --no-incremental` recomendado
  pra reprocessar fontes ja indexados com as 2 regras novas (lookup_bundle_hash
  mudou — warning automático da v0.3.13 vai disparar no próximo `ingest --incremental`).

## [0.3.18] - 2026-05-14

### Polish pack — fecha os 3 ultimos achados do `gaps/PLUGADVPL_QA_REPORT.md`. Com este release o backlog do QA inicial chega a zero — sobram apenas os achados ja resolvidos em v0.3.14-v0.3.17.

### Fixed
- **#9 — `lint` retornava findings duplicados**. BP-001 (RecLock sem
  MsUnlock) reportava o mesmo RecLock 2x quando vinha em forma alias
  (`<alias>->(RecLock(...))`) — casava com AMBOS regexes (`_RECLOCK_OPEN_RE`
  pra literal + `_RECLOCK_VIA_ALIAS_RE` pra alias). Fix: dedup por **linha**
  no detector antes de contar opens (`opens_by_line` dict). Mesma linha
  agora conta como 1 open mesmo casando 2 regexes.

### Added
- **#11 — `arch` expoe `tabelas_via_execauto: bool`**: quando o fonte tem
  capability `EXEC_AUTO_CALLER`, a flag fica True sinalizando que as
  listas `tabelas_read/write/reclock` podem estar incompletas (analise
  estatica nao expande a rotina chamada via MsExecAuto). Caller deve
  rodar `tables` na rotina alvo pra cobertura completa.
- **#12 — `callers` expoe `is_self_call: bool`** em cada row. Self-call
  quando `funcao_origem == nome` OU `basename(arquivo_origem) == nome`.
  Util pra filtrar self-references (FwLoadModel('X') de dentro de X.prw
  contava como caller externo no output).

### Tests
- `tests/integration/test_cli.py::TestLint`: +4 testes
  (`test_lint_findings_no_duplicates_alias_reclock` com fixture
  `reclock_alias_dup_trigger.prw`; `test_arch_flags_tabelas_via_execauto`;
  `test_arch_no_execauto_flag_when_no_capability`;
  `test_callers_flags_is_self_call`).
- 316 testes verde (era 312).

### Notes
- **QA report inicial agora 100% endereçado**:
  - Resolvidos em v0.3.14: #14 (SXG mislabel), #15 (consultas Δ).
  - Resolvidos em v0.3.15: #1 (CLAUDE.md fragment), #2 (--limit hint),
    #4 (gatilho destino), #8 (callees broken), #13 (project_root).
  - Resolvidos em v0.3.16: #5/#7 (WSRESTFUL), #6/#10 (PE canonico).
  - Resolvidos em v0.3.17: #3 (impacto boundary).
  - Resolvidos em v0.3.18: #9 (lint dups), #11 (execauto flag), #12
    (self-call flag).
- Próximo grande tema natural: v0.4.0 Universo 3 (Rastreabilidade) — ou
  promover mais regras planned restantes (SEC-004 hardcoded creds,
  SEC-003 PII em logs, BP-007 Protheus.doc, etc.).

## [0.3.17] - 2026-05-14

### Impacto preciso — fix #3 do `gaps/PLUGADVPL_QA_REPORT.md`. `plugadvpl impacto A1_COD` retornava >100KB de output em campo curto/comum, com gatilhos de campos cujo nome apenas CONTEM 'A1_COD' como substring (`BA1_CODEMP`, `BA1_CODINT`, `DA1_CODPRO`, `A1_CODSEG`, etc.). Para campos de tabelas standard (SA1, SB1, SC5...) o comando ficava praticamente inutilizavel — caso real reportado: `A1_COD` retornava ~150 resultados, ~95% falsos positivos.

### Fixed
- **#3 — `impacto` agora usa word boundary (`\\b<termo>\\b`)**. SQL continua
  fazendo prefiltro com `LIKE '%X%'` (cheap, narrows candidates) e Python
  re-valida cada match com regex `\\b<TERMO>\\b` antes de devolver. Falsos
  positivos sao silenciosamente descartados.
  - **ADVPL-aware**: `\\b` no Python NAO trata `_` como boundary (`_` eh
    `\\w`), entao `\\bA1_COD\\b` NAO casa em `BA1_COD` (B+A1 = continuacao
    `\\w`) nem em `A1_CODFAT` (CO+DF = continuacao `\\w`). Comportamento
    exato pra nomes de campo Protheus tipo `A1_COD`.
  - Aplicado em 3 lugares de `query.py`:
    - `_impacto_sx3` — campos com VALID/VLDUSER/WHEN/INIT referenciando o termo.
    - `_impacto_sx7_chain` — gatilhos com REGRA/CONDICAO referenciando o termo.
    - `_impacto_sx1` — perguntas com VALIDACAO/CONTEUDO_PADRAO referenciando.
  - Match exato em `campo_origem` SX7 (origem literal) continua aceito sempre.
- Helper novo `_word_boundary_re(termo)` em `query.py` — centraliza a logica
  pra uso futuro (qualquer query que precise de match exato em texto).

### Tests
- `tests/integration/test_ingest_sx.py::TestImpactoCommand::test_impacto_uses_word_boundary_no_substring_false_positives`
  (RED→GREEN). Fixture com 3 gatilhos: 1 real (`A1_COD->A1_NREDUZ`) +
  2 substring-fakes (`BA1_CODEMP`, `A1_CODFAT`). Antes do fix: os 3
  apareciam. Depois: so o real.
- 312 testes verde (era 311).

### Notes
- **Impacto em fontes (`fonte_chunks.content`) NAO foi alterado** — busca
  em codigo eh diferente: voce TAMBEM quer pegar `A1_COD` quando aparece
  como parte de uma string maior tipo `"SA1->A1_COD"`. Limitar a busca em
  conteudo de fonte com boundary derrubaria matches legitimos. So eh
  problema em campos textuais SX (regra/validacao/init), onde o termo eh
  um nome de campo e o boundary preserva a semantica esperada.
- **Backlog do QA report ainda restando**:
  - #9 `lint` retorna findings duplicados (UNIQUE constraint).
  - #11 flag `tabelas_via_execauto` quando `EXEC_AUTO_CALLER` set.
  - #12 flag `is_self_call` em `callers`.

## [0.3.16] - 2026-05-14

### Parser heuristics — fixes #5/#7 + #6/#10 do `gaps/PLUGADVPL_QA_REPORT.md`. WSRESTFUL classico nao virava webservice; PE canonico TOTVS (ANCTB102GR) nao era detectado. Ambos sao misclassificacoes silenciosas — usuario/IA que filtrasse "todos os webservices" ou "todos os PEs" perdia esses casos.

### Fixed
- **#5/#7 — WSRESTFUL classico classificado como webservice**: o parser
  capturava `WSSERVICE <Name>` mas nao `WSRESTFUL <Name>`. Classes
  REST puras (com `WSMETHOD GET WSSERVICE <Class>` em vez de
  `WSMETHOD GET <name> WSSERVICE <Class>`) caiam pra
  `source_type=user_function` e capability `WS-REST` ficava ausente.
  Agora:
  - Novo regex `_WSRESTFUL_HEADER_RE` captura `WSRESTFUL <Name>` e
    popula `ws_structures.ws_restfuls` (lista paralela a `ws_services`).
  - Novo regex `_WSMETHOD_REST_BARE_RE` captura `WSMETHOD <verb>
    WSSERVICE <Class>` (verb-only, padrao tipico de impl WSRESTFUL)
    e adiciona como `rest_endpoint` com `annotation_style='wsmethod_restful'`.
  - `_derive_capabilities` adiciona `WS-REST` quando `ws_restfuls` ou
    style `wsmethod_restful` aparece.
  - `_derive_source_type` agora considera `ws_restfuls` na decisao
    "eh webservice?".

- **#6/#10 — PE canonico TOTVS detectado via PARAMIXB**: o regex
  `_PE_NAME_RE` (`^[A-Z]{2,4}\\d{2,4}[A-Z_]{2,}$`) catura `MT100GRV`
  / `MA440PGN` mas nao `ANCTB102GR` (estrutura letras-letras-digitos-
  letras). Heuristica nova: User Function cujo corpo usa `PARAMIXB[N]`
  eh PE — independente do nome. PE Protheus recebe parametros via
  `PARAMIXB` (array global), entao falso-positivo eh minimo.
  - Novo helper `_derive_pontos_entrada(funcoes, content_lines)` em
    `parser.py` combina os 2 sinais (regex de nome + body scan).
  - `parse_source` agora popula `result["pontos_entrada"]` direto
    (antes vivia so em `ingest.py`).
  - `ingest.py` consome `parsed["pontos_entrada"]` em vez de recomputar.
  - `_derive_capabilities` usa `pontos_entrada` pra decidir capability
    `PE`; mantem fallback regex pra back-compat de callers que passem
    parsed dict sem `pontos_entrada` populado.

### Tests
- `tests/unit/test_parser.py::TestParseSource::test_wsrestful_classic_classified_as_webservice` (#5/#7 RED→GREEN).
- `tests/unit/test_parser.py::TestParseSource::test_pe_canonical_paramixb_detected` (#6/#10 RED→GREEN).
- Fixtures novos: `cli/tests/fixtures/synthetic/ws_restful_classic.prw` (WSRESTFUL com 2 endpoints) + `pe_paramixb.prw` (ANCTB102GR canonico usando PARAMIXB[1..5]).
- 311 testes verde (era 309).

### Notes
- **Nao incluido neste release** (ainda no backlog do QA report):
  - #3 `impacto` substring sem boundary.
  - #9 `lint` retorna findings duplicados.
  - #11 flag `tabelas_via_execauto`.
  - #12 flag `is_self_call` em callers.
- Usuarios existentes precisam re-rodar `plugadvpl ingest --no-incremental`
  para que `pontos_entrada` e `capabilities`/`source_type` sejam recalculados
  nos arquivos ja indexados (lookup_bundle_hash nao mudou — mudanca eh so
  no codigo, entao warning automatico da v0.3.13 nao dispara).

## [0.3.15] - 2026-05-14

### Correctness pack — 5 fixes derivados do `gaps/PLUGADVPL_QA_REPORT.md` (relatorio QA exploratorio rodado num projeto real de cliente com 1.992 fontes + dicionario SX completo, 421k registros). Foco nos achados de severidade alta/critica que **bugs reais** com fix surgical (parser heuristicas e melhorias de UX maiores ficam pra v0.3.16+).

### Fixed
- **#8 (CRITICO) — `callees` totalmente quebrado**: `chamadas_funcao.funcao_origem`
  estava sendo gravado como `""` em TODOS os 30k+ registros (`# best-effort vazio
  no MVP` esquecido). Resultado: `plugadvpl callees <funcao>` retornava vazio
  pra qualquer nome de funcao. Agora resolvemos via lookup nos chunks
  (linha_origem está dentro de quais [linha_inicio, linha_fim]?), escolhendo o
  chunk MAIS INTERNO em caso de nesting (Class > Method > Static).
- **#4 — `gatilho` ignorava destinos**: query era `WHERE upper(campo_origem) = ?`
  mas o help diz "originados/destinados". Campos que apenas RECEBEM gatilhos
  (chaves geradas) ficavam invisiveis. Agora `WHERE upper(campo_origem) = ?
  OR upper(campo_destino) = ?`.
- **#13 — `ingest-sx` sobrescrevia `project_root`**: chamava
  `init_meta(project_root=str(csv_dir))` que upsertava o slot do `project_root`
  com o `csv_dir`. Sintoma observado: status mostrava `project_root=D:\...\CSV`
  em vez da raiz do projeto. Agora so chama `init_meta` se `project_root`
  ainda nao existir (caso usuario rode `ingest-sx` antes de `init`); caso
  contrario so atualiza `cli_version`. `sx_csv_dir` continua indo pro slot
  proprio.

### Added
- **#2 — Hint amigavel para flag global misplaced**: `plugadvpl status --limit 20`
  retornava `No such option: --limit` sem indicar que `--limit` eh global e
  precisa vir antes do subcomando. Agora `main()` detecta o caso heuristicamente
  (token em `_GLOBAL_FLAGS` apos o subcomando) e imprime apos o erro do click:
  ```
  Dica: '--limit' eh uma flag GLOBAL — vem ANTES do subcomando.
    Errado:  plugadvpl status --limit ...
    Correto: plugadvpl --limit ... status
  ```
- Set `_GLOBAL_FLAGS` em cli.py com as 12 flags do callback.

### Changed
- **#1 — Fragment `CLAUDE.md` desatualizado**: tabela de decisao listava modos
  do `grep` como `--fts`/`--literal`/`--identifier` (flags inexistentes — o
  correto eh `-m fts|literal|identifier`). Atualizado. Projetos novos veem
  versao certa via `plugadvpl init`; projetos existentes podem regenerar
  manualmente ou aguardar proximo init.

### Tests
- `tests/unit/test_query.py::TestCallees::test_callees_by_function_name_works` (#8 RED→GREEN).
- `tests/integration/test_ingest_sx.py::TestGatilhoCommand::test_gatilho_includes_destination_matches` (#4 RED→GREEN).
- `tests/integration/test_ingest_sx.py::TestIngestSx::test_ingest_sx_preserves_project_root` (#13 RED→GREEN).
- `tests/integration/test_cli.py::TestGlobalFlagPositioning::test_misplaced_global_flag_shows_helpful_hint` (#2 RED→GREEN).
- 309 testes verde (era 305).

### Notes
- **Nao incluido neste release** (planejado v0.3.16+):
  - #3 `impacto` substring sem boundary (false positives massivos com `A1_COD`).
  - #5/#7 WSRESTFUL nao classifica como `source_type=webservice`.
  - #6/#10 PE canonico (ANCTB102GR) nao detectado.
  - #9 `lint` retorna findings duplicados.
  - #11 flag `tabelas_via_execauto` quando `EXEC_AUTO_CALLER`.
  - #12 flag `is_self_call` em callers.
- **Dados existentes**: usuarios precisam re-rodar `plugadvpl ingest --no-incremental`
  para que `funcao_origem` seja populado nos registros existentes (warning
  da v0.3.13 ja avisa quando lookups mudam — neste caso lookups nao mudaram,
  so o codigo, entao precisa reingest manual).

## [0.3.14] - 2026-05-14

### SXB consultas — PK fix + dedup transparency. Quarta rodada do mesmo feedback de IA externa: dump real do cliente com 58.796 linhas em `sxb.csv` virava 46.669 no DB (perda de 20,6%) silenciosamente. Pesquisa contra TDN oficial confirmou: SXB tem 6 tipos (XB_TIPO 1-6: header/indice/permissao/coluna/retorno/filtro) e a PK natural inclui XB_TIPO.

### Fixed
- **SXB consultas: PK agora inclui `tipo`** (`migrations/004_consultas_pk_with_tipo.sql`).
  Antes: PK `(alias, sequencia, coluna)` fazia colidir as 6 paginas da consulta padrao
  (uma consulta full virava 1-2 rows). Agora: PK `(alias, tipo, sequencia, coluna)`
  espelha a chave natural TOTVS (TDN: `XB_FILIAL+XB_ALIAS+XB_TIPO+XB_SEQ+XB_COLUNA`;
  XB_FILIAL eh sempre vazio porque SXB eh X2_MODO='C').
  `SCHEMA_VERSION` bumpado `3 → 4`.

### Added
- **Aviso de SXG mal-rotulado** (`parse_sxg`): quando `sxg.csv` tem header `X3_*`
  (eh um dump SX3 disfarcado, comum em alguns exports do Configurador), o parser
  agora emite aviso amarelo em stderr explicando o problema em vez de pular silencioso.
  Mensagem orienta solicitar o SXG correto ao DBA.
- **Transparencia de dedup** (`ingest_sx`): para cada tabela, conta PKs distintas
  ANTES de `INSERT OR REPLACE` e compara com linhas processadas. Quando diff > 0,
  imprime aviso amarelo `WARN: tabela 'X': N linhas CSV -> M distintas apos PK dedup
  (D duplicada(s) na PK (...) foram sobrescrita(s))`. Util pra distinguir bug
  do parser (PK incompleta) de duplicatas reais no dump.
- **`_PK_COLS_BY_TABLE`** em `ingest_sx.py` — mapa tabela -> tupla de colunas PK
  (espelha as migrations 001 + 002 + 004). Usado pelo dedup detector.

### Changed
- Skill `ingest-sx`: nova secao "Avisos em stderr (v0.3.14)" documentando os 2
  diagnosticos novos + nota historica sobre o bug do SXB com cenario real
  (58k -> 46k) e link com TDN.
- 18 skills bumpadas `@0.3.13` -> `@0.3.14`.

### Tests
- `tests/integration/test_ingest_sx.py::TestIngestSx`: +4 testes
  (`test_sxb_consultas_preserves_all_tipos` — RED test do bug; `test_sxg_mislabel_emits_warning`;
  `test_ingest_sx_warns_when_dedup_lost_rows`; `test_ingest_sx_no_dedup_warning_when_clean`).
- Fixture `sxb_with_collisions.csv` — 6 linhas USRGRP, 1 por XB_TIPO, todas com
  mesmo (seq, coluna). Antes do fix: 2 rows sobreviviam. Depois: 6 (uma por tipo).
- 305 testes verde (era 301).

### Migration notes
- `apply_migrations` aplica `004_*.sql` automaticamente no primeiro `init`/`ingest`/`ingest-sx`
  apos upgrade. Dados existentes em `consultas` sao preservados via `INSERT SELECT`
  pra `consultas_new` antes do swap.
- **Usuarios existentes precisam re-rodar `ingest-sx`** para popular os ~20% de
  rows que estavam sendo silenciosamente sobrescritos antes. Trigger automatico:
  v0.3.13 ja avisa quando `lookup_bundle_hash` muda (`ingest --incremental` warning),
  e o `status` ainda mostra divergencia `runtime_version != plugadvpl_version`.

### Notes
- Foi a 4a iteracao do mesmo loop "IA externa testa, reporta sintoma, fix":
  v0.3.11 (truncamento + --json), v0.3.12 (runtime vs index version),
  v0.3.13 (--incremental sem reaplicar regras), v0.3.14 (SXB PK + dedup transparency).
- Pesquisa contra fontes oficiais (TDN paginas 22479685-22479707) confirmou a
  semantica dos 6 tipos antes do schema change — evitou shipping de fix incorreto.
- SX9/SXA/SX1 tambem tem dedup minor (321/85/13 rows) no dump do cliente, mas
  analise mostrou que sao duplicatas reais no SX (nao bug de PK). Sem migration
  pra eles; a transparencia nova ja loga quando aparecerem.

## [0.3.13] - 2026-05-14

### `--incremental` post-upgrade gotcha — terceiro round do mesmo feedback de IA externa. Apos `uv tool upgrade plugadvpl` + `ingest --incremental`, os arquivos pulados (mtime nao mudou) NAO eram re-avaliados contra regras de lint novas, mesmo apos o usuario seguir corretamente o fluxo recomendado pela v0.3.12. Resultado: `total_lint_findings` ficava frozen na versao antiga pra 99% do projeto sem aviso.

### Added
- **Warning de divergencia de lookups no `ingest --incremental`** — antes de
  `seed_lookups()` sobrescrever `meta.lookup_bundle_hash`, capturamos o valor
  anterior. Apos o ingest, se (1) modo `--incremental`, (2) `lookup_bundle_hash`
  mudou, e (3) houve `arquivos_skipped > 0`, imprime aviso amarelo em **stderr**:
  ```
  ⚠ Lookups (lint_rules/funcoes_restritas/...) mudaram desde o ultimo ingest.
    --incremental pulou N arquivo(s) cujo mtime nao mudou — esses NAO foram
    re-avaliados contra as regras novas.
    Para cobrir todo o codebase com as regras atualizadas, rode:
        plugadvpl ingest --no-incremental
  ```
  Suprimivel com `--quiet`.

### Changed
- `plugadvpl.ingest.ingest()` retorna 2 chaves novas no dict de counters:
  - `lookup_hash_changed: bool` — True se o hash do bundle de lookups mudou
    entre o ingest anterior e o atual.
  - `previous_lookup_hash: str | None` — hash gravado antes deste ingest
    (None se primeiro ingest no DB).
  Tipo do retorno mudou de `dict[str, int]` para `dict[str, Any]` (back-compat:
  todas as chaves originais continuam tendo valores int/str).
- Skill `ingest`: nova secao "Pegadinha do --incremental apos upgrade do
  binario" com cenario tipico (5 passos) + exemplo do warning. Renomeada
  `--no-incremental` na lista de opcoes pra `--incremental`/`--no-incremental`
  (mostra os dois lados do toggle).
- Skill `plugadvpl-index-usage`: secao "Versao do plugin" ganhou subsecao
  "Pegadinha do --incremental apos upgrade" com fluxo correto pos-upgrade
  (status → ingest --no-incremental → status novamente).
- 18 skills bumpadas `@0.3.12` → `@0.3.13`.

### Tests
- `tests/integration/test_cli.py::TestIngest`: +4 testes
  (`test_ingest_incremental_warns_when_lookups_changed`,
  `test_ingest_no_incremental_no_warning_even_with_hash_change`,
  `test_ingest_incremental_no_warning_when_hash_unchanged`,
  `test_ingest_warning_suppressed_by_quiet`). Cobrem matriz completa
  hash×modo×skipped + supressao por `--quiet`.
- 301 testes verde (era 297).

### Notes
- Decisao de design: NAO implementar auto-relint (re-aplicar lint sem
  re-parsear) nesta versao — seria mais ergonomico mas adiciona
  complexidade (nova flag, novo caminho, separar parser cache de lint
  cache). Avisar é suficiente; usuario decide se vale o tempo de
  `--no-incremental`. Re-avaliar se feedback de uso indicar que a dor
  recorrente justifica.
- O sinal usado (`lookup_bundle_hash`) ja existia desde antes —
  `seed_lookups` ja calculava SHA-256 do bundle. So precisava ser lido
  ANTES de `seed_lookups` sobrescrever pra detectar mudanca. Custo
  marginal: 1 query SQL extra por ingest.

## [0.3.12] - 2026-05-14

### Version-confusion fix — IA externa (mesmo feedback da v0.3.11) tinha rodado `uv tool upgrade` e ficou perdida porque `plugadvpl status` continuava mostrando a versão antiga (frozen no índice). Padrão git/hatch/dvc: mostrar **runtime + stored** lado a lado e avisar quando divergem.

### Added
- **`plugadvpl --version` / `-V`** (eager flag global no callback) — imprime
  versão do binário e sai. Padrão UNIX consagrado; antes só existia o
  subcomando `plugadvpl version`. Agora ambos funcionam.
- **`status` expõe `runtime_version`** — nova chave no output do query
  `plugadvpl.query.status()`, populada com `plugadvpl.__version__` do
  binário rodando AGORA. Convive com `plugadvpl_version` (frozen no
  init/ingest) e `cli_version` (frozen no último ingest).
- **Aviso de divergência** — quando `runtime_version != plugadvpl_version`,
  o `status` imprime em **stderr** (amarelo): `⚠ Índice criado com
  plugadvpl X.Y.Z, binário atual é A.B.C. Rode 'plugadvpl ingest
  --incremental' para atualizar o índice com regras/parsers da versão
  nova.` Suprimível com `--quiet`.

### Changed
- `plugadvpl.query.status(conn, project_root, runtime_version=None)` —
  novo parâmetro keyword opcional `runtime_version` (back-compat: chave
  vira `None` quando não passado, comportamento preservado).
- Skill `status`: tabela de campos do output, seção "Para descobrir qual
  versão está instalada" com 4 caminhos (`--version`, `version`, `status`,
  `uv tool list`) e o que cada um responde.
- Skill `help`: documenta `--version`/`-V` no topo das flags globais +
  seção "Qual versão está instalada?" com 3 caminhos.
- Skill `plugadvpl-index-usage`: nova seção "Versão do plugin — runtime
  vs índice" explicando o cenário do `uv tool upgrade` sem reingest.
- 18 skills bumpadas `@0.3.10`/`@0.3.11` → `@0.3.12`.

### Tests
- `tests/unit/test_query.py::TestStatus`: +2 testes
  (`test_status_runtime_version_field_when_passed`,
  `test_status_runtime_version_diverges_from_stored`).
- `tests/integration/test_cli.py::TestVersion`: +2 testes
  (`test_version_global_flag_long`, `test_version_global_flag_short`).
- `tests/integration/test_cli.py::TestStatus`: +4 testes
  (`test_status_includes_runtime_version`,
  `test_status_warns_when_binary_diverges_from_index`,
  `test_status_no_warning_when_versions_match`,
  `test_status_warning_suppressed_by_quiet`).
- 297 tests verde (eram 252+45 = 297; 8 novos compensam o que estava
  faltando vs o agregado anterior).

### Notes
- Decisão deliberada: NÃO reescrever `meta.plugadvpl_version` no
  `status` — manter como "versão que tocou o DB pela última vez" (resposta
  semântica da pergunta "esse índice é compatível?"). O `runtime_version`
  é a resposta complementar.
- Comportamento back-compat: caller que chame `status(conn, root)` sem
  passar `runtime_version` continua recebendo `runtime_version: None` na
  saída — testado em `test_status_runtime_version_field_when_passed`.

## [0.3.11] - 2026-05-14

### UX/docs release — feedback de outra IA usando o plugin revelou 2 fricções de discoverability + 1 maintenance gap. Sem mudança de código de produção.

### Fixed
- **18 skills com `uvx plugadvpl@0.3.1` hardcoded** — bumped pra `@0.3.10`
  em todas (`arch`, `find`, `lint`, `tables`, `callees`, `callers`,
  `doctor`, `gatilho`, `grep`, `help`, `impacto`, `ingest`, `ingest-sx`,
  `init`, `param`, `reindex`, `status`, `sx-status`). Estavam congeladas
  desde a v0.3.1 — usuários do plugin marketplace puxavam o catálogo
  sem regras BP-008/PERF-005/MOD-004/PERF-004/SEC-005.

### Added
- **Skill `plugadvpl-index-usage`**: nova seção "Output format —
  IMPORTANTE para agentes IA" documentando explicitamente as 3 opções
  (`table`/`md`/`json`), com tabela mostrando truncamento + lista de
  anti-padrões observados em sessões reais (tentar `--json` standalone,
  setar `$env:COLUMNS=400`, misturar shell PS/Bash). Recomenda
  `--format md` para Claude/agentes.
- **Skills com tabelas largas** (`arch`, `find`, `lint`, `tables`,
  `callees`, `callers`): callout no topo "Para agente IA: prefira
  `--format md`" — comando exemplo já vem com a flag para induzir cópia
  correta.
- **Skill `help`**: documentação completa das 8 flags globais com
  posicionamento (callback vem ANTES do subcomando) + aviso explícito
  "flags `--json`/`--vertical`/`--wide`/`--no-table` não existem; use
  `--format json` ou `--format md`".
- **CLAUDE.md fragment** (injetado por `/plugadvpl:init`): nova seção
  "Output format — IMPORTANTE para agentes IA" com mesma orientação
  + 3 anti-padrões. Projetos novos terão a guidance baked in.

### Notes
- Não há mudança no comportamento do CLI — todas as flags já existiam
  (`--format`, `--quiet`, `--compact`, `--no-next-steps`). Era só
  discoverability.
- Trigger: usuário compartilhou feedback de outra IA que rodou o plugin
  e identificou 3 fricções (truncamento Rich em terminal estreito,
  tentou `--json` em vez de `--format json`, misturou syntax PS/Bash em
  workaround). Análise: 1 era UX real (truncamento), 2 eram falta de
  documentação no contrato CLI.
- Não foram adicionadas novas flags (`--vertical`, `--wide`,
  `--no-truncate`) — `--format md` já resolve sem truncamento e é mais
  legível para LLM. Mantém superfície da API enxuta.

## [0.3.10] - 2026-05-13

### Audit release — sem regras novas; 4 gaps de qualidade identificados na revisão item-a-item de v0.3.4–v0.3.9 (com pesquisa em TDN/casos reais), todos corrigidos.

### Added
- **Test guard novo `test_all_check_functions_registered_in_orchestrator`**
  (8º teste em `test_lint_catalog_consistency.py`) — verifica que toda
  função `_check_*` extraída dos docstrings de `parsing/lint.py` aparece
  registrada em `lint_source()` (single-file via
  `findings.extend(_check_xxx(...))`) ou em `_CROSS_FILE_RULES` (cross-file
  SX-*). Fecha gap "F6" da auditoria: catalog dizia `active`, função
  existia no módulo, mas se ninguém chamasse no orchestrator a regra nunca
  disparava em runtime e nenhum teste pegava.
- **BP-008**: 7 reservadas adicionais cobertas (de 13 → **20**):
  - `dDataBase` (CRÍTICO — shadow quebra toda lógica de competência/data
    de movimento; achado mais grave da auditoria)
  - `INCLUI`, `ALTERA` (modo de operação em pontos de entrada/gatilhos)
  - `cFunBkp`, `cFunName` (introspecção de função corrente)
  - `lAutoErrNoFile` (controle de erro em rotinas auto)
  - `__Language` (idioma da sessão)

  +4 testes positivos novos (`test_positive_dDataBase_shadow`,
  `test_positive_INCLUI_ALTERA_shadow`, `test_positive_cFunName_cFunBkp_shadow`,
  `test_positive_lAutoErrNoFile_shadow`).
- **PERF-005**: detecta agora `LastRec()` além de `RecCount()`.
  TDN documenta `LastRec` como funcionalmente idêntico a `RecCount`
  (mesmo full-scan O(n)) — gap real da v0.3.6, qualquer codebase legacy
  que usa `LastRec() > 0` (padrão CA-Clipper/xBase histórico) escapava
  do detector. +3 testes (`test_positive_lastrec_for_existence`,
  `test_positive_lastrec_alias_call`, `test_negative_lastrec_business_limit`).
- **MOD-004**: detecta agora `MsNewGetDados` além de
  `AxCadastro`/`Modelo2`/`Modelo3`. TDN marca `MsNewGetDados` como
  **deprecated desde 12.1.17** — grid editável standalone substituído por
  `AddGrid` em ViewDef (MVC) ou `FWFormBrowse + AddGrid`. +2 testes
  (`test_positive_msnewgetdados_call`, `test_positive_msnewgetdados_assign`).

### Changed
- Catálogo `lookups/lint_rules.json`:
  - `BP-008.descricao`: lista expandida das 20 reservadas, com `dDataBase`
    explicitamente marcada como CRÍTICO.
  - `PERF-005.titulo` + `descricao`: cita `LastRec()` como alias de
    `RecCount()`.
  - `MOD-004.titulo` + `descricao`: cita `MsNewGetDados` como deprecated
    desde 12.1.17.
- Skill `advpl-code-review`:
  - Tabela "Single-file": entradas de BP-008/PERF-005/MOD-004 mencionam
    expansão em v0.3.10.
  - Sub-seção BP-008: lista das 20 reservadas agrupada por categoria
    (sessão/data/PE-state/backup) + nota sobre por que `dDataBase` é o
    shadow mais perigoso.
  - Sub-seção PERF-005: exemplo errado adicional com `LastRec() > 0`.
  - Sub-seção MOD-004: exemplo legacy adicional com `MsNewGetDados`.

### Tests
- 101 testes (era 93): 93 lint + 8 catalog consistency. Verde, zero
  regressão. `test_active_count_matches_impl` continua dinâmico — nunca
  precisa atualizar quando promove planned→active no futuro.

### Notes
- Catálogo continua em **24 active + 6 planned + 5 cross-file = 35**
  (auditoria não promoveu novas regras, só expandiu cobertura interna
  das 3 modificadas).
- Auditoria seguiu metodologia: pesquisa web (TDN, github
  nginformatica, Code Analysis docs) → identificação de gap real →
  TDD (red test) → fix → green test → catalog/skill updates.

## [0.3.9] - 2026-05-13

### Added
- **`PERF-004` (warning) implementado** — detector de string concat em loop
  (anti-pattern O(n²)). Antes catalogada como `planned`. Pesquisa contra
  NG Informática's [advpl-performance-research](https://github.com/nginformatica/advpl-performance-research)
  e [string-builder-advpl](https://github.com/nginformatica/string-builder-advpl)
  confirmou: caso real reportado de 1+ hora → 14-15s após otimização. Strings
  ADVPL imutáveis — cada `cVar += "x"` aloca string nova + copia anterior.
  
  Detecção em 2 passes:
  1. Encontra ranges (start, end) de cada loop body via stack-based parser
     (`While...EndDo`, `For...Next` — suporta loops aninhados)
  2. Em cada range, busca:
     - **Compound**: `cVar += ...` (variável c-prefix = string via hungarian)
     - **Long form**: `cVar := cVar + ...` (mesmo nome via regex backreference)
  
  Heurística hungarian notation distingue string concat (`cVar += "x"`) de
  numeric accumulator (`nTotal += 1`) — só flagga c-prefix.

  Sugestão de fix com 3 alternativas: array + FwArrayJoin/Array2String/
  ArrTokStr/CenArr2Str, FCreate+FWrite buffer, StringBuilder class custom.

- **`tests/unit/test_lint.py::TestPERF004StringConcatInLoop`** (11 asserts):
  6 positives (compound em While, em For, long form, nested loop, múltiplas
  concats, linha correta) + 5 negatives (numeric accumulator, fora de loop,
  string, comentário, long-form com vars diferentes). Validado 11/11 PASS,
  84/84 todos lint tests sem regressão.

### Changed
- **Catálogo `lint_rules.json`**: PERF-004 promovido de `status="planned"`
  para `status="active"` + `impl_function="_check_perf004_string_concat_in_loop"`.
  Total: **29 active + 6 planned = 35** (mantido).
- **Skill `advpl-code-review`**: PERF-004 movida pra "active" (18 single-file).
  Adicionado exemplo de fix com 3 alternativas (FwArrayJoin, FCreate buffer,
  StringBuilder).

## [0.3.8] - 2026-05-13

### Added
- **`MOD-004` (info) implementado** — detector de chamadas a UI legacy
  `AxCadastro` (Modelo 1), `Modelo2` (cabeçalho + grid lote) e `Modelo3`
  (pai/filho cabeçalho + itens). Antes catalogada como `planned`. Pesquisa
  contra TDN canônica confirmou as 3 assinaturas e o padrão de migração
  pra MVC moderno (FWMBrowse + MenuDef + ModelDef + ViewDef).
  
  Detecção:
  - Match `\b(AxCadastro|Modelo2|Modelo3)\s*\(` case-insensitive
  - Negative lookbehind pra `:`/`.` — exclui method calls (`obj:Modelo3()`)
  - Pula declarações de função homônima (`User Function AxCadastro()`)
  - Pula matches em strings literais e comentários
  - Pula nomes similares (`AxCadastrox`, `Modelo30`, `MyModelo2`)
  - Dedup por (linha, função) — múltiplas chamadas iguais na mesma linha = 1
  
  Sugestão de fix específica por função:
  - **AxCadastro**: migra pra Modelo 1 MVC com FWMBrowse + AddFields
  - **Modelo2**: migra pra MVC com AddFields master + AddGrid detail
  - **Modelo3**: migra pra MVC com AddFields cabeçalho + AddGrid itens + SetRelation pai/filho

- **`tests/unit/test_lint.py::TestMOD004LegacyCadastro`** (11 asserts):
  6 positives (cada uma das 3 funções, case-insensitive, múltiplas calls
  separadas, linha correta) + 5 negatives (string, comentário, definição
  homônima, similar-name, method call). Validado 11/11 PASS, 73/73 todos
  lint tests sem regressão.

### Changed
- **Catálogo `lint_rules.json`**: MOD-004 promovido de `status="planned"`
  para `status="active"` + `impl_function="_check_mod004_legacy_cadastro"`.
  Total: **28 active + 7 planned = 35** (mantido).
- **Skill `advpl-code-review`**: MOD-004 movida da tabela "planned" pra
  "active" (17 single-file agora). Adicionado exemplo de fix com 2 cenários
  completos de migração (AxCadastro→MVC Modelo 1, Modelo3→MVC pai/filho
  com SetRelation).

## [0.3.7] - 2026-05-13

### Added
- **`SEC-005` (critical) implementado** — detector de chamada de função
  TOTVS restrita. Antes catalogada como `planned`. Carrega o lookup
  `funcoes_restritas` (~194 entries: `StaticCall`, `PTInternal`, e ~192
  internas categorizadas por módulo) e cruza com chamadas de função no
  fonte. Detecção:
  - Match `<NAME>(...)` case-insensitive (ADVPL não diferencia caso)
  - Negative lookbehind pra `:`/`.` — exclui method calls (`obj:Name()`)
    e property access TLPP
  - Pula declarações de função homônima (`User Function StaticCall()`)
  - Pula matches em strings literais e comentários
  - Dedup por (linha, nome) — múltiplas chamadas iguais na mesma linha = 1 finding
  
  Sugestão de fix usa o campo `alternativa` do lookup quando disponível
  (ex: StaticCall sugere "User Function pública ou TLPP namespaced").

- **`tests/unit/test_lint.py::TestSEC005RestrictedFunctionCall`** (10 asserts):
  4 positives (StaticCall direto, case-insensitive, PTInternal interna,
  alternativa em sugestao_fix) + 6 negatives (User Function call, native
  function, function definition homônima, method call, em string, em
  comentário). Validado 10/10 PASS, 62/62 todos lint tests sem regressão.

### Changed
- **Catálogo `lint_rules.json`**: SEC-005 promovido de `status="planned"`
  para `status="active"` + `impl_function="_check_sec005_restricted_function_call"`.
  Total: **27 active + 8 planned = 35** (mantido).
- **Skill `advpl-code-review`**: SEC-005 movida da tabela "planned" pra
  "active" (16 single-file agora). Critical checklist inclui SEC-005.

## [0.3.6] - 2026-05-13

### Added
- **`PERF-005` (warning) implementado** — detector de `RecCount()` usado pra
  checar existência. Antes catalogada como `planned`. Detecta os padrões
  comuns: `RecCount() > 0`, `RecCount() >= 1`, `RecCount() != 0`,
  `RecCount() <> 0` (ADVPL legacy), incluindo variantes com alias-call
  (`SA1->(RecCount()) > 0`). NÃO sinaliza:
  - `RecCount() > 100` (limite de business intencional)
  - `nTotal := RecCount()` (apenas armazena, não checa existência)
  - `RecCount() > 0` dentro de string ou comentário
  
  Bug protegido: `RecCount()` força full scan da tabela inteira para contar
  todos os registros, mesmo quando você só quer saber se existe 1. Substituir
  por `!Eof()` após `DbSeek`/`DbGoTop` é O(1). Em SQL embarcado, `EXISTS`
  é melhor que `SELECT COUNT(*)`.
  
- **`tests/unit/test_lint.py::TestPERF005ReccountForExistence`** (10 asserts,
  TDD): 6 positives (gt-zero, gte-one, neq-zero, <>-legacy, alias-call,
  linha correta) + 4 negatives (limite real, atribuição, string, comentário).
  Validado 10/10 PASS, sem regressão (52/52 todos lint tests).

### Changed
- **Catálogo `lint_rules.json`**: PERF-005 promovido de `status="planned"`
  para `status="active"` + `impl_function="_check_perf005_reccount_for_existence"`.
  Total: **26 active + 9 planned = 35** (mantido).
- **Skill `advpl-code-review`**: PERF-005 movida da tabela "planned" pra
  "active" (15 single-file agora). Adicionado exemplo de fix com 4 cenários
  (errado, !Eof() simples, !alias->(Eof()), EXISTS em SQL).

## [0.3.5] - 2026-05-12

### Added
- **`BP-008` (critical) implementado** — detector de shadowing de variável
  reservada framework. Antes catalogada como `planned` (#1 follow-up). Agora
  detecta declarações `Local`/`Static`/`Private`/`Public` cujo nome bate
  (case-insensitive) com uma das **13 reservadas** Public criadas pelo
  framework Protheus: `cFilAnt`, `cEmpAnt`, `cUserName`, `cModulo`, `cTransac`,
  `nProgAnt`, `oMainWnd`, `__cInternet`, `nUsado`, `PARAMIXB`, `aRotina`,
  `lMsErroAuto`, `lMsHelpAuto`. Cobre declarações multi-var
  (`Local cVar1, cFilAnt, cVar2`) e TLPP-typed (`Local cFilAnt as character`).
  Bug protegido: programador declara `Local cFilAnt := ""` e depois usa
  `cFilAnt` achando que tem o valor da filial real, mas vê "" — ICMS errado,
  query cross-filial vazia, etc.
- **`tests/unit/test_lint.py::TestBP008ShadowedReserved`** (11 asserts,
  TDD red→green): 7 positives (cFilAnt simples, case-insensitive, multi-var,
  TLPP-typed, Public PARAMIXB, Private lMsErroAuto, linha correta) + 4
  negatives (similar-name `cFilAntiga`, reservada em string, reservada em
  comentário, uso correto sem declarar). Validado 11/11 PASS.

### Changed
- **Catálogo `lint_rules.json`**: BP-008 promovido de `status="planned"`
  para `status="active"` + `impl_function="_check_bp008_shadowed_reserved"`.
  Total: 25 active + 10 planned = 35 (mantido).
- **Test `test_lint_catalog_consistency`**: assert `n_active == 24`
  trocado por dinâmico `n_active == len(impl)` — futuras promoções
  planned→active não exigem update do test, só catálogo + impl.
- **Skill `advpl-code-review`**: BP-008 movida da tabela "planned" pra
  "active" (14 single-file agora). Adicionado exemplo de fix com 3 cenários
  (errado, correto com rename, correto sem declarar).
- **Skill `advpl-fundamentals`**: nota sobre BP-008 atualizada — agora
  detecta via `/plugadvpl:lint`, cobre 13 reservadas case-insensitive.

## [0.3.4] - 2026-05-12

### Fixed
- **[Issue #1](https://github.com/JoniPraia/plugadvpl/issues/1) — `lookups/lint_rules.json`
  alinhado com `parsing/lint.py`**. Antes (v0.3.0..v0.3.3), o catálogo descrevia
  comportamentos diferentes da implementação real para o mesmo `regra_id`:
  10 regras com severidade divergente, 15 com título/topic completamente outros
  (ex: catálogo dizia `BP-002` = "Local fora do header"; impl emitia `BP-002` =
  "BEGIN TRANSACTION sem END"). Resultado: usuário lia output do lint, buscava
  no catálogo e via descrição errada. Catálogo agora reflete a impl 1:1.
  Adicionados 2 campos novos: `status` (`active`/`planned`) e `impl_function`
  (nome da `_check_*` em `lint.py`). Migration 003 adiciona as colunas em
  `lint_rules` table.

### Added
- **Test de regressão** `tests/unit/test_lint_catalog_consistency.py` — 7 asserts
  que impedem novo drift catalog × impl. Falha o build se severidade, título,
  status, impl_function ou contagem de regras divergem.
- **Migration 003** `cli/plugadvpl/migrations/003_lint_rules_status.sql` —
  `ALTER TABLE lint_rules ADD COLUMN status, impl_function`. SCHEMA_VERSION
  bumped 2 → 3.

### Changed
- **24 active vs 11 planned** explicitamente declarado no catálogo:
  - **Active** (24): BP-001, BP-002, BP-003, BP-004, BP-005, BP-006,
    SEC-001, SEC-002, PERF-001, PERF-002, PERF-003, MOD-001, MOD-002,
    SX-001..SX-011.
  - **Planned** (11): BP-002b, BP-007, BP-008, SEC-003, SEC-004, SEC-005,
    PERF-004, PERF-005, PERF-006, MOD-003, MOD-004 — catalogadas como
    roadmap/checklist mental, ainda sem `_check_*` em `lint.py`.
- **Skill `advpl-code-review`** atualizada — drift footnote substituída por
  nota explicando o realinhamento + referência ao test guard.

### Changed
- **Skills overhaul completo** — todas as 16 knowledge skills (`plugadvpl-index-usage`,
  `advpl-fundamentals`, `advpl-code-review`, `advpl-mvc`, `advpl-mvc-avancado`,
  `advpl-embedded-sql`, `advpl-pontos-entrada`, `advpl-encoding`, `advpl-webservice`,
  `advpl-web`, `advpl-jobs-rpc`, `advpl-dicionario-sx`, `advpl-dicionario-sx-validacoes`,
  `advpl-matxfis`, `advpl-tlpp`, `advpl-advanced`) revisadas, pesquisadas
  contra TDN/TOTVS Central/blogs canônicos e atualizadas. Mudanças cross-cutting:
  - **Phantom command `/plugadvpl:sql` removido** de 3 skills (não existe no CLI).
  - **Nomes de tabela corrigidos** — `sources`→`fontes`, `simbolos`→`fonte_chunks`,
    `calls`→`chamadas_funcao`, `params`→`parametros_uso`, `sql_refs`→`sql_embedado`,
    `ws_services`/`ws_structures`→`rest_endpoints`/`http_calls`. `mvc_hooks` e
    `dictionary_sx` removidos (não existem no schema).
  - **bCommit/bTudoOk descontinuados** documentados — `advpl-mvc` agora lidera com
    `FWModelEvent` + `InstallEvent()` (3 momentos: BeforeTTS/InTTS/AfterTTS), padrão
    canônico TOTVS desde Protheus 12.1.17+.
  - **`FWMVCRotina` corrigido para `FWMVCRotAuto`** (canônico).
  - **Limite identificador clarificado** — `.prw`/`.prx` mantém legado 10 chars
    (truncamento silencioso causa bug `nTotalGeralAnual` ≡ `nTotalGeralMensal`);
    `.tlpp` libera 250 chars.
  - **TLPP default PRIVATE vs ADVPL PUBLIC** documentado — armadilha de port.
  - **Lint rules alinhados à impl real** (não ao catálogo) em `advpl-code-review`,
    `advpl-embedded-sql`, `advpl-jobs-rpc`, `advpl-advanced`. Discrepância
    documentada como [issue #1](https://github.com/JoniPraia/plugadvpl/issues/1)
    pra resolução em v0.3.4.
  - **Cross-refs `[[name]]`** entre skills — ~120 links bidirecionais.
  - **Sources sections** com ~80 referências externas verificáveis (TDN, TOTVS
    Central, Terminal de Informação, Medium, GitHub canônicos).

### Fixed
- **Skills com claims falsos sobre estrutura interna** — várias skills citavam
  tabelas SQLite que não existem no schema. Auditadas e corrigidas individualmente.

## [0.3.3] - 2026-05-12

### Added
- **Skill `advpl-refactoring`** — 6 padrões de refactor comuns em ADVPL/TLPP com
  before/after side-by-side: DbSeek em loop → SQL embarcado (anti-N+1), Posicione
  repetido → cache em variável, IFs hardcoded → SX5/SX6 ou User Function central,
  AxCadastro/Modelo2/3 → MVC, string concat em loop → array + FwArrayJoin,
  RecLock solto → Begin Transaction. Inclui "quando NÃO refatorar" pra cada padrão
  + workflow plugadvpl integrado.
- **Skill `advpl-debugging`** — top 30 erros comuns em produção Protheus com tabela
  rápida sintoma → causa raiz → diagnóstico → fix. Cobre `Variable does not exist`,
  `Type mismatch` pós-query, `RecLock failed`, `Index out of range`, browse vazio,
  MV_PAR não inicializado, Job não roda, REST 500, encoding bagunçado, perf
  subitamente péssima, gatilho SX7 não dispara, etc. Inclui métodos de debug manual
  (ConOut, MemoWrite, FwLogMsg, varInfo, aClone+diff) pra quando não dá pra
  anexar debugger gráfico.

### Changed
- **`install.ps1` detecta Python local existente** (via `py -3.12` / `py -3.11` que
  consulta o registro Windows, não cai na MS Store stub). Quando encontra, passa
  `--python <path>` pro `uv tool install`, evitando download de ~30MB de Python
  managed na primeira instalação (que silenciava por minutos sem progresso). Script
  agora tem 4 steps em vez de 3 (uv → Python → plugadvpl → done).
- **`release.yml`** agora anexa `.whl` + `.tar.gz` ao GitHub Release. Antes o job
  `github-release` só fazia `actions/checkout@v4` e tentava `files: cli/dist/*` que
  não existia naquele job — resultado: Release ficava vazio desde v0.3.0. Fix:
  `upload-artifact` no job `publish-pypi`, `download-artifact` no `github-release`.

## [0.3.2] - 2026-05-12

### Fixed
- **CRITICAL: `plugadvpl --help` crashava no Windows desde v0.3.0**. Docstrings
  dos comandos `impacto` e `gatilho` e o help de `ingest-sx` continham
  setas Unicode (`↔`, `→`) que não existem em cp1252. O console default
  do Windows (PS 5.1, cmd.exe) usa cp1252 e Python jogava
  `UnicodeEncodeError: 'charmap' codec can't encode character '↔'`
  no meio da renderização. Resultado: nenhum usuário Windows conseguia
  rodar `plugadvpl --help`, `plugadvpl impacto --help`, etc. Fix em duas
  camadas:
  - **App layer**: setas Unicode trocadas por ASCII (`<->`, `->`) em todas
    as strings user-facing (docstrings, help text, snippets de lint
    SX-002/SX-010, output do `impacto`/`gatilho`).
  - **I/O layer (defense)**: `main()` agora chama `sys.stdout/stderr.
    reconfigure(encoding='utf-8', errors='replace')` no Windows. Mesmo
    que algum char Unicode escape no futuro, vira `?` em vez de tombar.
- **`install.ps1` rodando via `irm | iex`** tinha o shebang `#!/usr/bin/env
  pwsh` interpretado como comando porque o arquivo estava UTF-8 BOM
  (introduzido no v0.3.1 pra PS 5.1 compat); o BOM sobrevivia ao
  Invoke-RestMethod e tornava o `#` da linha 1 invisível ao parser. Erro
  cosmético — install continuava — mas confundia quem rodasse manualmente.
  Fix: arquivo regravado UTF-8 **sem BOM**, mensagens ASCII-only
  (`não` → `nao`, em-dash → traço normal). Glifos `[OK]`/`[X]`/`[!]`
  preservados, formatação melhorada (`[OK] uv` em vez de `[OK]uv`).
- **`install.ps1` step [2/3] parecia travado** em primeira instalação.
  Adicionado aviso: "na primeira instalacao pode levar 1-3 min: uv baixa
  Python managed + deps. Sem barra de progresso ate terminar".

### Changed
- **Bump `uvx plugadvpl@0.3.0` → `@0.3.1`** em todos os assets do plugin
  (18 skills, 4 agents, hook `session-start.mjs`, `cli/README.md`). Sem
  este bump, slash commands depois do `/plugin marketplace update`
  continuavam invocando CLI v0.3.0 com o bug do `--help` e o SX-005
  quebrado (corrigidos no v0.3.1).

## [0.3.1] - 2026-05-12

### Added
- **4 slash commands faltantes do v0.3.0**: `/plugadvpl:ingest-sx`,
  `/plugadvpl:impacto`, `/plugadvpl:gatilho`, `/plugadvpl:sx-status`. Os
  comandos CLI já existiam desde v0.3.0, mas os wrappers de skill nunca
  foram criados — o README anunciava como `/plugadvpl:*` mas só funcionavam
  via CLI direta. Agora o plugin Claude Code expõe os 18 comandos completos.

### Changed
- **Bump `uvx plugadvpl@0.1.0` → `@0.3.0`** em todos os assets do plugin
  (14 skills antigas, 4 agents, hook `session-start.mjs`, `cli/README.md`).
  Como migration 002 introduziu o schema v2, qualquer slash command pinado
  em v0.1.0 contra um índice atual falharia com `OperationalError`. Specs
  históricos em `docs/superpowers/` ficaram intocados.

### Fixed
- **`install.ps1`** — compatibilidade real com Windows PowerShell 5.1.
  Três problemas atacados de uma vez: TLS default (1.0/1.1) que quebrava
  `irm https://astral.sh/uv/install.ps1`, glifos UTF-8 (`✓`/`✗`/`⚠`) que
  o parser PS 5.1 lia como cp1252 e travavam com `unexpected token`, e
  `2>&1` em executáveis nativos que disparavam `NativeCommandError` com
  `$ErrorActionPreference='Stop'`. PS 7+ continua funcionando sem mudança.
- **Lint cross-file `SX-005`** — estava silenciosamente quebrado desde
  v0.3.0. O segundo probe usava `LIMIT 1` dentro de cada perna de um
  `UNION ALL` (sintaxe inválida em SQLite), e o erro era engolido pelo
  `try/except sqlite3.OperationalError` em `lint_cross_file`. Nenhum
  finding SX-005 foi emitido em produção até este fix. De brinde, o
  N+1 query (1+N*2 LIKE scans) virou 3 queries agregadas com substring
  em memória — ~37 ms para 500 campos × 2.000 fontes em bench sintético.

## [0.3.0] - 2026-05-11

### Added — Universo 2: Dicionário SX

- **Migration 002** — 11 novas tabelas SQLite cobrindo todo o dicionário
  Protheus exportado em CSV: `tabelas` (SX2), `campos` (SX3), `indices` (SIX),
  `gatilhos` (SX7), `parametros` (SX6), `perguntas` (SX1), `tabelas_genericas`
  (SX5), `relacionamentos` (SX9), `pastas` (SXA), `consultas` (SXB),
  `grupos_campo` (SXG). Indexes específicos para cross-lookup em
  `validacao`/`vlduser`/`when_expr`/`inicializador`/`f3`.
- **Parser SX** (`plugadvpl/parsing/sx_csv.py`, ~440 linhas, type-hinted) —
  port do parser interno do autor (`parser_sx.py`, 872 linhas). Auto-detect
  encoding (cp1252/utf-8-sig), delimiter (vírgula/ponto-e-vírgula),
  conversão XLSX disfarçado de CSV, sanitização de surrogates Unicode.
  Filtra rows logicamente deletadas (`D_E_L_E_T_ = '*'`).
- **Pipeline** `plugadvpl/ingest_sx.py` — orquestrador idempotente
  (`INSERT OR REPLACE`), batches de 1000 rows, tolerante a CSVs faltantes.
- **3 novos comandos CLI**:
  - `plugadvpl ingest-sx <pasta-csv>` — popula o dicionário SX no índice.
  - `plugadvpl impacto <campo> [--depth 1..3]` — **killer feature**: cruza
    referências a um campo em fontes ↔ SX3 ↔ SX7 ↔ SX1, com cadeia de
    gatilhos configurável.
  - `plugadvpl gatilho <campo> [--depth 1..3]` — lista cadeia SX7
    origem → destino com BFS.
  - `plugadvpl sx-status` — counts por tabela do dicionário.
  - `plugadvpl lint --cross-file` — recalcula as 11 regras cross-file SX-***.
- **11 cross-file lint rules** SX-001..SX-011 (regra_id `SX-*`):
  X3_VALID com U_xxx não indexado, gatilho SX7 com destino inexistente em SX3,
  parâmetro MV_ nunca lido, pergunta SX1 nunca usada, campo custom sem
  referências, X3_VALID com SQL embarcado (BeginSql/TCQuery), função restrita
  TOTVS em validador, tabela compartilhada com xFilial em VALID, campo
  obrigatório com INIT vazio, gatilho Pesquisar sem SEEK, X3_F3 apontando
  para SXB inexistente.
- **Skill nova** `advpl-dicionario-sx-validacoes` — guia completo das
  expressões ADVPL embutidas no dicionário (X3_VALID/INIT/WHEN/VLDUSER,
  X7_REGRA/CONDIC/CHAVE, X1_VALID, X6_VALID/INIT) e workflow para
  análise de impacto.
- **Tests** — 11 novos integration tests cobrindo ingest-sx, impacto,
  gatilho, sx-status, lint --cross-file; 1 bench (~26ms para 11 CSVs
  sintéticos); 3 e2e_local contra `D:/Clientes/CSV` (gated por env var
  `PLUGADVPL_E2E_SX_DIR`).

### Changed
- `SCHEMA_VERSION` bumped to `"2"`.
- `plugin.json` / `marketplace.json` versão `0.3.0`.
- `plugadvpl --help` agora lista 18 subcomandos (14 + 4 novos).

### Notes
- Plugin agora ingere **apenas** o dicionário custom do cliente
  (`plugadvpl ingest-sx <pasta>`). Padrão TOTVS é ignorado por design
  (carga inútil para auditoria de customização).
- `sxg.csv` com header `X3_*` (export malformado) é silenciosamente
  pulado — apenas exports legítimos com header `XG_*` são ingeridos.

## [0.2.0] - 2026-05-11

### Added
- ~21k lines of curated ADVPL/TLPP reference documentation embedded as
  `reference.md` supporting files in 6 existing skills (fundamentals, mvc,
  embedded-sql, webservice, pontos-entrada, matxfis).
- 5 new knowledge skills:
  - `advpl-advanced` — threads, IPC, debug, OO em profundidade
  - `advpl-tlpp` — TLPP moderno (OO, namespaces, annotations)
  - `advpl-web` — interfaces web (Webex/HTML/WebExpress)
  - `advpl-dicionario-sx` — SX1/SX2/SX3/SX5/SX6/SX7/SIX/SXA/SXB
  - `advpl-mvc-avancado` — eventos, validações cruzadas, FWMVCRotAuto
- 7 production-grade code examples embedded in `skills/<x>/exemplos/`.

### Changed
- Plugin agora tem 30 skills total (15 knowledge + 14 command + 1 setup,
  contagem revisada após reorganização).

## [0.1.0] - 2026-05-11

### Added

- Plugin Claude Code com 24 skills (14 slash command + 10 thematic knowledge) + 4 agents + 1 SessionStart hook (Node.js)
- CLI Python `plugadvpl` (PyPI) com 14 subcomandos: `init`, `ingest`, `reindex`, `status`, `find`, `callers`, `callees`, `tables`, `param`, `arch`, `lint`, `doctor`, `grep`, `version`
- Schema SQLite com 22 tabelas + 2 FTS5 (external content + trigram) + 6 lookups pré-populados (279 funcoes_nativas, 194 funcoes_restritas, 24 lint_rules, 6 sql_macros, 8 modulos_erp, 15 pontos_entrada_padrao)
- Parser ADVPL/TLPP com strip-first pattern (ignora comentários `*`, `&&`, `//`, `/* */` + strings) e ~25 extractors module-level
- Lint engine com 13 regras single-file (BP/SEC/PERF/MOD) executadas durante ingest
- Ingest pipeline com paralelização adaptive (single-thread / ProcessPool com fork em Linux, spawn em macOS/Windows)
- CLAUDE.md fragment idempotente escrito pelo `init` (delimitado entre `<!-- BEGIN plugadvpl -->` ... `<!-- END plugadvpl -->`)
- CI matrix 3 OS × 3 Python + Trusted Publisher OIDC + github-action-benchmark
- 239 tests (unit + integration + 15 snapshots syrupy + 1 bench + 3 e2e_local)
- Docs: README, cli-reference, schema (Mermaid ER), architecture, CONTRIBUTING, SECURITY, CoC

### Known limitations

Veja [`docs/limitations.md`](docs/limitations.md) para a lista completa de gaps conhecidos
(parser, lint, schema, performance, plataforma) e o que NÃO está incluído neste MVP.
