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

if [ "$(git rev-parse --abbrev-ref HEAD)" = "jobwise" ]; then
  echo "ERRO: rode este script do clone principal, não do worktree jobwise." >&2
  exit 1
fi

# descobre o worktree que está no branch jobwise (onde a melhoria é integrada)
JOBWISE_WT="$(git worktree list --porcelain \
  | awk '/^worktree /{wt=substr($0,10)} /^branch refs\/heads\/jobwise$/{print wt; exit}')"
if [ -z "${JOBWISE_WT:-}" ]; then
  echo "ERRO: worktree do branch jobwise não encontrado (crie com: git worktree add ../jw-advpl-work jobwise)." >&2
  exit 1
fi

echo ">> garantindo branch $BRANCH..."
git checkout "$BRANCH"

echo ">> gates: ruff/mypy só nos arquivos do diff; pytest completo..."
# Lint só nos .py mudados nesta branch vs upstream/main — evita travar em lint
# PRE-EXISTENTE do upstream (e em drift de versão do ruff local vs CI).
MERGE_BASE="$(git merge-base upstream/main HEAD)"
mapfile -t _CHANGED < <(git diff --name-only --diff-filter=ACMR "$MERGE_BASE"...HEAD -- 'cli/**/*.py')
_PKG_PY=()   # arquivos do pacote (mypy) — relativos a cli/
_ALL_PY=()   # todos os .py mudados (ruff) — relativos a cli/
for _f in "${_CHANGED[@]}"; do
  _rel="${_f#cli/}"
  _ALL_PY+=("$_rel")
  case "$_rel" in plugadvpl/*) _PKG_PY+=("$_rel");; esac
done

(
  cd cli
  if [ ${#_ALL_PY[@]} -gt 0 ]; then
    # ruff = NÃO-bloqueante (warn): ruff local pode ser mais novo que o CI do upstream
    # e acusar estilo pré-existente. O CI do maintainer é o gate de estilo real.
    echo "   ruff (aviso, não bloqueia) em: ${_ALL_PY[*]}"
    uv run ruff check "${_ALL_PY[@]}" || echo "   ⚠ ruff check apontou itens — REVISE antes do PR."
    uv run ruff format --check "${_ALL_PY[@]}" || echo "   ⚠ ruff format sugeriu mudanças — REVISE antes do PR."
    # mypy = BLOQUEANTE, só no pacote (testes não são strict-typed)
    if [ ${#_PKG_PY[@]} -gt 0 ]; then
      echo "   mypy --strict (bloqueante): ${_PKG_PY[*]}"
      uv run mypy --strict "${_PKG_PY[@]}"
    fi
  else
    echo "   (nenhum .py mudado sob cli/ — pulando ruff/mypy)"
  fi
  echo "   pytest unit+integration (bloqueante)"
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

echo ">> integrando a melhoria no branch jobwise (no worktree $JOBWISE_WT)..."
(
  cd "$JOBWISE_WT"
  git merge --no-ff "$BRANCH" -m "merge($SLUG): integra melhoria no downstream jw-advpl"
  # insere a linha DENTRO da tabela (após o marcador) — não no fim do arquivo,
  # que hoje tem seções depois da tabela.
  MARKER="<!-- novas linhas são anexadas aqui pelo jw-enviar-melhoria.sh -->"
  ROW="| $SLUG | [#$ISSUE_NUM]($ISSUE_URL) | [#$PR_NUM]($PR_URL) | proposed | |"
  _tmp=$(mktemp)
  awk -v marker="$MARKER" -v row="$ROW" '{print} index($0,marker){print row}' MELHORIAS.md > "$_tmp" && mv "$_tmp" MELHORIAS.md
  git add MELHORIAS.md
  git commit -m "docs(melhorias): registra $SLUG (issue #$ISSUE_NUM, PR #$PR_NUM)"
  git push origin jobwise
)

cat <<EOF

OK ✅  '$SLUG' concluído:
  - issue upstream : $ISSUE_URL
  - PR upstream    : $PR_URL
  - integrado em   : jobwise (cópia local sempre usável)
  - ledger         : MELHORIAS.md atualizado (status: proposed)

Edite a issue/PR no GitHub para preencher os detalhes (os corpos foram criados como template).
EOF
