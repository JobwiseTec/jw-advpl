"""Testes end-to-end — requer FairCom + .dtc fixture em tests/fixtures/.

Pulados se a fixture não existir. Marcados como `e2e`, NÃO rodam no CI por padrão
(rode com `pytest -m e2e`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytestmark = pytest.mark.e2e

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures"


def _find_fixture() -> Path | None:
    for ext in ("*.dtc", "*.DTC"):
        for f in FIXTURE_DIR.glob(ext):
            return f
    return None


@pytest.fixture
def sample_dtc(faircom_required: None) -> Path:
    fixture = _find_fixture()
    if fixture is None:
        pytest.skip(
            f"Sem fixture .dtc em {FIXTURE_DIR}. "
            "Adicione um arquivo (ex: SAMPLE01.dtc) pra rodar e2e."
        )
    return fixture


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_info_command_against_real_dtc(sample_dtc: Path, runner: CliRunner) -> None:
    from plugadvpl.dtc.cli import app

    result = runner.invoke(app, ["info", str(sample_dtc)])
    assert result.exit_code == 0, result.stdout
    assert "Registros:" in result.stdout
    assert "Schema" in result.stdout


def test_export_csv_creates_valid_file(sample_dtc: Path, runner: CliRunner, tmp_path: Path) -> None:
    from plugadvpl.dtc.cli import app

    destino = tmp_path / "out.csv"
    result = runner.invoke(app, ["export", str(sample_dtc), "-f", "csv", "-o", str(destino)])
    assert result.exit_code == 0, result.stdout
    assert destino.exists()
    content = destino.read_text(encoding="utf-8-sig")
    assert "," in content  # CSV não vazio
    assert len(content.splitlines()) >= 2  # header + ≥1 row


def test_export_json_creates_valid_file(
    sample_dtc: Path, runner: CliRunner, tmp_path: Path
) -> None:
    from plugadvpl.dtc.cli import app

    destino = tmp_path / "out.json"
    result = runner.invoke(app, ["export", str(sample_dtc), "-f", "json", "-o", str(destino)])
    assert result.exit_code == 0
    data = json.loads(destino.read_text(encoding="utf-8"))
    assert isinstance(data, list)


def test_export_xlsx_creates_valid_file(
    sample_dtc: Path, runner: CliRunner, tmp_path: Path
) -> None:
    from plugadvpl.dtc.cli import app

    destino = tmp_path / "out.xlsx"
    result = runner.invoke(app, ["export", str(sample_dtc), "-f", "xlsx", "-o", str(destino)])
    assert result.exit_code == 0
    assert destino.exists()
    assert destino.stat().st_size > 0


def test_batch_processes_fixtures_folder(runner: CliRunner, tmp_path: Path) -> None:
    from plugadvpl.dtc.cli import app

    fixture = _find_fixture()
    if fixture is None:
        pytest.skip("Sem fixture .dtc")

    out = tmp_path / "out"
    result = runner.invoke(app, ["batch", str(FIXTURE_DIR), "-f", "csv", "-o", str(out)])
    assert result.exit_code == 0
    assert any(out.iterdir())
