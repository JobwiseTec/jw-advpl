"""Testes do plugadvpl.compile orchestrator (v0.8.0 Fase 1).
Subprocess sempre mockado — nada real."""
from __future__ import annotations

import re as _re
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from plugadvpl.compile import CompileRequest, run

_CRED_REGEX = _re.compile(r"(?i)(password|psw|senha|pwd)\s*[:=]\s*\S+")


class TestResolveFiles:
    def test_explicit_list_separates_valid_missing_rejected(self, tmp_path: Path) -> None:
        """Critério: extensão inválida -> rejected_ext; arquivo não existe -> missing;
        prioridade: extensão checada antes de existência."""
        (tmp_path / "foo.prw").write_text("", encoding="utf-8")
        (tmp_path / "bar.tlpp").write_text("", encoding="utf-8")
        (tmp_path / "baz.txt").write_text("", encoding="utf-8")
        missing_path = tmp_path / "missing.prw"
        from plugadvpl.compile import resolve_files
        result = resolve_files(
            [tmp_path / "foo.prw", tmp_path / "bar.tlpp",
             tmp_path / "baz.txt", missing_path],
            changed_since=None, root=tmp_path,
        )
        names = sorted(p.name for p in result.valid_files)
        assert names == ["bar.tlpp", "foo.prw"]
        assert result.rejected_ext == [tmp_path / "baz.txt"]
        assert result.missing == [missing_path]


class TestChangedSince:
    def test_changed_since_lists_modified_advpl_only(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
        (tmp_path / "foo.prw").write_text("a", encoding="utf-8")
        (tmp_path / "README.md").write_text("a", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
        (tmp_path / "foo.prw").write_text("ab", encoding="utf-8")
        (tmp_path / "bar.tlpp").write_text("c", encoding="utf-8")
        (tmp_path / "README.md").write_text("ab", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "change"], cwd=tmp_path, check=True)

        from plugadvpl.compile import _resolve_changed_since
        result = _resolve_changed_since("HEAD~1", tmp_path)
        names = sorted(p.name for p in result)
        assert names == ["bar.tlpp", "foo.prw"]

    def test_not_a_git_repo_raises(self, tmp_path: Path) -> None:
        from plugadvpl.compile import _resolve_changed_since
        with pytest.raises(RuntimeError, match="git"):
            _resolve_changed_since("HEAD", tmp_path)


class TestPickMode:
    def test_explicit_mode_wins(self) -> None:
        from plugadvpl.compile import pick_mode
        assert pick_mode("cli", runtime_cfg=None) == "cli"
        assert pick_mode("appre", runtime_cfg=None) == "appre"

    def test_auto_no_runtime_cfg_picks_appre(self) -> None:
        from plugadvpl.compile import pick_mode
        assert pick_mode("auto", runtime_cfg=None) == "appre"

    def test_auto_with_reachable_picks_cli(self) -> None:
        from plugadvpl.compile import pick_mode
        cfg = MagicMock(appserver_reachable=True)
        assert pick_mode("auto", runtime_cfg=cfg) == "cli"

    def test_auto_with_unreachable_picks_appre(self) -> None:
        from plugadvpl.compile import pick_mode
        cfg = MagicMock(appserver_reachable=False)
        assert pick_mode("auto", runtime_cfg=cfg) == "appre"


class TestRunAppre:
    def test_clean_compile_appre(self, tmp_path: Path) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="appre", no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )
        with patch("plugadvpl.compile.subprocess.Popen") as popen_mock:
            proc = MagicMock()
            proc.communicate.return_value = (b"", b"")
            proc.returncode = 0
            popen_mock.return_value = proc
            with patch("plugadvpl.compile._resolve_advpls", return_value=Path("/fake/advpls")):
                result = run(request, runtime_cfg=None, root=tmp_path)
        assert result.exit_code == 0
        assert result.summary["mode_used"] == "appre"
        assert result.summary["total_files"] == 1
        assert result.summary["ok"] == 1
        assert result.summary["failed"] == 0

    def test_compile_appre_with_error(self, tmp_path: Path) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="appre", no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )
        with patch("plugadvpl.compile.subprocess.Popen") as popen_mock:
            proc = MagicMock()
            proc.communicate.return_value = (b"foo.prw(42) error: Unbalanced ENDIF", b"")
            proc.returncode = 1
            popen_mock.return_value = proc
            with patch("plugadvpl.compile._resolve_advpls", return_value=Path("/fake/advpls")):
                result = run(request, runtime_cfg=None, root=tmp_path)
        assert result.exit_code == 1
        assert result.summary["failed"] == 1
        row = next(r for r in result.rows if r["arquivo"] == str(foo))
        assert row["ok"] is False
        assert row["counts"]["error"] == 1

    def test_timeout_returns_synthetic_diagnostic(self, tmp_path: Path) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="appre", no_warnings=False,
            timeout_seconds=5, no_security_warning=True,
            includes_override=None, changed_since=None,
        )
        with patch("plugadvpl.compile.subprocess.Popen") as popen_mock:
            proc = MagicMock()
            proc.communicate.side_effect = subprocess.TimeoutExpired(cmd="advpls", timeout=5)
            popen_mock.return_value = proc
            with patch("plugadvpl.compile._resolve_advpls", return_value=Path("/fake/advpls")):
                result = run(request, runtime_cfg=None, root=tmp_path)
        assert result.exit_code == 1
        assert result.summary["total_errors"] >= 1
        proc.terminate.assert_called()

    def test_unmatched_diagnostic_goes_to_unmatched_bucket(self, tmp_path: Path) -> None:
        """Spec §7.8 — diagnostic com arquivo fora de requested_files vai pra row __unmatched__."""
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="appre", no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )
        # Mock retorna erro em arquivo desconhecido (outro.prw — não solicitado)
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            proc.communicate.return_value = (b"outro.prw(99) error: orphan", b"")
            proc.returncode = 1
            PopenMock.return_value = proc
            with patch("plugadvpl.compile._resolve_advpls", return_value=Path("/fake/advpls")):
                result = run(request, runtime_cfg=None, root=tmp_path)
        # Existe row __unmatched__ com o diagnostic
        unmatched_rows = [r for r in result.rows if r["arquivo"] == "__unmatched__"]
        assert len(unmatched_rows) == 1
        assert unmatched_rows[0]["counts"]["error"] == 1
        # NÃO existe row __unknown__ (nome antigo)
        assert not any(r["arquivo"] == "__unknown__" for r in result.rows)


class TestRunCli:
    def _make_runtime_cfg(
        self, host: str = "127.0.0.1", warn_remote: bool = False
    ) -> MagicMock:
        return MagicMock(
            tds_ls=MagicMock(binary=Path("/fake/advpls")),
            appserver=MagicMock(host=host, port=1234, secure=False,
                                build="7.00.240223P", environment="P2510"),
            auth=MagicMock(user_env="PROTHEUS_USER", password_env="PROTHEUS_PASS"),
            compile=MagicMock(recompile=True, includes=()),
            logging=MagicMock(log_to_file="", show_console_output=True),
            warn_remote_host=warn_remote, appserver_reachable=True,
        )

    def test_cli_mode_uses_ini_script(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "totvs")
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="cli", no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )
        runtime_cfg = self._make_runtime_cfg()
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            proc.communicate.return_value = (b"", b"")
            proc.returncode = 0
            PopenMock.return_value = proc
            result = run(request, runtime_cfg=runtime_cfg, root=tmp_path)
        assert result.exit_code == 0
        args = PopenMock.call_args.args[0]
        assert Path(args[0]) == Path("/fake/advpls")
        assert args[1] == "cli"
        assert args[2].endswith("compile.ini")
        assert PopenMock.call_args.kwargs.get("stdin") == subprocess.DEVNULL

    def test_security_warning_remote_host(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "totvs")
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="cli", no_warnings=False,
            timeout_seconds=10, no_security_warning=False,
            includes_override=None, changed_since=None,
        )
        runtime_cfg = self._make_runtime_cfg(host="187.77.46.221", warn_remote=True)
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock(); proc.communicate.return_value = (b"", b""); proc.returncode = 0
            PopenMock.return_value = proc
            run(request, runtime_cfg=runtime_cfg, root=tmp_path)
        captured = capsys.readouterr()
        assert "WARNING" in captured.err or "warning" in captured.err.lower()
        assert "ssh -L" in captured.err

    def test_no_security_warning_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "totvs")
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="cli", no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )
        runtime_cfg = self._make_runtime_cfg(host="187.77.46.221", warn_remote=True)
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock(); proc.communicate.return_value = (b"", b""); proc.returncode = 0
            PopenMock.return_value = proc
            run(request, runtime_cfg=runtime_cfg, root=tmp_path)
        captured = capsys.readouterr()
        assert "ssh -L" not in captured.err

    def test_cli_mode_without_runtime_cfg_returns_exit_2(
        self, tmp_path: Path
    ) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="cli", no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )
        with patch("plugadvpl.compile._resolve_advpls", return_value=Path("/fake/advpls")):
            result = run(request, runtime_cfg=None, root=tmp_path)
        assert result.exit_code == 2
        assert result.summary["mode_used"] == "cli"
        assert result.summary["runtime_config_loaded"] is False


class TestOutputEncoding:
    def test_utf16_le_bom_decoded(self, tmp_path: Path) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="appre", no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )
        msg = "foo.prw(1) error: Unbalanced ENDIF"
        utf16_bytes = b"\xff\xfe" + msg.encode("utf-16-le")
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            proc.communicate.return_value = (utf16_bytes, b"")
            proc.returncode = 1
            PopenMock.return_value = proc
            with patch("plugadvpl.compile._resolve_advpls", return_value=Path("/fake/advpls")):
                result = run(request, runtime_cfg=None, root=tmp_path)
        row = next(r for r in result.rows if r["arquivo"] == str(foo))
        assert row["counts"]["error"] == 1

    def test_cp1252_fallback_when_utf8_invalid(self, tmp_path: Path) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="appre", no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )
        cp1252_bytes = "foo.prw(1) error: função quebrou".encode("cp1252")
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            proc.communicate.return_value = (cp1252_bytes, b"")
            proc.returncode = 1
            PopenMock.return_value = proc
            with patch("plugadvpl.compile._resolve_advpls", return_value=Path("/fake/advpls")):
                result = run(request, runtime_cfg=None, root=tmp_path)
        row = next(r for r in result.rows if r["arquivo"] == str(foo))
        assert row["counts"]["error"] == 1
        diag = row["diagnostics"][0]
        assert "função" in diag["mensagem"] or "fun" in diag["mensagem"]


class TestNoCredentialLeak:
    """≥5 testes confirmando: regex (?i)(password|psw|senha|pwd)\\s*[:=]\\s*\\S+
    ausente em stdout/stderr/diagnostic.raw em todos os cenários típicos."""

    def _build_request(self, tmp_path: Path, mode: str = "cli") -> CompileRequest:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        return CompileRequest(
            files=[foo], mode=mode, no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )

    def _runtime_cfg(self) -> MagicMock:
        return MagicMock(
            tds_ls=MagicMock(binary=Path("/fake/advpls")),
            appserver=MagicMock(host="127.0.0.1", port=1234, secure=False,
                                build="x", environment="y"),
            auth=MagicMock(user_env="PROTHEUS_USER", password_env="PROTHEUS_PASS"),
            compile=MagicMock(recompile=True, includes=()),
            logging=MagicMock(log_to_file="", show_console_output=True),
            warn_remote_host=False, appserver_reachable=True,
        )

    def _assert_no_leak(self, captured: str, *result_jsons: dict[str, object]) -> None:
        import json as _json
        assert _CRED_REGEX.search(captured) is None, f"leak in: {captured[:200]}"
        for r in result_jsons:
            text = _json.dumps(r)
            assert _CRED_REGEX.search(text) is None, f"leak in result: {text[:200]}"

    def test_clean_compile_no_leak(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "secretSauce42")
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock(); proc.communicate.return_value = (b"", b""); proc.returncode = 0
            PopenMock.return_value = proc
            result = run(self._build_request(tmp_path), self._runtime_cfg(), tmp_path)
        captured = capsys.readouterr()
        self._assert_no_leak(captured.err + captured.out, result.summary, *result.rows)

    def test_advpls_echoes_psw_in_stderr_no_leak(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "secretSauce42")
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            proc.communicate.return_value = (b"", b"auth failed: psw=secretSauce42")
            proc.returncode = 1
            PopenMock.return_value = proc
            result = run(self._build_request(tmp_path), self._runtime_cfg(), tmp_path)
        import json as _json
        result_text = _json.dumps([_json.dumps(r) for r in result.rows])
        assert "secretSauce42" not in result_text

    def test_advpls_echoes_password_no_leak(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "topSecret")
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            proc.communicate.return_value = (
                b"foo.prw(1) error: failed with PASSWORD=topSecret oops", b""
            )
            proc.returncode = 1
            PopenMock.return_value = proc
            result = run(self._build_request(tmp_path), self._runtime_cfg(), tmp_path)
        import json as _json
        assert "topSecret" not in _json.dumps([_json.dumps(r) for r in result.rows])

    def test_pt_senha_no_leak(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "minhaSenh@")
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            proc.communicate.return_value = (b"erro: senha=minhaSenh@", b"")
            proc.returncode = 1
            PopenMock.return_value = proc
            result = run(self._build_request(tmp_path), self._runtime_cfg(), tmp_path)
        import json as _json
        assert "minhaSenh@" not in _json.dumps([_json.dumps(r) for r in result.rows])

    def test_appre_mode_no_leak(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            proc.communicate.return_value = (
                b"foo.prw(1) error: missing include 'pwd=xyz.ch'", b""
            )
            proc.returncode = 1
            PopenMock.return_value = proc
            with patch("plugadvpl.compile._resolve_advpls", return_value=Path("/fake/advpls")):
                result = run(self._build_request(tmp_path, mode="appre"), None, tmp_path)
        import json as _json
        text = _json.dumps([_json.dumps(r) for r in result.rows])
        assert "pwd=xyz" not in text
        assert "REDACTED" in text


class TestLifecycle:
    def test_keyboard_interrupt_kills_subprocess(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "totvs")
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="cli", no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )
        runtime_cfg = MagicMock(
            tds_ls=MagicMock(binary=Path("/fake/advpls")),
            appserver=MagicMock(host="127.0.0.1", port=1234, secure=False,
                                build="x", environment="y"),
            auth=MagicMock(user_env="PROTHEUS_USER", password_env="PROTHEUS_PASS"),
            compile=MagicMock(recompile=True, includes=()),
            logging=MagicMock(log_to_file="", show_console_output=True),
            warn_remote_host=False, appserver_reachable=True,
        )
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            proc.communicate.side_effect = KeyboardInterrupt
            PopenMock.return_value = proc
            with pytest.raises(KeyboardInterrupt):
                run(request, runtime_cfg=runtime_cfg, root=tmp_path)
            proc.terminate.assert_called_once()

    def test_keyboard_interrupt_cleans_tempdir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Spec §11.3: ao receber KeyboardInterrupt, tempdir deve ser removido."""
        import tempfile as _tempfile
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "totvs")
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="cli", no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )
        runtime_cfg = MagicMock(
            tds_ls=MagicMock(binary=Path("/fake/advpls")),
            appserver=MagicMock(host="127.0.0.1", port=1234, secure=False,
                                build="x", environment="y"),
            auth=MagicMock(user_env="PROTHEUS_USER", password_env="PROTHEUS_PASS"),
            compile=MagicMock(recompile=True, includes=()),
            logging=MagicMock(log_to_file="", show_console_output=True),
            warn_remote_host=False, appserver_reachable=True,
        )

        captured_tempdir: list[Path] = []
        original_mkdtemp = _tempfile.mkdtemp

        def _spy_mkdtemp(*args: object, **kwargs: object) -> str:
            td = original_mkdtemp(*args, **kwargs)
            captured_tempdir.append(Path(td))
            return td

        with patch("plugadvpl.compile.tempfile.mkdtemp", side_effect=_spy_mkdtemp):
            with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
                proc = MagicMock()
                proc.communicate.side_effect = KeyboardInterrupt
                PopenMock.return_value = proc
                with pytest.raises(KeyboardInterrupt):
                    run(request, runtime_cfg=runtime_cfg, root=tmp_path)

        assert len(captured_tempdir) == 1, "esperava 1 tempdir criado"
        assert not captured_tempdir[0].exists(), (
            f"tempdir {captured_tempdir[0]} deveria ter sido removido"
        )


class TestTempIniFile:
    def test_creates_secure_tempdir_and_file(self, tmp_path: Path) -> None:
        from plugadvpl.compile import _write_secure_ini
        content = "[auth]\nuser=admin\n"
        ini_path, tempdir = _write_secure_ini(content)
        try:
            assert ini_path.is_file()
            raw = ini_path.read_bytes()
            assert raw == content.encode("cp1252", errors="replace")
            import os as _os
            if _os.name == "posix":
                mode = _os.stat(ini_path).st_mode & 0o777
                assert mode == 0o600
        finally:
            import shutil as _shutil
            _shutil.rmtree(tempdir, ignore_errors=True)

    def test_encoding_with_accent_password(self, tmp_path: Path) -> None:
        from plugadvpl.compile import _write_secure_ini
        content = "psw=açúcar\n"
        ini_path, tempdir = _write_secure_ini(content)
        try:
            assert ini_path.read_bytes() == "psw=açúcar\n".encode("cp1252")
        finally:
            import shutil as _shutil
            _shutil.rmtree(tempdir, ignore_errors=True)


class TestBuildIni:
    def test_ini_contains_all_sections(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from plugadvpl.compile import _build_ini_script
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "totvs")
        runtime_cfg = MagicMock(
            appserver=MagicMock(host="127.0.0.1", port=1234, secure=False,
                                build="7.00.240223P", environment="P2510"),
            auth=MagicMock(user_env="PROTHEUS_USER", password_env="PROTHEUS_PASS"),
            compile=MagicMock(recompile=True),
            logging=MagicMock(log_to_file="", show_console_output=True),
        )
        files = [Path("foo.prw"), Path("bar.prw")]
        includes = [Path("D:/inc1"), Path("D:/inc2")]
        text = _build_ini_script(runtime_cfg, files, includes)
        assert "[auth]" in text
        assert "[compile]" in text
        assert "action=authentication" in text
        assert "action=compile" in text
        assert "user=admin" in text
        assert "psw=totvs" in text
        assert "server=127.0.0.1" in text
        assert "port=1234" in text
        assert "secure=0" in text
        assert "build=7.00.240223P" in text
        assert "environment=P2510" in text
        assert "program=foo.prw;bar.prw" in text
        assert "recompile=T" in text
        assert "includes=D:/inc1;D:/inc2" in text
        assert "showConsoleOutput=true" in text


class TestNormalizeExitCode:
    """v0.8.1: advpls retorna -1 em Windows que vira 4294967295 unsigned no JSON.
    Normalizar pra faixa 0-255 (POSIX). 0=sucesso, !=0=falha."""

    def test_zero_stays_zero(self) -> None:
        from plugadvpl.compile import _normalize_exit_code
        assert _normalize_exit_code(0) == 0

    def test_negative_becomes_one(self) -> None:
        from plugadvpl.compile import _normalize_exit_code
        assert _normalize_exit_code(-1) == 1

    def test_huge_unsigned_becomes_one(self) -> None:
        from plugadvpl.compile import _normalize_exit_code
        assert _normalize_exit_code(4294967295) == 1

    def test_in_range_preserved(self) -> None:
        from plugadvpl.compile import _normalize_exit_code
        assert _normalize_exit_code(1) == 1
        assert _normalize_exit_code(124) == 124


class TestAppreErrprwIntegration:
    """v0.8.1 bug #1: advpls appre escreve erros em .errprw (não stdout/stderr).
    Verifica que orchestrator passa -O <tempdir> e lê .errprw."""

    def test_appre_passes_output_dir_to_advpls(self, tmp_path: Path) -> None:
        from plugadvpl.compile import _build_appre_args
        binary = Path("/fake/advpls")
        files = [tmp_path / "foo.prw"]
        output_dir = tmp_path / "out"
        args = _build_appre_args(binary, [], files, output_dir)
        assert "-O" in args
        assert str(output_dir) in args

    def test_collect_errprw_reads_basename_lowercase(self, tmp_path: Path) -> None:
        from plugadvpl.compile import _collect_errprw_diagnostics
        # advpls escreve foo_real.errprw (lowercase) mesmo se fonte é FOO_REAL.PRW
        errprw = tmp_path / "foo_real.errprw"
        errprw.write_text(
            "APPRE41.PRW(0) Error C2090  File not found PRTOPDEF.CH",
            encoding="utf-8",
        )
        fonte = tmp_path / "FOO_REAL.PRW"
        by_file = _collect_errprw_diagnostics(tmp_path, [fonte])
        assert str(fonte) in by_file
        diags = by_file[str(fonte)]
        assert len(diags) == 1
        assert diags[0].severidade == "error"
        assert diags[0].codigo == "C2090"

    def test_collect_errprw_missing_file_skipped(self, tmp_path: Path) -> None:
        from plugadvpl.compile import _collect_errprw_diagnostics
        # Compilação bem-sucedida não gera .errprw
        fonte = tmp_path / "CLEAN.PRW"
        by_file = _collect_errprw_diagnostics(tmp_path, [fonte])
        assert by_file == {}


class TestResolveAdvplsChecksInstalledDir:
    """v0.8.8 bug 3: _resolve_advpls precisa checar ~/.plugadvpl/advpls/
    (não só env var + runtime.toml + PATH)."""

    def test_resolves_from_installed_dir_when_no_env_no_cfg(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from plugadvpl.compile import _resolve_advpls
        # Mock home + cria advpls em ~/.plugadvpl/advpls/bin/<os>/
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        import os as _os
        os_sub = {"nt": "windows", "posix": "linux"}.get(_os.name, "linux")
        bin_name = "advpls.exe" if _os.name == "nt" else "advpls"
        target = tmp_path / ".plugadvpl" / "advpls" / "bin" / os_sub / bin_name
        target.parent.mkdir(parents=True)
        target.write_text("", encoding="utf-8")
        monkeypatch.delenv("PLUGADVPL_ADVPLS_BINARY", raising=False)
        with patch("plugadvpl.compile.shutil.which", return_value=None):
            with patch("plugadvpl.compile_doctor._ADVPLS_WIN_CANDIDATES", []):
                result = _resolve_advpls(None)
        assert result == target


class TestOkFlagConsidersSubprocessFailure:
    """v0.8.1 bug #3: ok=true ignorava advpls crash que não produz diagnostic.
    Agora ok requer (zero errors) AND (subprocess ok OR diagnostics estruturados)."""

    def test_subprocess_fails_silently_ok_false(self, tmp_path: Path) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="appre", no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            # advpls retorna -1 (crash silencioso) sem stdout/stderr
            proc.communicate.return_value = (b"", b"")
            proc.returncode = -1
            PopenMock.return_value = proc
            with patch("plugadvpl.compile._resolve_advpls", return_value=Path("/fake/advpls")):
                result = run(request, runtime_cfg=None, root=tmp_path)
        # exit_code normalizado (não 4294967295)
        assert result.rows[0]["exit_code"] == 1
        # ok=false porque subprocess falhou sem produzir diagnostic
        assert result.rows[0]["ok"] is False
        # Plugin exit code também 1
        assert result.exit_code == 1

