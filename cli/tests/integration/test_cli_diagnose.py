"""Teste de CLI do comando ``diagnose`` — relativização end-to-end."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from plugadvpl.cli import app

if TYPE_CHECKING:
    from pathlib import Path

ROUTINE = '''#include "protheus.ch"

User Function ABCLibPed( cCli, cLoja, nValPed )
    If SA1->A1_MSBLQL == "1"
        Return "BLOQUEADO"
    EndIf
    If ( nSaldo + nValPed ) > SA1->A1_LC
        Return "BLOQUEADO"
    EndIf
Return "LIBERADO"
'''


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def _setup(tmp_path: Path) -> Path:
    (tmp_path / "ABCLibPed.prw").write_text(ROUTINE, encoding="cp1252")
    rec = tmp_path / "rec.json"
    rec.write_text(
        '{"A1_MSBLQL": "2", "nSaldo": 21500, "nValPed": 30000, "A1_LC": 50000}',
        encoding="utf-8",
    )
    return rec


class TestDiagnoseCLI:
    def test_trace_relativizado(self, tmp_path: Path, runner: CliRunner) -> None:
        rec = _setup(tmp_path)
        result = runner.invoke(
            app,
            ["--root", str(tmp_path), "--format", "md", "diagnose", "ABCLibPed.prw",
             "--record-file", str(rec)],
        )
        assert result.exit_code == 0, result.output
        assert "103%" in result.output  # razão relativizada
        assert "VERDADEIRO" in result.output  # estourou o limite
        assert "FALSO" in result.output  # bloqueio manual não
        assert "51500" not in result.output  # valor real NÃO vaza
        assert "50000" not in result.output

    def test_record_inline_bloqueio_manual(self, tmp_path: Path, runner: CliRunner) -> None:
        _setup(tmp_path)
        result = runner.invoke(
            app,
            ["--root", str(tmp_path), "--format", "json", "diagnose", "ABCLibPed.prw",
             "--record", '{"A1_MSBLQL": "1"}'],
        )
        assert result.exit_code == 0, result.output
        assert "VERDADEIRO" in result.output  # A1_MSBLQL=1 -> bloqueio manual

    def test_fonte_inexistente(self, tmp_path: Path, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--root", str(tmp_path), "diagnose", "NAOEXISTE.prw"])
        assert result.exit_code == 1

    def test_json_invalido(self, tmp_path: Path, runner: CliRunner) -> None:
        _setup(tmp_path)
        result = runner.invoke(
            app, ["--root", str(tmp_path), "diagnose", "ABCLibPed.prw", "--record", "{bad"]
        )
        assert result.exit_code == 2
