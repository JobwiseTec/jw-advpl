"""Integration tests do subcomando ``gera-script`` (typer CliRunner)."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

from plugadvpl.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_example_imprime_json_valido(runner: CliRunner) -> None:
    r = runner.invoke(app, ["gera-script", "--example"])
    assert r.exit_code == 0
    cfg = json.loads(r.stdout)
    assert cfg["PROTHEUS_PASSWORD_ENV"] == "PROTHEUS_PASS"
    assert cfg["BASE_DIR_PATCHES"].startswith("<")


def test_schema_imprime_chaves(runner: CliRunner) -> None:
    r = runner.invoke(app, ["gera-script", "--schema"])
    assert r.exit_code == 0
    keys = {f["key"] for f in json.loads(r.stdout)}
    assert {"PROTHEUS_SERVER", "BUILD_DIR", "PROTHEUS_PASSWORD"} <= keys


def test_both_gera_os_3_artefatos(runner: CliRunner, tmp_path: Path) -> None:
    out = tmp_path / "deploy"
    r = runner.invoke(app, ["gera-script", "--shell", "both", "--out", str(out)])
    assert r.exit_code == 0, r.stdout
    assert (out / "patch_e_compilacao.ps1").is_file()
    assert (out / "patch_e_compilacao.sh").is_file()
    assert (out / "patch_e_compilacao_config.json").is_file()


def test_shell_ps1_nao_gera_sh(runner: CliRunner, tmp_path: Path) -> None:
    r = runner.invoke(app, ["gera-script", "--shell", "ps1", "--out", str(tmp_path)])
    assert r.exit_code == 0
    assert (tmp_path / "patch_e_compilacao.ps1").is_file()
    assert not (tmp_path / "patch_e_compilacao.sh").exists()


@pytest.mark.skipif(os.name == "nt", reason="bits de exec sao POSIX")
def test_sh_gerado_e_executavel(runner: CliRunner, tmp_path: Path) -> None:
    runner.invoke(app, ["gera-script", "--shell", "sh", "--out", str(tmp_path)])
    sh = tmp_path / "patch_e_compilacao.sh"
    assert sh.read_text().startswith("#!/usr/bin/env bash")
    assert sh.stat().st_mode & stat.S_IXUSR


def test_secret_config_poe_senha_placeholder(runner: CliRunner, tmp_path: Path) -> None:
    runner.invoke(app, ["gera-script", "--shell", "sh", "--secret", "config", "--out", str(tmp_path)])
    cfg = json.loads((tmp_path / "patch_e_compilacao_config.json").read_text())
    assert cfg["PROTHEUS_PASSWORD"] == "<SENHA_COMPILACAO>"
    assert "PROTHEUS_PASSWORD_ENV" not in cfg


def test_nao_sobrescreve_sem_force(runner: CliRunner, tmp_path: Path) -> None:
    a = ["gera-script", "--shell", "sh", "--out", str(tmp_path)]
    assert runner.invoke(app, a).exit_code == 0
    r2 = runner.invoke(app, a)
    assert r2.exit_code == 2
    assert "force" in r2.output.lower()
    assert runner.invoke(app, [*a, "--force"]).exit_code == 0


def test_shell_invalido_exit2(runner: CliRunner, tmp_path: Path) -> None:
    r = runner.invoke(app, ["gera-script", "--shell", "banana", "--out", str(tmp_path)])
    assert r.exit_code == 2


def test_use_server_inexistente_exit2(runner: CliRunner, tmp_path: Path) -> None:
    r = runner.invoke(
        app, ["gera-script", "--use-server", "nao_existe_zzz", "--out", str(tmp_path)]
    )
    assert r.exit_code == 2


def test_aviso_placeholder_e_envvar_sem_server(runner: CliRunner, tmp_path: Path) -> None:
    r = runner.invoke(app, ["gera-script", "--shell", "sh", "--out", str(tmp_path)])
    assert r.exit_code == 0
    assert "PROTHEUS_PASS" in r.output  # lembrete da env var


def test_tq_inclui_fase_e_chaves(runner: CliRunner, tmp_path: Path) -> None:
    r = runner.invoke(app, ["gera-script", "--shell", "both", "--tq", "--out", str(tmp_path)])
    assert r.exit_code == 0, r.output
    cfg = json.loads((tmp_path / "patch_e_compilacao_config.json").read_text())
    assert {"TQ_DEST_APO", "TQ_CMP_RPO", "TQ_DEST_BIN", "TQ_RPO_FILES"} <= set(cfg)
    assert "ETAPA 3: TROCA QUENTE" in (tmp_path / "patch_e_compilacao.sh").read_text()
    assert "ETAPA 3: TROCA QUENTE" in (tmp_path / "patch_e_compilacao.ps1").read_text()


def test_sem_tq_nao_inclui_fase(runner: CliRunner, tmp_path: Path) -> None:
    r = runner.invoke(app, ["gera-script", "--shell", "sh", "--out", str(tmp_path)])
    assert r.exit_code == 0
    cfg = json.loads((tmp_path / "patch_e_compilacao_config.json").read_text())
    assert not any(k.startswith("TQ_") for k in cfg)
    assert "TROCA QUENTE" not in (tmp_path / "patch_e_compilacao.sh").read_text()


def test_example_tq_mostra_chaves(runner: CliRunner) -> None:
    r = runner.invoke(app, ["gera-script", "--tq", "--example"])
    assert r.exit_code == 0
    assert "TQ_DEST_APO" in r.stdout
