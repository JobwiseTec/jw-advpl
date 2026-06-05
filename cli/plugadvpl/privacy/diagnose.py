"""Motor de relativização (``diagnose``) — passos 3+4.

Dado o **fonte** (de onde extraímos as decisões) e um **registro** (valores reais
de campos/variáveis), avalia o **desfecho EXATO** de cada comparação localmente —
sobre os valores reais — e **relativiza** os operandos sensíveis na explicação:
mostra ``saldo ~103% de limite -> VERDADEIRO`` em vez do R$ real.

Garantia de precisão: o *outcome* (VERDADEIRO/FALSO) é computado por aritmética
exata e determinística sobre os valores reais; só a **exibição** dos números
sensíveis vira razão/faixa. Operando não-resolvível -> ``outcome = None`` (não
chuta). Mesmo (fonte, registro) -> mesma saída, sempre.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from plugadvpl.parsing.decisions import extract_decisions

from .buckets import bucket, is_financial_field

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from plugadvpl.parsing.decisions import Comparison

_ALIAS_RE = re.compile(r"^\s*\w+->")
_GETMV_RE = re.compile(r'(?i)(?:super)?getmv\s*\(\s*["\'](MV_\w+)["\']')
_ORDER_OPS = frozenset({">", "<", ">=", "<="})
_RES = {True: "VERDADEIRO", False: "FALSO", None: "(nao avaliavel)"}
_PAIR_LEN = 2  # mínimo p/ ter par de aspas ("x")
_BINOPS: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
}
_NUM_OPS: dict[str, Callable[[float, float], bool]] = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
}


@dataclass(frozen=True)
class ComparisonEval:
    """Avaliação de uma comparação: desfecho exato + explicação relativizada."""

    comparison: Comparison
    outcome: bool | None
    explain: str


@dataclass(frozen=True)
class DecisionEval:
    """Um ponto de decisão avaliado contra o registro."""

    line: int
    condition: str
    comparisons: tuple[ComparisonEval, ...]


# --------------------------------------------------------------------------
# resolução de valores
# --------------------------------------------------------------------------


def _strv(value: object) -> str:
    """String normalizada: remove aspas externas e espaços das pontas."""
    text = str(value).strip()
    quoted = len(text) >= _PAIR_LEN and text[0] in "\"'" and text[-1] == text[0]
    return text[1:-1] if quoted else text


def _num(value: object) -> float | None:
    """Converte para float (sem tratar bool como número; aceita pt-BR ``1.234,56``)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        text = _strv(value)
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _record_value(record: Mapping[str, object], name: str) -> object | None:
    if name in record:
        return record[name]
    upper = name.upper()
    for key, val in record.items():
        if key.upper() == upper:
            return val
    return None


def _clean_name(token: str) -> str:
    return _ALIAS_RE.sub("", token.strip())


def _eval_binop(node: ast.BinOp, record: Mapping[str, object]) -> float | None:
    left = _eval_node(node.left, record)
    right = _eval_node(node.right, record)
    if left is None or right is None:
        return None
    fn = _BINOPS.get(type(node.op))
    if fn is not None:
        return fn(left, right)
    if isinstance(node.op, ast.Div) and right != 0:
        return left / right
    return None


def _eval_node(node: ast.expr, record: Mapping[str, object]) -> float | None:
    if isinstance(node, ast.Constant):
        return float(node.value) if isinstance(node.value, int | float) else None
    if isinstance(node, ast.Name):
        return _num(_record_value(record, node.id))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        inner = _eval_node(node.operand, record)
        return None if inner is None else -inner
    if isinstance(node, ast.BinOp):
        return _eval_binop(node, record)
    return None


def _eval_expr(expr: str, record: Mapping[str, object]) -> float | None:
    norm = re.sub(r"\b\w+->", "", expr)  # tira alias (SA1->A1_LC -> A1_LC)
    try:
        tree = ast.parse(norm, mode="eval")
    except SyntaxError:
        return None
    return _eval_node(tree.body, record)


def _resolve(token: str, kind: str, record: Mapping[str, object]) -> object | None:
    if kind == "literal":
        num = _num(token)
        return num if num is not None else _strv(token)
    if kind == "const":
        upper = token.strip().upper()
        return True if upper == ".T." else False if upper == ".F." else None
    if kind in ("field", "var"):
        return _record_value(record, _clean_name(token))
    if kind == "expr":
        return _eval_expr(token, record)
    if kind == "call":
        mv = _GETMV_RE.search(token)
        return _record_value(record, mv.group(1)) if mv else None
    return None


# --------------------------------------------------------------------------
# comparação exata
# --------------------------------------------------------------------------


def _eq(left: object, right: object) -> bool:
    ln, rn = _num(left), _num(right)
    if ln is not None and rn is not None:
        return ln == rn
    return _strv(left) == _strv(right)


def _compare(left: object, op: str, right: object) -> bool | None:
    if left is None or right is None:
        return None
    if op in ("==", "="):
        return _eq(left, right)
    if op in ("!=", "<>"):
        return not _eq(left, right)
    if op == "$":
        return _strv(left) in _strv(right)
    fn = _NUM_OPS.get(op)
    ln, rn = _num(left), _num(right)
    if fn is None or ln is None or rn is None:
        return None
    return fn(ln, rn)


# --------------------------------------------------------------------------
# relativização (exibição)
# --------------------------------------------------------------------------


def _is_fin(token: str, kind: str, financial: frozenset[str]) -> bool:
    if kind not in ("field", "var", "expr"):
        return False
    if kind == "expr":
        return any(
            is_financial_field(ident, financial)
            for ident in re.findall(r"[A-Za-z]\w*", _clean_name(token))
        )
    return is_financial_field(_clean_name(token), financial)


def _side(token: str, kind: str, value: object, fin: bool) -> str:
    if kind == "literal":
        return _strv(token)
    name = _clean_name(token)
    if value is None:
        return name
    num = _num(value)
    if fin and num is not None:
        return f"{name}(~{bucket(num)})"
    return f"{name}={_strv(value)}"


def _explain(
    comp: Comparison,
    lval: object,
    rval: object,
    outcome: bool | None,
    financial: frozenset[str],
) -> str:
    res = _RES[outcome]
    lfin = _is_fin(comp.left, comp.left_kind, financial)
    rfin = _is_fin(comp.right, comp.right_kind, financial)
    ln, rn = _num(lval), _num(rval)
    if comp.op in _ORDER_OPS and ln is not None and rn is not None and (lfin or rfin):
        lname, rname = _clean_name(comp.left), _clean_name(comp.right)
        if rn != 0:
            return f"{lname} ~{round(ln / rn * 100)}% de {rname} -> {res}"
        return f"{lname} {comp.op} {rname}(zero) -> {res}"
    left_repr = _side(comp.left, comp.left_kind, lval, lfin)
    right_repr = _side(comp.right, comp.right_kind, rval, rfin)
    return f"{left_repr} {comp.op} {right_repr} -> {res}"


def _eval_comparison(
    comp: Comparison, record: Mapping[str, object], financial: frozenset[str]
) -> ComparisonEval:
    lval = _resolve(comp.left, comp.left_kind, record)
    rval = _resolve(comp.right, comp.right_kind, record)
    outcome = _compare(lval, comp.op, rval)
    return ComparisonEval(comp, outcome, _explain(comp, lval, rval, outcome, financial))


def diagnose(
    source: str,
    record: Mapping[str, object],
    *,
    financial_fields: frozenset[str] = frozenset(),
) -> list[DecisionEval]:
    """Avalia os pontos de decisão de ``source`` contra ``record`` (determinístico).

    Cada comparação recebe o **desfecho exato** (sobre os valores reais) e uma
    **explicação relativizada** (números sensíveis viram razão/faixa).
    """
    out: list[DecisionEval] = []
    for decision in extract_decisions(source):
        evals = tuple(_eval_comparison(c, record, financial_fields) for c in decision.comparisons)
        out.append(DecisionEval(decision.line, decision.condition, evals))
    return out
