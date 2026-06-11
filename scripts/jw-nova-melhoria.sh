#!/usr/bin/env bash
# jw-nova-melhoria.sh — abre uma branch de melhoria a partir do upstream/main sincronizado.
# Uso: scripts/jw-nova-melhoria.sh <slug>
# (downstream-only — existe apenas no branch jobwise)
set -euo pipefail

SLUG="${1:?uso: jw-nova-melhoria.sh <slug-curto-da-melhoria>}"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

echo ">> sincronizando main com upstream..."
git checkout main
git fetch upstream --tags
git reset --hard upstream/main
git push origin main

echo ">> criando branch feat/$SLUG a partir de upstream/main..."
git checkout -b "feat/$SLUG"

cat <<EOF

OK. Branch 'feat/$SLUG' criada limpa a partir de upstream/main.

Próximos passos:
  1. Implemente a melhoria.
  2. scripts/jw-enviar-melhoria.sh "$SLUG" "<título da melhoria>"
     (roda gates, push no fork, abre issue+PR upstream, integra no jobwise e atualiza o ledger)
EOF
