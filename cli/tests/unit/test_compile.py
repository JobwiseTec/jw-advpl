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
