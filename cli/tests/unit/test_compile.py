"""Testes do plugadvpl.compile orchestrator (v0.8.0 Fase 1).
Subprocess sempre mockado — nada real."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from plugadvpl.compile import CompileRequest, run


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
