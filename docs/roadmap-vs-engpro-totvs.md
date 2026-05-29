# Roadmap — gaps do plugadvpl vs EngPro ADVPL/TLPP (TOTVS)

> Análise comparativa entre o **plugadvpl** (ferramenta independente da comunidade) e o
> repositório oficial **[totvs/engpro-advpl-tlpp-skills](https://github.com/totvs/engpro-advpl-tlpp-skills)**
> (site: https://skills.engpro.totvs.io/).
>
> Data da análise: 2026-05-29 · plugadvpl v0.16.2

---

## Diferença arquitetural de fundo

| | **EngPro (TOTVS)** | **plugadvpl (nós)** |
|---|---|---|
| O que é | **Só skills** (instruções/prompts) | Skills **+ ferramentas** (índice, compile, lint…) |
| Dicionário SX | Roda `execute-sql` no **banco ao vivo** (depende de tool externo) | **Ingere** num índice SQLite, consulta **offline** + cruza com código |
| Doc TOTVS | `product-docs-search` (MCP TDN ao vivo) | — (não temos) |
| Code review | Mapeia regras **SonarQube oficiais** (`sonar-rules.engpro.totvs.com.br`, 54 regras) | Taxonomia **própria** (40 regras BP/SEC/PERF/SX) |
| Alcance | **Multi-agente** (CLAUDE.md + AGENTS.md) | **Claude Code** principalmente |
| Superpowers | As **mesmas 14** que usamos | As mesmas 14 |

**Insight central:** eles dependem de tools externos que o host precisa fornecer
(`execute-sql`, `product-docs-*` — provavelmente MCP servers da TOTVS). Nós **trazemos a
ferramenta junto**. Modelos opostos: eles sempre-fresco-mas-precisa-conexão; nós
self-contained-offline.

**Posicionamento:** somos **complementares, não concorrentes**. Eles são a camada de
instrução oficial; nós somos a única com ferramental (índice/compile/análise).

---

## O que SÓ nós temos (nosso fosso — eles dizem explicitamente "does NOT index/compile/analyze")

Índice SQLite+FTS5 · `compile` (advpls multi-env) · `tq` (troca quente) ·
`ingest-protheus` (COLETADB ao vivo) · lint executável cross-file · call-graph real
(`callers/callees/impacto/trace`) · `ini-audit` (487 regras) · `log-diagnose` (93 tips) ·
`metrics/hotspots/cobertura-doc`.

Nenhum gap abaixo ameaça isso — os gaps **completam** a ferramenta, não defendem.

---

## Tabela de gaps (ordenada por importância)

| # | Coisa | O que é | Dá pra implementar? | Esforço | Importância | Status |
|---|---|---|---|---|---|---|
| 1 | **Mapeamento SonarQube** | Traduzir nossas 40 regras de lint pros IDs oficiais TOTVS (`SEC-001 ≈ BG1000`) | Sim — campo novo no catálogo de regras | 🟢 Baixo | 🔴 Alta | **✅ PARCIAL — 10/40 (v0.16.0)** |
| 2 | **Suporte multi-agente (AGENTS.md)** | Skills rodarem em Cursor, Copilot, Gemini — não só Claude. A CLI já roda em qualquer lugar | Sim — adaptar formato das skills | 🟡 Médio | 🔴 Alta | **✅ FASE 1 — Codex+Cursor (v0.16.1/v0.16.2)** |
| 3 | **Gerador de teste E2E (TIR)** | Skill que gera teste de tela em Python (TIR robot) — clica, preenche, valida | Sim — skill + templates | 🟡 Médio | 🔴 Alta | pendente |
| 4 | **Gerar ProtheusDOC** | Skill que **escreve** o bloco de doc da função (hoje só **lemos** com `docs`) | Sim — temos vantagem: índice já sabe params/assinatura | 🟢 Baixo | 🟡 Média | pendente |
| 5 | **Teste unitário (ProBat)** | Gerar unit test TLPP (`@TestFixture`) — testa função isolada, sem subir tela | Sim — skill + templates | 🟡 Médio | 🟡 Média | pendente |
| 6 | **Migração ADVPL→TLPP** | Skill dedicada que converte código clássico pro TLPP moderno | Sim — temos `advpl-tlpp` mas não a skill de migração | 🟡 Médio | 🟡 Média | pendente |
| 7 | **Geradores dedicados** (MVC, REST, FWRest client) | Skills que **geram** código pronto desses padrões | Sim — temos o agent `code-generator`, falta granular | 🟡 Médio | 🟡 Média | pendente |
| 8 | **Reduzir complexidade de método** | Skill que pega método complexo e quebra em helpers | Sim — temos `metrics`/`hotspots` que **apontam** candidatos | 🟢 Baixo | 🟢 Baixa | pendente |
| 9 | **Spec-Driven Development (SDD)** | Metodologia formal: especifica→desenha→tarefas→executa (17 arquivos) | Sim, mas skill grande | 🔴 Alto | 🟢 Baixa | pendente |
| 10 | **Busca na doc TDN ao vivo** | Buscar/ler documentação oficial TOTVS em tempo real | Parcial — precisa scraping ou MCP da TOTVS | 🔴 Alto | 🟢 Baixa | pendente |

---

## Comparação skill a skill (aderência)

**✅ Empate / cobrimos igual** (em vários somos mais fortes — temos lint/índice executável, não só guia):
code-review, refactor, query-builder, entry-point-designer, mvc, encoding, context-map, sql-code-review.

**❌ Eles têm, nós não:** ver tabela de gaps acima (TIR, ProBat, doc-writer, SDD, migração, geradores, SonarQube mapping, multi-agente).

---

## Priorização

- **Itens 1-4 são o foco.** O #1 (SonarQube) é o melhor custo-benefício: pouco esforço,
  ganho grande de legitimidade + interop com vocabulário que o mercado já conhece.
- **Do #5 pra baixo:** "se sobrar fôlego" — já cobrimos parcialmente (geradores via agent,
  complexidade via metrics), dependem de infra TOTVS (TDN), ou pesados demais pro retorno (SDD).

### Sobre o item 1 — mapeamento SonarQube

A TOTVS publicou regras SonarQube oficiais pra ADVPL/TLPP em
`sonar-rules.engpro.totvs.com.br` (54 regras catalogadas em grupos G1-Security,
G2-Performance, G3-Legacy, etc). Mapear nossas 40 regras pros IDs deles dá:

1. Falar a língua que o mercado já conhece (dev vê `BG1000` e entende)
2. Legitimidade **sem dependência** — continuamos offline/independentes
3. Ponte de adoção pra quem já roda Sonar no CI

Não é virar SonarQube nem depender dele — é **traduzir** o que já fazemos pro dialeto oficial.

### Sobre o item 2 — suporte multi-agente

v0.16.1 entregou AGENTS.md gêmeo (cobre Codex). v0.16.2 entregou Cursor Rules nativos via `.cursor/rules/*.mdc` gerados no `init`. Pendente: Phase 2 GitHub Copilot.
