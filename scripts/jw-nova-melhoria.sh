#!/usr/bin/env bash
# jw-nova-melhoria.sh — abre uma branch de melhoria a partir do upstream/main sincronizado.
# Uso: scripts/jw-nova-melhoria.sh <slug>
# RODE DO CLONE PRINCIPAL (não do worktree main de integração). Downstream-only.
set -euo pipefail

SLUG="${1:?uso: jw-nova-melhoria.sh <slug-curto-da-melhoria>}"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

if [ "$(git rev-parse --abbrev-ref HEAD)" = "main" ]; then
  echo "ERRO: rode este script do clone principal, não do worktree main de integração." >&2
  exit 1
fi

echo ">> buscando upstream..."
git fetch upstream --tags

# feat/* nasce LIMPO de upstream/main — sem tocar/resetar o main local (que e o
# branch de integracao downstream e nao pode ser sobrescrito pelo upstream).
echo ">> criando branch feat/$SLUG a partir de upstream/main (limpo)..."
git checkout -b "feat/$SLUG" upstream/main

cat <<EOF

OK. Branch 'feat/$SLUG' criada limpa a partir de upstream/main.

Próximos passos:
  1. Implemente a melhoria.
  2. scripts/jw-enviar-melhoria.sh "$SLUG" "<título da melhoria>"
     (roda gates, push no fork, abre issue+PR upstream, integra no main e atualiza o ledger)
EOF
