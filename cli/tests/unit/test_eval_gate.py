"""Fase 2 do roadmap-ia — gate de regressão do eval (Camada A, roda no CI).

Carrega o seed golden, roda contra um índice-fixture com os símbolos esperados
e trava se faithfulness/pass_rate caírem abaixo do baseline commitado.
Determinístico, $0 (sem LLM).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from plugadvpl.db import apply_migrations, open_db, seed_lookups
from plugadvpl.eval_harness import compare_baseline, load_golden, run_eval

_EVAL_DIR = Path(__file__).parents[1] / "eval"
_GOLDEN = _EVAL_DIR / "golden" / "seed.json"
_BASELINE = _EVAL_DIR / "baseline.json"


@pytest.fixture
def gate_index(tmp_path: Path) -> sqlite3.Connection:
    """Índice-fixture com os símbolos que o seed golden referencia."""
    c = open_db(tmp_path / "idx.db")
    apply_migrations(c)
    seed_lookups(c)
    # nativas que o seed afirma existir
    c.executemany(
        "INSERT INTO funcoes_nativas (nome, categoria) VALUES (?, 'mvc')",
        [("FWModelEvent",), ("InstallEvent",)],
    )
    # campo customer afirmado
    c.execute(
        "INSERT INTO campos (tabela, campo, custom, proprietario) "
        "VALUES ('ZX1', 'ZX1_STATUS', 1, 'U')"
    )
    c.commit()
    return c


def test_seed_golden_passes_against_correct_index(gate_index: sqlite3.Connection) -> None:
    cases = load_golden(_GOLDEN)
    assert cases, "seed golden vazio"
    scorecard = run_eval(gate_index, cases)
    # Num índice correto o seed deve passar 100% (faithfulness + sem armadilhas).
    assert scorecard["totals"]["faithfulness_avg"] == 1.0
    assert scorecard["totals"]["pass_rate"] == 1.0


def test_seed_meets_committed_baseline(gate_index: sqlite3.Connection) -> None:
    cases = load_golden(_GOLDEN)
    scorecard = run_eval(gate_index, cases)
    baseline = json.loads(_BASELINE.read_text(encoding="utf-8"))
    regressions = compare_baseline(scorecard, baseline)
    assert regressions == [], f"regressão no eval: {regressions}"
