"""Extração DETERMINÍSTICA de pontos de decisão (``If``/``ElseIf``/``While``) de
fonte ADVPL/TLPP — primeiro passo da relativização (comando ``diagnose``).

Objetivo: saber QUAIS campos/operandos são comparados e com QUAL operador em cada
branch, **sem precisar do valor do registro**. Função pura: mesmo fonte → mesma
saída, sempre (sem randomness, sem estado). Isso é o que permite, depois, computar
o desfecho exato de cada comparação e relativizar (``saldo 103% > limite: TRUE``)
sem dar errado.

Limites honestos (v1): trata as formas de statement (``If``/``ElseIf``/``While``);
não desmonta expressões aninhadas complexas — operandos compostos viram ``expr``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Statement de decisão no início da linha (após espaços).
_DECISION_RE = re.compile(r"^\s*(else\s*if|elseif|if|while)\b(.*)$", re.IGNORECASE)

# Operadores de comparação — ordem importa: multi-char antes de single-char.
_OPERATORS = ("==", "!=", "<>", ">=", "<=", "=", ">", "<", "$")

_ALIAS_RE = re.compile(r"^\s*\w+->")  # remove "SA1->" / "M->"
_FIELD_RE = re.compile(r"^[A-Z][0-9A-Z]{1,2}_[0-9A-Z]+$")
_STR_RE = re.compile(r"""^(".*"|'.*')$""")
_NUM_RE = re.compile(r"^[-+]?\d+(\.\d+)?$")
_CALL_RE = re.compile(r"^\w+\s*\(")
_CONST = frozenset({".T.", ".F.", "NIL"})
_EXPR_CHARS = frozenset("+-*/ ")


@dataclass(frozen=True)
class Comparison:
    """Uma comparação ``left <op> right`` extraída de uma condição."""

    left: str
    op: str
    right: str
    left_kind: str  # field | var | literal | call | const | expr
    right_kind: str


@dataclass(frozen=True)
class Decision:
    """Um ponto de decisão (statement) e suas comparações de topo."""

    line: int
    kind: str  # if | elseif | while
    condition: str
    comparisons: tuple[Comparison, ...]


def _strip_comment(text: str) -> str:
    """Remove comentário ``//...`` fora de string. Determinístico."""
    in_str: str | None = None
    for i, ch in enumerate(text):
        if in_str:
            if ch == in_str:
                in_str = None
        elif ch in ('"', "'"):
            in_str = ch
        elif ch == "/" and i + 1 < len(text) and text[i + 1] == "/":
            return text[:i]
    return text


def _classify(token: str) -> str:
    """Classifica um operando: field | literal | const | call | expr | var."""
    norm = _ALIAS_RE.sub("", token.strip())
    upper = norm.upper()
    if _FIELD_RE.match(upper):
        return "field"
    if _STR_RE.match(norm) or _NUM_RE.match(norm):
        return "literal"
    if upper in _CONST:
        return "const"
    if _CALL_RE.match(norm):
        return "call"
    if norm.startswith("(") or any(c in norm for c in _EXPR_CHARS):
        return "expr"
    return "var"


def _split_top_level(cond: str) -> list[str]:
    """Divide a condição nos ``.And.``/``.Or.`` de nível 0 (respeita parênteses)."""
    clauses: list[str] = []
    depth = 0
    start = 0
    i = 0
    low = cond.lower()
    while i < len(cond):
        ch = cond[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and (low.startswith(".and.", i) or low.startswith(".or.", i)):
            clauses.append(cond[start:i])
            i += 5 if low.startswith(".and.", i) else 4
            start = i
            continue
        i += 1
    clauses.append(cond[start:])
    return [c.strip() for c in clauses if c.strip()]


def _find_op(clause: str) -> tuple[int, str] | None:
    """Acha o operador de comparação de nível 0 (fora de parênteses/string)."""
    depth = 0
    in_str: str | None = None
    i = 0
    while i < len(clause):
        ch = clause[i]
        if in_str:
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ('"', "'"):
            in_str = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            if clause.startswith("->", i):  # alias ADVPL (SA1->A1_LC) — não é operador
                i += 2
                continue
            for op in _OPERATORS:
                if clause.startswith(op, i):
                    return i, op
        i += 1
    return None


def _parse_comparison(clause: str) -> Comparison | None:
    """Extrai ``left <op> right`` de uma cláusula, ou ``None`` se não houver."""
    inner = clause.strip()
    while inner.startswith("(") and inner.endswith(")") and _find_op(inner[1:-1]) is not None:
        inner = inner[1:-1].strip()
    found = _find_op(inner)
    if found is None:
        return None
    pos, op = found
    left = inner[:pos].strip()
    right = inner[pos + len(op) :].strip()
    if not left or not right:
        return None
    return Comparison(left, op, right, _classify(left), _classify(right))


def extract_decisions(source: str) -> list[Decision]:
    """Extrai os pontos de decisão de ``source`` (determinístico)."""
    out: list[Decision] = []
    for idx, raw in enumerate(source.splitlines(), start=1):
        match = _DECISION_RE.match(raw)
        if not match:
            continue
        kw = match.group(1).lower().replace(" ", "")
        kind = "elseif" if kw in ("elseif",) else kw
        cond = _strip_comment(match.group(2)).strip()
        if not cond:
            continue
        comps = tuple(
            c for c in (_parse_comparison(cl) for cl in _split_top_level(cond)) if c is not None
        )
        out.append(Decision(line=idx, kind=kind, condition=cond, comparisons=comps))
    return out
