"""Testes da camada CLI (typer)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from plugadvpl.dtc import __version__
from plugadvpl.dtc.cli import app
from plugadvpl.dtc.exporter import ExportFormat


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestVersion:
    def test_version_short_flag(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["-V"])
        assert result.exit_code == 0
        assert __version__ in result.stdout

    def test_version_long_flag(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.stdout


class TestHelp:
    def test_top_level_help_lists_commands(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for cmd in ("doctor", "info", "export", "batch", "server"):
            assert cmd in result.stdout

    def test_server_subcommand_help(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["server", "--help"])
        assert result.exit_code == 0
        for cmd in ("start", "stop", "status"):
            assert cmd in result.stdout

    def test_no_args_shows_help(self, runner: CliRunner) -> None:
        result = runner.invoke(app, [])
        assert result.exit_code != 0  # typer exits non-zero quando no_args_is_help


class TestDoctor:
    def test_doctor_runs_and_returns_exit_code(self, runner: CliRunner, no_faircom: None) -> None:
        result = runner.invoke(app, ["doctor"])
        # v0.4.0: sem FairCom o doctor passa (leitura via parser nativo) → exit 0.
        assert result.exit_code == 0
        assert "Check" in result.stdout
        assert "opcional" in result.stdout  # FairCom listado como opcional

    def test_doctor_passes_when_env_complete(
        self, runner: CliRunner, fake_faircom_home: Path
    ) -> None:
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "FAIL" not in result.stdout


class TestInfoCommand:
    def test_info_missing_file_exits(self, runner: CliRunner, tmp_path: Path) -> None:
        missing = tmp_path / "nao_existe.dtc"
        result = runner.invoke(app, ["info", str(missing)])
        assert result.exit_code == 1

    def test_info_calls_reader(self, runner: CliRunner, tmp_path: Path, mocker) -> None:
        arquivo = tmp_path / "SAMPLE01.dtc"
        arquivo.write_bytes(b"\x00" * 16)
        spy = mocker.patch("plugadvpl.dtc.cli.read_info")
        result = runner.invoke(app, ["info", str(arquivo), "--sample", "3"])
        assert result.exit_code == 0
        spy.assert_called_once()
        assert spy.call_args.kwargs["sample"] == 3


class TestExportCommand:
    def test_export_default_format_is_csv(self, runner: CliRunner, tmp_path: Path, mocker) -> None:
        arquivo = tmp_path / "SAMPLE.dtc"
        arquivo.write_bytes(b"\x00")
        spy = mocker.patch("plugadvpl.dtc.cli.export_file")
        result = runner.invoke(app, ["export", str(arquivo)])
        assert result.exit_code == 0
        assert spy.call_args.kwargs["fmt"] == ExportFormat.csv

    def test_export_explicit_format(self, runner: CliRunner, tmp_path: Path, mocker) -> None:
        arquivo = tmp_path / "SAMPLE.dtc"
        arquivo.write_bytes(b"\x00")
        spy = mocker.patch("plugadvpl.dtc.cli.export_file")
        result = runner.invoke(app, ["export", str(arquivo), "-f", "json"])
        assert result.exit_code == 0
        assert spy.call_args.kwargs["fmt"] == ExportFormat.json

    def test_export_invalid_format_rejected(self, runner: CliRunner, tmp_path: Path) -> None:
        arquivo = tmp_path / "SAMPLE.dtc"
        arquivo.write_bytes(b"\x00")
        result = runner.invoke(app, ["export", str(arquivo), "-f", "yaml"])
        assert result.exit_code != 0

    def test_export_keep_deleted_flag(self, runner: CliRunner, tmp_path: Path, mocker) -> None:
        arquivo = tmp_path / "SAMPLE.dtc"
        arquivo.write_bytes(b"\x00")
        spy = mocker.patch("plugadvpl.dtc.cli.export_file")
        result = runner.invoke(app, ["export", str(arquivo), "--keep-deleted"])
        assert result.exit_code == 0
        assert spy.call_args.kwargs["keep_deleted"] is True


class TestBatchCommand:
    def test_batch_missing_folder(self, runner: CliRunner, tmp_path: Path) -> None:
        missing = tmp_path / "nao_existe"
        result = runner.invoke(app, ["batch", str(missing)])
        assert result.exit_code == 1

    def test_batch_empty_folder(self, runner: CliRunner, tmp_path: Path) -> None:
        result = runner.invoke(app, ["batch", str(tmp_path)])
        assert result.exit_code == 1
        assert "Nenhum .dtc" in result.stdout

    def test_batch_processes_each_file(self, runner: CliRunner, tmp_path: Path, mocker) -> None:
        for name in ["A.dtc", "B.dtc", "C.DTC"]:
            (tmp_path / name).write_bytes(b"\x00")
        out = tmp_path / "out"
        spy = mocker.patch("plugadvpl.dtc.cli.export_file")
        result = runner.invoke(app, ["batch", str(tmp_path), "-o", str(out)])
        assert result.exit_code == 0
        assert spy.call_count == 3
        assert out.is_dir()
