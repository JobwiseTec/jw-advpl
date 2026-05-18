"""Testes do plugadvpl.compile orchestrator (v0.8.0 Fase 1).
Subprocess sempre mockado — nada real."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from plugadvpl.compile import CompileRequest, CompileResult, run


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
