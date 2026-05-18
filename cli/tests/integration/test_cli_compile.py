"""Integration tests do subcomando compile (PATH-shim de advpls)."""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from plugadvpl.cli import app


@pytest.fixture
def runner() -> CliRunner:
    # Compatibilidade Click 8.0-8.2: NAO passar mix_stderr (removido em 8.2+).
    # Padrao do projeto em tests/integration/test_cli.py tambem usa sem flag.
    return CliRunner()


@pytest.fixture
def fake_advpls(tmp_path: Path) -> Path:
    """Cria um "binario" `advpls` que finge ser o compilador (cross-platform).

    Retorna o Path do executavel a ser passado via env var
    PLUGADVPL_ADVPLS_BINARY (test hook reconhecido por `_resolve_advpls`).

    Comportamento default: exit 0 sem output. Sobrescreva via env vars:
      SHIM_OUTPUT - texto a imprimir em stdout
      SHIM_EXIT   - codigo de saida (int)
    """
    shim_py = tmp_path / "advpls_shim.py"
    shim_py.write_text(
        'import sys, os\n'
        'output = os.environ.get("SHIM_OUTPUT", "")\n'
        'exit_code = int(os.environ.get("SHIM_EXIT", "0"))\n'
        'sys.stdout.write(output)\n'
        'sys.exit(exit_code)\n',
        encoding="utf-8",
    )
    if os.name == "nt":
        target = tmp_path / "advpls.bat"
        target.write_text(
            f'@echo off\r\n"{sys.executable}" "{shim_py}" %*\r\n',
            encoding="cp1252",
        )
    else:
        target = tmp_path / "advpls"
        target.write_text(
            f'#!{sys.executable}\n'
            f'import sys, runpy\n'
            f'sys.argv = [r"{shim_py}"] + sys.argv[1:]\n'
            f'runpy.run_path(r"{shim_py}", run_name="__main__")\n',
            encoding="utf-8",
        )
        target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return target


class TestInitConfig:
    def test_init_config_creates_template(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        (tmp_path / ".gitignore").write_text("", encoding="utf-8")
        result = runner.invoke(app, ["--root", str(tmp_path), "compile", "--init-config"])
        assert result.exit_code == 0
        assert (tmp_path / ".plugadvpl" / "runtime.toml").is_file()
        gi = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert ".plugadvpl/runtime.toml" in gi

    def test_init_config_refuses_overwrite(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        (tmp_path / ".plugadvpl").mkdir()
        (tmp_path / ".plugadvpl" / "runtime.toml").write_text("existing", encoding="utf-8")
        result = runner.invoke(app, ["--root", str(tmp_path), "compile", "--init-config"])
        assert result.exit_code == 1

    def test_init_config_force_overwrites(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        (tmp_path / ".plugadvpl").mkdir()
        (tmp_path / ".plugadvpl" / "runtime.toml").write_text("existing", encoding="utf-8")
        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile", "--init-config", "--force"]
        )
        assert result.exit_code == 0
        # Conteudo agora e o template, nao "existing"
        content = (tmp_path / ".plugadvpl" / "runtime.toml").read_text(encoding="utf-8")
        assert "[tds_ls]" in content


class TestCompileBasics:
    def test_compile_no_args_exits_2(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        result = runner.invoke(app, ["--root", str(tmp_path), "compile"])
        assert result.exit_code == 2

    def test_compile_cli_no_runtime_toml_exits_2(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        # NOTA: --mode antes do positional. files: list[Path] e variadic
        # (nargs=-1) e consome tokens option-like depois dele.
        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile", "--mode", "cli", str(foo)]
        )
        assert result.exit_code == 2


class TestCompileAppreEndToEnd:
    def test_compile_appre_with_path_shim(
        self, runner: CliRunner, tmp_path: Path, fake_advpls: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        # Test hook: env var faz compile.py usar nosso shim
        monkeypatch.setenv("PLUGADVPL_ADVPLS_BINARY", str(fake_advpls))
        # Shim retorna sucesso por default (SHIM_OUTPUT="", SHIM_EXIT="0")
        result = runner.invoke(
            app, ["--root", str(tmp_path), "--format", "json", "compile",
                  "--mode", "appre", str(foo)]
        )
        assert result.exit_code == 0, (
            f"stderr: {result.stderr if hasattr(result, 'stderr') else ''}\n"
            f"output: {result.output}"
        )


class TestSchemaContract:
    """Garante schema JSON estavel conforme spec section 8."""

    def test_full_schema_clean_compile(
        self, runner: CliRunner, tmp_path: Path, fake_advpls: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        monkeypatch.setenv("PLUGADVPL_ADVPLS_BINARY", str(fake_advpls))
        result = runner.invoke(
            app, ["--root", str(tmp_path), "--format", "json", "compile",
                  "--mode", "appre", str(foo)]
        )
        assert result.exit_code == 0, result.output
        payload = json.loads(result.stdout)

        # Top-level: render padrao do plugin envolve em {"rows": ...}.
        # output.py _render_json sempre adiciona "total"/"shown"/"truncated".
        assert "rows" in payload

        # Cada row tem campos obrigatorios (schema completo do contrato §8).
        # JSON render NAO filtra por `columns` — passa todo o dict — entao
        # counts/diagnostics aparecem mesmo com `columns=["arquivo", ...]`
        # no callback.
        for row in payload["rows"]:
            for field in ("arquivo", "ok", "mode", "duration_ms",
                          "exit_code", "counts", "diagnostics"):
                assert field in row, f"missing row field: {field} in {row}"
            assert set(row["counts"].keys()) == {"error", "warning", "info", "unknown"}

    def test_schema_with_errors(
        self, runner: CliRunner, tmp_path: Path, fake_advpls: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        monkeypatch.setenv("PLUGADVPL_ADVPLS_BINARY", str(fake_advpls))
        monkeypatch.setenv("SHIM_OUTPUT", "foo.prw(42) error: Unbalanced ENDIF\n")
        monkeypatch.setenv("SHIM_EXIT", "1")
        result = runner.invoke(
            app, ["--root", str(tmp_path), "--format", "json", "compile",
                  "--mode", "appre", str(foo)]
        )
        assert result.exit_code == 1
        payload = json.loads(result.stdout)
        # Cada diagnostic tem schema completo
        for row in payload["rows"]:
            for diag in row["diagnostics"]:
                for field in ("severidade", "arquivo", "linha", "coluna",
                              "mensagem", "codigo", "raw"):
                    assert field in diag, f"missing diagnostic field: {field}"
                assert diag["severidade"] in ("error", "warning", "info", "unknown")
