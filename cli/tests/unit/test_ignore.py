"""Unit do matcher de .plugadvplignore (issue #141)."""
from __future__ import annotations

from pathlib import Path

from plugadvpl.ignore import IgnoreMatcher, load_ignore_file


class TestIgnoreMatcher:
    def test_empty_patterns_matches_nothing(self) -> None:
        m = IgnoreMatcher([])
        assert m.matches("src/MATA010.prw") is False
        assert m.pattern_count == 0

    def test_dir_slash_matches_subtree(self) -> None:
        m = IgnoreMatcher(["descontinuado/"])
        assert m.matches("descontinuado/MATA010.prw") is True
        assert m.matches("mod/descontinuado/x.prw") is True   # em qualquer nível
        assert m.matches("descontinuado") is False            # é arquivo, não dir-content
        assert m.matches("ativo/MATA010.prw") is False

    def test_dir_match_for_pruning(self) -> None:
        m = IgnoreMatcher(["descontinuado/"])
        assert m.matches_dir("descontinuado") is True
        assert m.matches_dir("mod/descontinuado") is True
        assert m.matches_dir("ativo") is False

    def test_basename_glob_any_level(self) -> None:
        m = IgnoreMatcher(["*_old.prw"])
        assert m.matches("MATA010_old.prw") is True
        assert m.matches("mod/x/FINA050_old.prw") is True
        assert m.matches("MATA010.prw") is False

    def test_path_glob_with_doublestar(self) -> None:
        m = IgnoreMatcher(["clientes/**/v1/*.prw"])
        assert m.matches("clientes/abc/v1/X.prw") is True
        assert m.matches("clientes/abc/def/v1/Y.prw") is True
        assert m.matches("clientes/abc/v2/Z.prw") is False

    def test_comments_and_blanks_ignored(self) -> None:
        m = IgnoreMatcher(["# comentario", "", "  ", "descontinuado/"])
        assert m.pattern_count == 1
        assert m.matches("descontinuado/x.prw") is True

    def test_backslash_paths_normalized(self) -> None:
        """rel_path com separador do Windows (UM backslash) é normalizado pra '/'."""
        m = IgnoreMatcher(["descontinuado/"])
        assert m.matches("descontinuado\\x.prw") is True   # \\x = um backslash + x


class TestLoadIgnoreFile:
    def test_absent_file_returns_empty(self, tmp_path: Path) -> None:
        assert load_ignore_file(tmp_path) == []

    def test_reads_lines(self, tmp_path: Path) -> None:
        (tmp_path / ".plugadvplignore").write_text(
            "# header\ndescontinuado/\n\n*.bak.prw\n", encoding="utf-8"
        )
        lines = load_ignore_file(tmp_path)
        assert "descontinuado/" in lines
        assert "*.bak.prw" in lines
