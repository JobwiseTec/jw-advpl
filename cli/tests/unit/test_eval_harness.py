"""Fase 2 do roadmap-ia — eval harness (Camada A determinística, $0).

Ver docs/roadmap-ia/02-eval-harness.md. Scorer de faithfulness reusa o
verify_claims da Fase 1; nenhum LLM nesta camada.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from plugadvpl.db import apply_migrations, open_db, seed_lookups


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = open_db(tmp_path / "idx.db")
    apply_migrations(c)
    seed_lookups(c)
    c.execute("INSERT INTO fontes (arquivo, caminho_relativo) VALUES ('a.prw', 'a.prw')")
    c.execute(
        "INSERT INTO fonte_chunks (id, arquivo, funcao, funcao_norm, tipo_simbolo) "
        "VALUES ('a.prw::ZMYFUNC', 'a.prw', 'ZMYFUNC', 'ZMYFUNC', 'user_function')"
    )
    c.execute("INSERT INTO funcoes_nativas (nome, categoria) VALUES ('FWModelEvent', 'mvc')")
    c.commit()
    return c


def _case(**kw: object) -> dict[str, object]:
    base: dict[str, object] = {"id": "x", "category": "c", "question": "q", "claims": []}
    base.update(kw)
    return base


class TestLoadGolden:
    def test_loads_list_of_cases(self, tmp_path: Path) -> None:
        from plugadvpl.eval_harness import load_golden

        p = tmp_path / "g.json"
        p.write_text(json.dumps([_case(id="a")]), encoding="utf-8")
        cases = load_golden(p)
        assert len(cases) == 1
        assert cases[0]["id"] == "a"

    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        from plugadvpl.eval_harness import load_golden

        p = tmp_path / "g.json"
        p.write_text(json.dumps([{"id": "a"}]), encoding="utf-8")  # falta question
        with pytest.raises((ValueError, KeyError)):
            load_golden(p)


class TestScoreCase:
    def test_all_claims_exist_is_faithful_and_passes(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.eval_harness import score_case

        case = _case(claims=[
            {"id": "c1", "kind": "function", "symbol": "ZMYFUNC"},
            {"id": "c2", "kind": "function", "symbol": "FWModelEvent"},
        ])
        r = score_case(conn, case)
        assert r["faithfulness"] == 1.0
        assert r["passed"] is True

    def test_hallucinated_claim_lowers_faithfulness_and_fails(
        self, conn: sqlite3.Connection
    ) -> None:
        from plugadvpl.eval_harness import score_case

        case = _case(claims=[
            {"id": "c1", "kind": "function", "symbol": "ZMYFUNC"},
            {"id": "c2", "kind": "function", "symbol": "FWLerExcel"},  # alucinação
        ])
        r = score_case(conn, case)
        assert r["faithfulness"] == 0.5
        assert r["passed"] is False

    def test_no_claims_is_faithful(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.eval_harness import score_case

        r = score_case(conn, _case(claims=[]))
        assert r["faithfulness"] == 1.0

    def test_trap_string_present_fails(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.eval_harness import score_case

        case = _case(
            answer="Use bCommit para gravar",
            must_not_mention=["bCommit"],
        )
        r = score_case(conn, case)
        assert r["traps_ok"] is False
        assert r["passed"] is False

    def test_trap_string_absent_ok(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.eval_harness import score_case

        case = _case(answer="Use FWModelEvent", must_not_mention=["bCommit"])
        r = score_case(conn, case)
        assert r["traps_ok"] is True


class TestRunEvalAndBaseline:
    def test_run_eval_aggregates_by_category(self, conn: sqlite3.Connection) -> None:
        from plugadvpl.eval_harness import run_eval

        cases = [
            _case(id="a", category="mvc",
                  claims=[{"id": "c1", "kind": "function", "symbol": "ZMYFUNC"}]),
            _case(id="b", category="mvc",
                  claims=[{"id": "c1", "kind": "function", "symbol": "FWLerExcel"}]),
        ]
        sc = run_eval(conn, cases)
        assert sc["by_category"]["mvc"]["total"] == 2
        assert sc["by_category"]["mvc"]["passed"] == 1
        assert sc["totals"]["total"] == 2

    def test_compare_baseline_detects_faithfulness_regression(self) -> None:
        from plugadvpl.eval_harness import compare_baseline

        baseline = {"totals": {"faithfulness_avg": 1.0, "pass_rate": 1.0}}
        worse = {"totals": {"faithfulness_avg": 0.8, "pass_rate": 0.9}}
        regressions = compare_baseline(worse, baseline)
        assert regressions  # não vazio = regressão

    def test_compare_baseline_no_regression_when_equal_or_better(self) -> None:
        from plugadvpl.eval_harness import compare_baseline

        baseline = {"totals": {"faithfulness_avg": 0.9, "pass_rate": 0.9}}
        same = {"totals": {"faithfulness_avg": 0.9, "pass_rate": 0.95}}
        assert compare_baseline(same, baseline) == []
