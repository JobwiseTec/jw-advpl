# Ledger de melhorias — downstream `jw-advpl`

> **Só existe no branch `jobwise`.** Fonte da verdade do que é seu, do que foi proposto upstream e do status.
> Atualizado automaticamente pelo `scripts/jw-enviar-melhoria.sh`.

**Fork:** [`JobwiseTec/jw-advpl`](https://github.com/JobwiseTec/jw-advpl) · **Upstream:** [`JoniPraia/plugadvpl`](https://github.com/JoniPraia/plugadvpl)

## Como ler o status

- `proposed` — issue + PR abertos no upstream, aguardando review.
- `accepted` — PR mergeado upstream (já chega via sync do `main`).
- `rejected` — upstream recusou; vive **só** no `jobwise`.
- `local-only` — decisão consciente de não propor (específico seu); vive só no `jobwise`.
- `superseded` — substituído por outra melhoria/refactor.

## Melhorias

| Slug | Issue | PR | Status | Notas |
|------|-------|----|--------|-------|
<!-- novas linhas são anexadas aqui pelo jw-enviar-melhoria.sh -->
| rebrand-plugin-jw-advpl | — | — | local-only | renomeia plugin+marketplace p/ jw-advpl e source local (não upstreamável) |
| fragment-namespace-aware | [#152](https://github.com/JoniPraia/plugadvpl/issues/152) | [#153](https://github.com/JoniPraia/plugadvpl/pull/153) | proposed | fragment usa namespace real do plugin |
| gate-lint-diff-only | — | — | local-only | jw-enviar-melhoria: ruff só no diff e não-bloqueante (drift de versão) |
| upstream-watch | — | — | local-only | workflow semanal avisa release nova do upstream (issue no fork) |
| mvc-setproperty-fwbuildfeature | [#155](https://github.com/JoniPraia/plugadvpl/issues/155) | [#156](https://github.com/JoniPraia/plugadvpl/pull/156) | proposed | SetProperty+FWBuildFeature p/ WHEN/VALID/INIT por código |

## Qual modelo usar em cada etapa do ciclo

Guia prático de custo/qualidade. Regra geral: **cabe num script/passo-a-passo claro → Haiku;
exige decidir sob ambiguidade ou diagnosticar por que algo quebrou → Opus** (Sonnet como meio-termo).
No Claude Code dá pra trocar com `/model`, e subagentes podem usar modelo diferente do principal
(ex.: Opus orquestra, dispara Haiku pra partes mecânicas).

| Etapa do ciclo | Modelo sugerido | Por quê |
|---|---|---|
| `jw-nova-melhoria.sh` / `jw-enviar-melhoria.sh` (ciclo já scriptado) | **Haiku 4.5** | passo-a-passo determinístico |
| Edição pequena/isolada, mudança de literal, seguir checklist | **Haiku 4.5** | bem-definido |
| Busca/comparação de arquivos, consulta ao índice plugadvpl, git/gh "receita" | **Haiku 4.5** | mecânico |
| Implementar feature nova ou refactor com nuance | **Sonnet 4.6** (ou Opus) | precisa de design, mas escopado |
| Resolver conflito de merge não-trivial (ex.: marca vs upstream) | **Opus 4.8** | julgamento |
| Debugar CI/tooling (ruff/version drift, schedule/default-branch/Issues off) | **Opus 4.8** | diagnóstico de causa por ausência de erro |
| Decisão de arquitetura/fluxo, comparação ambígua, "o que portar do jobwise" | **Opus 4.8** | trade-offs sob ambiguidade |
| Escolher entre abordagens / fazer as perguntas certas antes de agir | **Opus 4.8** | clarificação dirigida |

> Heads-up: o gate do `jw-enviar-melhoria.sh` deixa o **ruff não-bloqueante** — então, rodando o ciclo
> com Haiku, **revise os avisos de ruff/format antes do PR** (o Haiku tende a não questioná-los). `mypy`
> e `pytest` continuam bloqueantes, então erro de tipo/teste o script pega sozinho.
