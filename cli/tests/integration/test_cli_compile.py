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


class TestBug1FlagAfterPositional:
    """v0.8.8 bug 1 (smoke real): typer positional variadic consome flags
    posteriores. ANTES: caía silenciosamente em --mode auto/appre.
    AGORA: detecta flags conhecidas em `files` e erra com exit 2 + mensagem."""

    def test_mode_after_positional_errors_loud(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile",
                  str(foo), "--mode", "cli", "--includes", "/inc"],
        )
        assert result.exit_code == 2
        # Mensagem inclui as 2 flags detectadas + exemplo CERTO/ERRADO
        combined = (result.stdout or "") + (result.stderr or "") + (result.output or "")
        assert "--mode" in combined
        assert "--includes" in combined

    def test_flags_before_positional_still_works(
        self, runner: CliRunner, tmp_path: Path, fake_advpls: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        monkeypatch.setenv("PLUGADVPL_ADVPLS_BINARY", str(fake_advpls))
        # Ordem correta: flags ANTES
        result = runner.invoke(
            app, ["--root", str(tmp_path), "--format", "json", "compile",
                  "--mode", "appre", str(foo)],
        )
        assert result.exit_code == 0, result.output


class TestBug4UseServerValidation:
    """v0.8.8 bug 4: --use-server com server incompleto OU env vars ausentes
    deve errar cedo com mensagem clara."""

    def test_server_missing_build_errors_early(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from plugadvpl.compile_servers import Server, add_server
        add_server(Server(
            name="incomplete", host="127.0.0.1", port=1234, build="",
            environments=["P2510"], default_environment="P2510",
        ))
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile",
                  "--use-server", "incomplete", "--mode", "cli", str(foo)],
        )
        assert result.exit_code == 2
        combined = (result.stdout or "") + (result.stderr or "") + (result.output or "")
        assert "build" in combined.lower()

    def test_server_missing_env_vars_errors_early(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("PROTHEUS_USER", raising=False)
        monkeypatch.delenv("PROTHEUS_PASS", raising=False)
        from plugadvpl.compile_servers import Server, add_server
        add_server(Server(
            name="needauth", host="127.0.0.1", port=1234, build="7.00.240223P",
            environments=["P2510"], default_environment="P2510",
            user_env="PROTHEUS_USER", password_env="PROTHEUS_PASS",
        ))
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile",
                  "--use-server", "needauth", "--mode", "cli", str(foo)],
        )
        assert result.exit_code == 2
        combined = (result.stdout or "") + (result.stderr or "") + (result.output or "")
        assert "PROTHEUS_USER" in combined or "PROTHEUS_PASS" in combined


class TestCredentialsKeyringIntegration:
    """v0.9.0: --set-credentials → --use-server reads from keyring transparently."""

    def test_keyring_resolves_when_env_missing(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Server tem creds no cofre, env vars vazias → resolve_credentials
        deve achar e o erro de "env missing" NÃO deve aparecer."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("PROTHEUS_USER", raising=False)
        monkeypatch.delenv("PROTHEUS_PASS", raising=False)
        from plugadvpl.compile_servers import Server, add_server

        # Monkeypatch keyring para in-memory
        import sys
        from tests.unit.test_credentials import FakeKeyring
        fake = FakeKeyring()
        monkeypatch.setitem(sys.modules, "keyring", fake)
        monkeypatch.setitem(
            sys.modules, "keyring.errors",
            type("M", (), {"KeyringError": Exception}),
        )

        # Salva credenciais no fake keyring
        from plugadvpl.credentials import set_credentials_in_keyring
        set_credentials_in_keyring("kringsrv", "kr_admin", "kr_secret")

        add_server(Server(
            name="kringsrv", host="127.0.0.1", port=1234, build="7.00.240223P",
            environments=["P2510"], default_environment="P2510",
        ))
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")

        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile",
                  "--use-server", "kringsrv", "--mode", "cli", str(foo)],
        )
        # Pode falhar por motivos posteriores (advpls ausente, AppServer
        # inacessível) — o que importa é que NÃO deu erro de "sem credencial".
        combined = (result.stdout or "") + (result.stderr or "") + (result.output or "")
        assert "sem credencial" not in combined.lower()
        assert "--set-credentials" not in combined  # erro de cofre não apareceu

    def test_no_creds_anywhere_shows_both_options(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Sem env, sem keyring (mock vazio) → erro com 2 opções
        (Opção A keyring, Opção B env var)."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("PROTHEUS_USER", raising=False)
        monkeypatch.delenv("PROTHEUS_PASS", raising=False)

        import sys
        from tests.unit.test_credentials import FakeKeyring
        monkeypatch.setitem(sys.modules, "keyring", FakeKeyring())
        monkeypatch.setitem(
            sys.modules, "keyring.errors",
            type("M", (), {"KeyringError": Exception}),
        )

        from plugadvpl.compile_servers import Server, add_server
        add_server(Server(
            name="empty", host="127.0.0.1", port=1234, build="7.00.240223P",
            environments=["P2510"], default_environment="P2510",
        ))
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")

        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile",
                  "--use-server", "empty", "--mode", "cli", str(foo)],
        )
        assert result.exit_code == 2
        combined = (result.stdout or "") + (result.stderr or "") + (result.output or "")
        # Erro mostra ambas as opções
        assert "set-credentials" in combined or "Opção A" in combined
        assert "PROTHEUS_USER" in combined or "Opção B" in combined


class TestAppreSkipsCredentials:
    """v0.9.1: --use-server + --mode appre NÃO deve exigir credenciais
    (appre é pré-processador local, não conecta no AppServer)."""

    def test_use_server_appre_runs_without_credentials(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        monkeypatch.delenv("PROTHEUS_USER", raising=False)
        monkeypatch.delenv("PROTHEUS_PASS", raising=False)

        # Sem keyring tampouco
        import sys
        from tests.unit.test_credentials import FakeKeyring
        monkeypatch.setitem(sys.modules, "keyring", FakeKeyring())
        monkeypatch.setitem(
            sys.modules, "keyring.errors",
            type("M", (), {"KeyringError": Exception}),
        )

        from plugadvpl.compile_servers import Server, add_server
        add_server(Server(
            name="appre-only", host="127.0.0.1", port=1234, build="7.00.240223P",
            environments=["P2510"], default_environment="P2510",
        ))
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")

        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile",
                  "--use-server", "appre-only", "--mode", "appre", str(foo)],
        )
        # Pode falhar depois (advpls ausente, etc) — o que NÃO pode é o
        # erro de credencial. exit_code 2 do _apply_server_override é o gate.
        combined = (result.stdout or "") + (result.stderr or "") + (result.output or "")
        assert "sem credencial" not in combined.lower()
        assert "Opção A" not in combined
        assert "Opção B" not in combined


class TestSetRestartCmd:
    """v0.14: --set-restart-cmd grava restart_cmd no server do registry."""

    def test_set_restart_cmd_happy_path(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from plugadvpl.compile_servers import Server, add_server, get_server
        add_server(Server(
            name="local-dev", host="127.0.0.1", port=1234, build="7.00.240223P",
            environments=["env_a"], default_environment="env_a",
        ))
        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile",
                  "--set-restart-cmd", "local-dev",
                  "--cmd", "echo restart"],
        )
        assert result.exit_code == 0, result.output
        srv = get_server("local-dev")
        assert srv is not None
        assert srv.restart_cmd == "echo restart"

    def test_set_restart_cmd_without_cmd_errors(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from plugadvpl.compile_servers import Server, add_server
        add_server(Server(
            name="x", host="127.0.0.1", port=1234, build="7.00.240223P",
            environments=["env_a"], default_environment="env_a",
        ))
        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile",
                  "--set-restart-cmd", "x"],
        )
        assert result.exit_code == 2
        combined = (result.stdout or "") + (result.stderr or "")
        assert "--cmd" in combined

    def test_set_restart_cmd_unknown_server_errors(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile",
                  "--set-restart-cmd", "ghost",
                  "--cmd", "echo x"],
        )
        assert result.exit_code == 2
        combined = (result.stdout or "") + (result.stderr or "")
        assert "ghost" in combined and "não cadastrado" in combined


class TestAllEnvs:
    """v0.13.2: --all-envs itera environments do server.

    Caso de uso: servidor com `protheus` E `protheus_rest` -- compile precisa
    bater nos 2 RPOs senao o REST nao carrega o codigo novo.
    """

    def test_all_envs_requires_use_server(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--all-envs sem --use-server deve erar."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile",
                  "--all-envs", "--mode", "appre", str(foo)],
        )
        assert result.exit_code == 2
        combined = (result.stdout or "") + (result.stderr or "") + (result.output or "")
        assert "--all-envs" in combined and "--use-server" in combined

    def test_all_envs_conflicts_with_use_environment(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--all-envs + --use-environment sao mutuamente exclusivos."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from plugadvpl.compile_servers import Server, add_server
        add_server(Server(
            name="multi", host="127.0.0.1", port=1234, build="7.00.240223P",
            environments=["env_a", "env_b"], default_environment="env_a",
        ))
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile",
                  "--all-envs", "--use-server", "multi",
                  "--use-environment", "env_a", "--mode", "appre", str(foo)],
        )
        assert result.exit_code == 2
        combined = (result.stdout or "") + (result.stderr or "") + (result.output or "")
        assert "all-envs" in combined and ("use-environment" in combined or "mutuamente" in combined)

    def test_all_envs_with_single_env_warns_and_runs(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Server com 1 env nao quebra --all-envs, so emite warning."""
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from plugadvpl.compile_servers import Server, add_server
        add_server(Server(
            name="solo", host="127.0.0.1", port=1234, build="7.00.240223P",
            environments=["only_env"], default_environment="only_env",
        ))
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile",
                  "--all-envs", "--use-server", "solo",
                  "--mode", "appre", str(foo)],
        )
        # Pode falhar depois (advpls ausente etc), mas o warning + nao erro
        # antes do compile e o que conta.
        combined = (result.stdout or "") + (result.stderr or "") + (result.output or "")
        # Nao deve cair em "--all-envs requer" ou "mutuamente exclusivos"
        assert "--all-envs requer" not in combined
        assert "mutuamente exclusivos" not in combined


class TestExplainConfig:
    """v0.9.0: --explain-config mostra de onde vem cada campo."""

    def test_explain_includes_resolution_order(
        self, runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = runner.invoke(
            app, ["--format", "json", "--root", str(tmp_path),
                  "compile", "--explain-config"],
        )
        assert result.exit_code == 0, result.output
        import json
        payload = json.loads(result.stdout)
        # Estrutura conhecida
        row = payload["rows"][0]
        assert "resolution_order" in row
        assert "fields" in row
        assert "credentials" in row
        assert any("keyring" in step.lower() for step in row["resolution_order"])
