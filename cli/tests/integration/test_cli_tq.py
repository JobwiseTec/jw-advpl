"""Testes integration do subcomando plugadvpl tq."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from plugadvpl.cli import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestTqValidations:
    """Erros estruturados antes de qualquer side-effect."""

    def test_tq_without_use_server_errors(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = runner.invoke(app, ["--root", str(tmp_path), "tq"])
        assert result.exit_code == 2
        combined = (result.stdout or "") + (result.stderr or "")
        assert "--use-server" in combined

    def test_tq_with_unknown_server_errors(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = runner.invoke(
            app, ["--root", str(tmp_path), "tq", "--use-server", "ghost"]
        )
        assert result.exit_code == 2
        combined = (result.stdout or "") + (result.stderr or "")
        assert "ghost" in combined and "não cadastrado" in combined

    def test_tq_server_without_restart_cmd_errors(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from plugadvpl.compile_servers import Server, add_server
        add_server(Server(
            name="no-cmd", host="127.0.0.1", port=1234,
            build="7.00.240223P", environments=["env_a"],
            default_environment="env_a",
        ))
        result = runner.invoke(
            app, ["--root", str(tmp_path), "tq", "--use-server", "no-cmd"]
        )
        assert result.exit_code == 2
        combined = (result.stdout or "") + (result.stderr or "")
        assert "sem restart_cmd" in combined
        assert "--set-restart-cmd no-cmd --cmd" in combined


class TestTqDryRun:
    """--dry-run nao executa subprocess, so imprime preview."""

    def test_dry_run_with_valid_server(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from plugadvpl.compile_servers import Server, add_server
        add_server(Server(
            name="dev", host="127.0.0.1", port=1234,
            build="7.00.240223P", environments=["env_a"],
            default_environment="env_a",
            restart_cmd="echo restart",
        ))
        result = runner.invoke(
            app, ["--root", str(tmp_path), "tq",
                  "--use-server", "dev", "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        combined = (result.stdout or "") + (result.stderr or "")
        assert "echo restart" in combined
        assert "dry_run" in combined.lower() or "dry-run" in combined.lower()


class TestTqPortOverride:
    """--port override do server.port (caso real: TCP advpls != REST port)."""

    def test_dry_run_with_port_override_uses_new_port(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from plugadvpl.compile_servers import Server, add_server
        add_server(Server(
            name="dev", host="127.0.0.1", port=1234,  # TCP advpls
            build="7.00.240223P", environments=["env_a"],
            default_environment="env_a",
            restart_cmd="echo restart",
        ))
        result = runner.invoke(
            app, ["--root", str(tmp_path), "tq",
                  "--use-server", "dev", "--port", "8019",
                  "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        combined = (result.stdout or "") + (result.stderr or "")
        assert "8019" in combined  # porta override aparece no host display


class TestTqJsonOutput:
    """--format json honra schema documentado."""

    def test_dry_run_json_output_has_expected_keys(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from plugadvpl.compile_servers import Server, add_server
        add_server(Server(
            name="dev", host="127.0.0.1", port=1234,
            build="7.00.240223P", environments=["env_a"],
            default_environment="env_a",
            restart_cmd="echo restart",
        ))
        result = runner.invoke(
            app, ["--format", "json", "--root", str(tmp_path), "tq",
                  "--use-server", "dev", "--dry-run"]
        )
        assert result.exit_code == 0, result.output
        # Output deve conter um JSON parseável
        out = result.stdout or ""
        # Extrai o JSON (pode ter linhas antes/depois)
        json_start = out.find("{")
        json_end = out.rfind("}")
        if json_start == -1 or json_end == -1:
            json_start = out.find("[")
            json_end = out.rfind("]")
        assert json_start != -1, f"Sem JSON no output: {out!r}"
        payload = json.loads(out[json_start:json_end + 1])
        # Aceita lista de rows ou dict
        if isinstance(payload, list):
            payload = payload[0]
        elif "rows" in payload:
            payload = payload["rows"][0]
        assert payload.get("server") == "dev" or payload.get("server_name") == "dev"
