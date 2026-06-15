"""Fase 2 do roadmap-ia — eval harness (Camada A determinística, custo $0).

Mede a qualidade de forma reprodutível, sem LLM: ``faithfulness`` de símbolo
(reusa o ``verify_claims`` da Fase 1) + armadilhas de alucinação
(``must_not_mention``). É o gate de regressão. Camada B (resposta do agente +
juiz LLM) é opt-in/offline e mora fora daqui.

Ver docs/roadmap-ia/02-eval-harness.md. Golden set em JSON (zero dependência
nova, vs YAML).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .verify import verify_claims

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path
    from typing import Any

_REQUIRED_FIELDS = ("id", "category", "question")
_HIT_STATUS = ("exists", "relation_holds")


def load_golden(path: Path) -> list[dict[str, Any]]:
    """Carrega e valida um golden set (lista de casos JSON)."""
    cases: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    for case in cases:
        for field in _REQUIRED_FIELDS:
            if field not in case:
                raise ValueError(f"golden case sem campo obrigatório '{field}': {case!r}")
    return cases


def score_case(conn: sqlite3.Connection, case: dict[str, Any]) -> dict[str, Any]:
    """Pontua um caso: faithfulness de símbolo + armadilhas. Tudo determinístico."""
    claims = case.get("claims") or []
    if claims:
        verdict = verify_claims(conn, claims)
        hits = sum(1 for r in verdict["results"] if r["status"] in _HIT_STATUS)
        faithfulness = hits / len(claims)
    else:
        faithfulness = 1.0

    answer = str(case.get("answer", ""))
    traps = case.get("must_not_mention") or []
    traps_ok = not any(str(t) in answer for t in traps)

    return {
        "id": case.get("id", ""),
        "category": case.get("category", ""),
        "faithfulness": faithfulness,
        "traps_ok": traps_ok,
        "passed": faithfulness == 1.0 and traps_ok,
    }


def run_eval(conn: sqlite3.Connection, cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Roda o eval sobre todos os casos → scorecard (por categoria + totais)."""
    acc: dict[str, dict[str, float]] = {}
    for case in cases:
        r = score_case(conn, case)
        cat = str(r["category"])
        agg = acc.setdefault(cat, {"passed": 0.0, "total": 0.0, "faith_sum": 0.0})
        agg["total"] += 1
        agg["passed"] += 1 if r["passed"] else 0
        agg["faith_sum"] += float(r["faithfulness"])

    by_category: dict[str, Any] = {}
    tot_passed = tot = 0.0
    faith_sum = 0.0
    for cat, agg in acc.items():
        total = agg["total"]
        by_category[cat] = {
            "passed": int(agg["passed"]),
            "total": int(total),
            "faithfulness_avg": agg["faith_sum"] / total if total else 1.0,
        }
        tot_passed += agg["passed"]
        tot += total
        faith_sum += agg["faith_sum"]

    totals = {
        "passed": int(tot_passed),
        "total": int(tot),
        "pass_rate": tot_passed / tot if tot else 1.0,
        "faithfulness_avg": faith_sum / tot if tot else 1.0,
    }
    return {"by_category": by_category, "totals": totals}


def compare_baseline(
    scorecard: dict[str, Any], baseline: dict[str, Any], *, tolerance: float = 1e-9
) -> list[str]:
    """Lista regressões (vazio = ok). Gate trava só na Camada A determinística."""
    regressions: list[str] = []
    bt = baseline.get("totals", {})
    st = scorecard.get("totals", {})
    for metric in ("faithfulness_avg", "pass_rate"):
        base = bt.get(metric)
        cur = st.get(metric)
        if base is not None and cur is not None and cur < base - tolerance:
            regressions.append(f"{metric}: {cur:.3f} < baseline {base:.3f}")
    return regressions
