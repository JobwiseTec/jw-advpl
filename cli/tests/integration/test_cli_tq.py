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


class TestTqConfirmProd:
    """v0.15: server is_prod=True exige --confirm-prod pra rodar tq de verdade."""

    def _add_prod_server(self, name: str = "prd") -> None:
        from plugadvpl.compile_servers import Server, add_server
        add_server(Server(
            name=name, host="127.0.0.1", port=1234,
            build="7.00.240223P", environments=["env_a"],
            default_environment="env_a",
            restart_cmd="echo restart",
            is_prod=True,
        ))

    def test_prod_server_without_confirm_prod_errors(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        self._add_prod_server()
        result = runner.invoke(
            app, ["--root", str(tmp_path), "tq", "--use-server", "prd"]
        )
        assert result.exit_code == 2
        combined = (result.stdout or "") + (result.stderr or "")
        assert "PROD" in combined
        assert "--confirm-prod" in combined

    def test_prod_server_dry_run_bypasses_confirmation(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--dry-run não precisa de --confirm-prod (ainda é só preview, não restarta)."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        self._add_prod_server()
        result = runner.invoke(
            app, ["--root", str(tmp_path), "tq",
                  "--use-server", "prd", "--dry-run"]
        )
        assert result.exit_code == 0, result.output

    def test_prod_server_with_confirm_prod_proceeds(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--confirm-prod libera execução real. --no-healthcheck evita
        esperar o (inexistente) AppServer responder."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        self._add_prod_server()
        result = runner.invoke(
            app, ["--root", str(tmp_path), "tq",
                  "--use-server", "prd", "--confirm-prod",
                  "--no-healthcheck"]
        )
        # restart_cmd "echo restart" sai 0 → ok=True com healthcheck skipped
        assert result.exit_code == 0, result.output

    def test_non_prod_server_doesnt_require_confirm_prod(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Server sem is_prod (default False) não exige flag — dry-run só pra
        garantir que passa da validação de PROD sem executar restart."""
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


class TestMarkProd:
    """v0.15: --mark-prod / --no-prod no compile altera flag is_prod no registry."""

    def test_mark_prod_sets_is_prod_true(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from plugadvpl.compile_servers import Server, add_server, get_server
        add_server(Server(
            name="srv", host="h", port=1, build="b",
            environments=["e"], default_environment="e",
        ))
        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile", "--mark-prod", "srv"]
        )
        assert result.exit_code == 0, result.output
        assert get_server("srv").is_prod is True

    def test_no_prod_resets_is_prod(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from plugadvpl.compile_servers import Server, add_server, get_server
        add_server(Server(
            name="srv", host="h", port=1, build="b",
            environments=["e"], default_environment="e",
            is_prod=True,
        ))
        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile", "--no-prod", "srv"]
        )
        assert result.exit_code == 0, result.output
        assert get_server("srv").is_prod is False

    def test_mark_prod_unknown_server_errors(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile", "--mark-prod", "ghost"]
        )
        assert result.exit_code == 2
        combined = (result.stdout or "") + (result.stderr or "")
        assert "ghost" in combined and "não cadastrado" in combined


class TestTqHealthcheckHints:
    """v0.14.1: quando healthcheck falha, output sugere o que verificar."""

    def test_healthcheck_timeout_shows_actionable_hints(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Server com restart_cmd OK mas porta morta → output cita
        console.log + --port + --timeout pra orientar o usuario."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from plugadvpl.compile_servers import Server, add_server
        # Porta 1 = privileged, virtualmente garantido connection refused
        add_server(Server(
            name="deadport", host="127.0.0.1", port=1,
            build="7.00.240223P", environments=["env_a"],
            default_environment="env_a",
            restart_cmd="cmd /c echo restart" if hasattr(__builtins__, "WindowsPath") or True else "echo restart",
        ))
        result = runner.invoke(
            app, ["--root", str(tmp_path), "tq",
                  "--use-server", "deadport", "--timeout", "1"]
        )
        assert result.exit_code == 1, result.output
        combined = (result.stdout or "") + (result.stderr or "")
        # Hint deve citar pelo menos console.log + uma das opcoes acionaveis
        assert "console.log" in combined.lower(), f"sem hint sobre console.log: {combined!r}"
        # E uma das flags pra ajustar
        assert ("--port" in combined or "--timeout" in combined), \
            f"sem hint sobre --port/--timeout: {combined!r}"


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
