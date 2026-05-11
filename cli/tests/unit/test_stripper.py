"""Testes do mini-tokenizer (strip_advpl).

Princípio: substituir comentários (//, /* */) e strings (",') por espaços,
preservando newlines e contagem de linhas/offsets.
"""
from __future__ import annotations

from plugadvpl.parsing.stripper import strip_advpl


def _same_length(original: str, stripped: str) -> bool:
    return len(original) == len(stripped)


def _same_lines(original: str, stripped: str) -> bool:
    return original.count("\n") == stripped.count("\n")


class TestLineComment:
    def test_strips_line_comment(self) -> None:
        src = 'cFoo := "hello"   // comment\nReturn .T.'
        out = strip_advpl(src)
        assert _same_length(src, out)
        assert _same_lines(src, out)
        # comentário e string viram espaços
        assert "comment" not in out
        assert "hello" not in out
        # código preservado
        assert "cFoo" in out
        assert "Return" in out


class TestBlockComment:
    def test_strips_multiline_block_comment(self) -> None:
        src = "Function Foo()\n/* multi\nline comment */\nReturn .T."
        out = strip_advpl(src)
        assert _same_length(src, out)
        assert _same_lines(src, out)
        assert "multi" not in out
        assert "comment" not in out
        assert "Function" in out
        assert "Return" in out


class TestStrings:
    def test_strips_double_quoted(self) -> None:
        src = 'cMsg := "RecLock(\'SA1\')"'
        out = strip_advpl(src)
        assert "RecLock" not in out  # estava dentro da string
        assert "cMsg" in out

    def test_strips_single_quoted(self) -> None:
        src = "DbSelectArea('SA1')"
        out = strip_advpl(src)
        assert "SA1" not in out  # estava dentro de string single-quoted
        assert "DbSelectArea" in out


class TestNoFalsePositives:
    def test_reclock_in_comment_disappears(self) -> None:
        src = 'Function Grava()\n  // TODO: RecLock("SA1")\nReturn .T.'
        out = strip_advpl(src)
        assert "RecLock" not in out
        assert "Function" in out
        assert "Grava" in out


class TestPreserveOffsets:
    def test_offsets_preserved_exact(self) -> None:
        src = 'a := "hello world" + b'
        out = strip_advpl(src)
        assert len(src) == len(out)
        # 'b' deve estar na mesma posição
        assert out.rstrip()[-1] == "b"
        assert out.index("b") == src.index("b")
