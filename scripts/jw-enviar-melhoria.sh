#!/usr/bin/env bash
# jw-enviar-melhoria.sh — roda gates, publica no fork, abre issue+PR upstream,
#   integra a melhoria no branch jobwise (cópia local sempre usável) e atualiza o ledger.
# Uso: scripts/jw-enviar-melhoria.sh <slug> "<título da melhoria>"
# (downstream-only — existe apenas no branch jobwise)
set -euo pipefail

SLUG="${1:?uso: jw-enviar-melhoria.sh <slug> \"<título>\"}"
TITLE="${2:?informe o título da melhoria}"
UPSTREAM_REPO="JoniPraia/plugadvpl"
FORK_OWNER="JobwiseTec"
BRANCH="feat/$SLUG"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

echo ">> garantindo branch $BRANCH..."
git checkout "$BRANCH"

echo ">> gates de qualidade (ruff/mypy/pytest — mesmos do CI upstream)..."
(
  cd cli
  uv run ruff format --check .
  uv run ruff check .
  uv run mypy --strict plugadvpl
  uv run pytest tests/unit tests/integration -q
)

echo ">> push da branch pro fork (origin)..."
git push -u origin "$BRANCH"

echo ">> abrindo issue de proposta no upstream..."
ISSUE_URL=$(gh issue create --repo "$UPSTREAM_REPO" \
  --title "[feat] $TITLE" --label enhancement \
  --body "## Problema que resolve

_(descreva a dor do dia-a-dia ADVPL/Protheus)_

## Solução proposta

_(como funciona + exemplo de uso/output)_

## Alternativas consideradas

_(workarounds atuais)_")
ISSUE_NUM="${ISSUE_URL##*/}"
echo "   issue: $ISSUE_URL"

echo ">> abrindo PR (fork -> upstream) referenciando a issue..."
PR_URL=$(gh pr create --repo "$UPSTREAM_REPO" \
  --base main --head "$FORK_OWNER:$BRANCH" \
  --title "feat: $TITLE" \
  --body "Closes #$ISSUE_NUM

## Resumo

_(o que muda e por quê)_

## Testes

_(o que foi validado: unit/integration)_")
PR_NUM="${PR_URL##*/}"
echo "   PR: $PR_URL"

echo ">> integrando a melhoria no branch jobwise (independe da aceitação)..."
git checkout jobwise
git merge --no-ff "$BRANCH" -m "merge($SLUG): integra melhoria no downstream jw-advpl"

echo ">> atualizando o ledger MELHORIAS.md..."
printf '| %s | [#%s](%s) | [#%s](%s) | proposed | |\n' \
  "$SLUG" "$ISSUE_NUM" "$ISSUE_URL" "$PR_NUM" "$PR_URL" >> MELHORIAS.md
git add MELHORIAS.md
git commit -m "docs(melhorias): registra $SLUG (issue #$ISSUE_NUM, PR #$PR_NUM)"
git push origin jobwise

cat <<EOF

OK ✅  '$SLUG' concluído:
  - issue upstream : $ISSUE_URL
  - PR upstream    : $PR_URL
  - integrado em   : jobwise (cópia local sempre usável)
  - ledger         : MELHORIAS.md atualizado (status: proposed)

Edite a issue/PR no GitHub para preencher os detalhes (os corpos foram criados como template).
EOF
