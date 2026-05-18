"""Universo 4 / Feature B — métricas de qualidade por função.

Extrai:
- **Complexidade ciclomática** (McCabe simplificado): conta paths de decisão
  (`If/ElseIf/While/For/Case/Catch/IIf`). Padrão: ``Else`` não conta.
- **Profundidade de aninhamento** (max depth): stack-based scan de openers
  (`If`/`While`/`For`/`Do Case`/`Try`/`Begin Sequence`/`Begin Transaction`)
  vs closers (`EndIf`/`EndDo`/`Next`/`EndCase`/`End`).

Roda sobre conteúdo já stripado (sem comentários/strings) — usa
:func:`plugadvpl.parsing.stripper.strip_advpl`.

Spec completo: ``docs/universo4/B-qualidade-metricas.md``.
"""
from __future__ import annotations

import re
from typing import Any

from plugadvpl.parsing.stripper import strip_advpl

# Decision keywords pra complexidade ciclomática.
# Else NÃO conta (McCabe — não adiciona path).
# Cada Case dentro de Do Case = +1 (espelha if/elseif).
# `Do Case` em si NÃO conta como Case (lookbehind exclui) — o switch como um
# todo equivale ao base; é cada cláusula Case que adiciona path.
# OtherWise NÃO conta (= else do Do Case).
# Catch +1 por bloco.
# IIf() ternário inline +1.
_CC_DECISION_RE = re.compile(
    r"\b(?:If|ElseIf|While|For|(?<!Do\s)Case|Catch|IIf)\b",
    re.IGNORECASE,
)

# Openers de bloco (aumentam profundidade).
# Multi-word: Do Case / Begin Sequence / Begin Transaction — vão como uma única alternativa.
_OPENER_RE = re.compile(
    r"\b(?:"
    r"If"
    r"|While"
    r"|For"
    r"|Do\s+Case"
    r"|Try"
    r"|Begin\s+Sequence"
    r"|Begin\s+Transaction"
    r")\b",
    re.IGNORECASE,
)

# Closers (diminuem profundidade).
_CLOSER_RE = re.compile(
    r"\b(?:"
    r"EndIf"
    r"|EndDo"
    r"|Next"
    r"|EndCase"
    r"|End\s*Try"
    r"|End\s+Sequence"
    r"|End\s+Transaction"
    r")\b",
    re.IGNORECASE,
)


def compute_cyclomatic_complexity(body: str) -> int:
    """Complexidade ciclomática McCabe simplificada.

    Roda strip primeiro pra ignorar keywords em strings/comments.
    Retorna ``1 + count(matches)`` — base mínima é 1 (função sem ramificação).
    """
    stripped = strip_advpl(body)
    matches = _CC_DECISION_RE.findall(stripped)
    return 1 + len(matches)


def compute_max_nesting(body: str) -> int:
    """Profundidade máxima de aninhamento de blocos.

    Stack-based scan: incrementa depth em opener, decrementa em closer,
    track max ao longo da passada. Retorna 0 pra função sem blocos.
    """
    stripped = strip_advpl(body)
    # Coleta posições de openers e closers, processa em ordem.
    events: list[tuple[int, int]] = []  # (offset, +1/-1)
    for m in _OPENER_RE.finditer(stripped):
        events.append((m.start(), 1))
    for m in _CLOSER_RE.finditer(stripped):
        events.append((m.start(), -1))
    events.sort(key=lambda e: e[0])

    depth = 0
    max_depth = 0
    for _, delta in events:
        depth += delta
        if depth > max_depth:
            max_depth = depth
        if depth < 0:
            # closer sem opener — tolera (código mal-formado não trava)
            depth = 0
    return max_depth


def extract_function_metrics(body: str) -> dict[str, Any]:
    """Agregador: roda CC + nesting + retorna dict combinado."""
    return {
        "cc": compute_cyclomatic_complexity(body),
        "nesting": compute_max_nesting(body),
    }
