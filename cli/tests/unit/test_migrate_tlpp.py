"""Unit tests for plugadvpl/migrate_tlpp.py + migrate_tlpp_diff.py (v0.18.0+)."""
from __future__ import annotations

from plugadvpl.migrate_tlpp_diff import has_changes, unified_diff_text


class TestUnifiedDiffText:
    def test_returns_empty_when_identical(self) -> None:
        result = unified_diff_text("x\ny\n", "x\ny\n", "a.prw", "a.tlpp")
        assert result == ""

    def test_includes_headers_and_changes(self) -> None:
        result = unified_diff_text(
            "User Function X()\n", "function u_x()\n", "a.prw", "a.tlpp"
        )
        assert "--- a.prw" in result
        assert "+++ a.tlpp" in result
        assert "-User Function X()" in result
        assert "+function u_x()" in result


class TestHasChanges:
    def test_true_when_differ(self) -> None:
        assert has_changes("a", "b") is True

    def test_false_when_identical(self) -> None:
        assert has_changes("x", "x") is False
