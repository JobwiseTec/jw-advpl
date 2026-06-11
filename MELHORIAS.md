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
