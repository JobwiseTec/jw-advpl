"""Testes de plugadvpl.compile_parser (v0.8.0 Fase 1)."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.compile_parser import Diagnostic, parse_diagnostics


FIXTURES = Path(__file__).parent.parent / "fixtures" / "compile_outputs"


class TestParseBasic:
    def test_unbalanced_endif_en(self) -> None:
        raw = (FIXTURES / "unbalanced_endif_en.txt").read_text(encoding="utf-8")
        matched, unmatched = parse_diagnostics(
            stdout=raw, stderr="", mode="cli", requested_files=[Path("foo.prw")]
        )
        # 1 diagnostic estruturado + nenhum unknown extra (linha única)
        errors = [d for d in matched if d.severidade == "error"]
        assert len(errors) == 1
        d = errors[0]
        assert d.arquivo == "foo.prw"
        assert d.linha == 42
        assert "Unbalanced" in d.mensagem
        assert unmatched == []

    def test_pt_br_missing_include(self) -> None:
        raw = (FIXTURES / "missing_include_pt.txt").read_text(encoding="utf-8")
        matched, _ = parse_diagnostics(
            stdout=raw, stderr="", mode="cli", requested_files=[Path("foo.prw")]
        )
        errors = [d for d in matched if d.severidade == "error"]
        assert len(errors) == 1
        assert errors[0].linha == 3
        assert "xxx.ch" in errors[0].mensagem


class TestParseMixed:
    def test_mixed_counts_match(self) -> None:
        raw = (FIXTURES / "mixed_errors_warnings.txt").read_text(encoding="utf-8")
        matched, _ = parse_diagnostics(
            stdout=raw, stderr="", mode="cli",
            requested_files=[Path("foo.prw"), Path("bar.prw")],
        )
        errors = [d for d in matched if d.severidade == "error"]
        warnings = [d for d in matched if d.severidade == "warning"]
        unknowns = [d for d in matched if d.severidade == "unknown"]
        assert len(errors) == 5
        assert len(warnings) == 3
        assert len(unknowns) >= 2


class TestPathNormalization:
    def test_absolute_path_matches_relative_request(self, tmp_path: Path) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        absolute_str = str(foo.resolve())
        raw = f"{absolute_str}(42) error: bad"
        matched, unmatched = parse_diagnostics(
            stdout=raw, stderr="", mode="cli", requested_files=[foo],
        )
        errors = [d for d in matched if d.severidade == "error"]
        assert len(errors) == 1
        assert errors[0].arquivo == str(foo)
        assert unmatched == []

    def test_unrequested_file_goes_to_unmatched_bucket(self, tmp_path: Path) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        raw = "outro.prw(1) error: bad"
        matched, unmatched = parse_diagnostics(
            stdout=raw, stderr="", mode="cli", requested_files=[foo],
        )
        errors_in_matched = [d for d in matched if d.severidade == "error"]
        assert errors_in_matched == []
        assert len(unmatched) == 1
        assert unmatched[0].arquivo == "outro.prw"

    def test_relative_path_in_requested_works(self) -> None:
        """Path inexistente no cwd ainda deve casar com diagnostic raw."""
        raw = "foo.prw(1) error: bad"
        matched, _ = parse_diagnostics(
            stdout=raw, stderr="", mode="cli", requested_files=[Path("foo.prw")]
        )
        errors = [d for d in matched if d.severidade == "error"]
        assert len(errors) == 1
        assert errors[0].arquivo == "foo.prw"


class TestTieBreak:
    def test_same_ordem_first_in_json_wins(self) -> None:
        raw = "foo.prw(1) error: x"
        matched, _ = parse_diagnostics(
            stdout=raw, stderr="", mode="cli", requested_files=[Path("foo.prw")]
        )
        errors = [d for d in matched if d.severidade == "error"]
        assert len(errors) == 1
        assert errors[0].severidade == "error"


class TestEmptyAndCrash:
    def test_empty_output_returns_empty_lists(self) -> None:
        matched, unmatched = parse_diagnostics(
            stdout="", stderr="", mode="cli", requested_files=[Path("foo.prw")]
        )
        assert matched == []
        assert unmatched == []

    def test_clean_compile_only_unknown_lines(self) -> None:
        raw = (FIXTURES / "clean_compile.txt").read_text(encoding="utf-8")
        matched, unmatched = parse_diagnostics(
            stdout=raw, stderr="", mode="cli", requested_files=[Path("foo.prw")]
        )
        assert all(d.severidade == "unknown" for d in matched)
        assert unmatched == []

    def test_empty_fixture_file_returns_empty(self) -> None:
        raw = (FIXTURES / "empty_output.txt").read_text(encoding="utf-8")
        matched, unmatched = parse_diagnostics(
            stdout=raw, stderr="", mode="cli", requested_files=[Path("foo.prw")]
        )
        assert matched == []
        assert unmatched == []


class TestRedact:
    def test_password_redacted_in_raw(self) -> None:
        raw = "foo.prw(1) error: connection failed psw=mySecret123"
        matched, _ = parse_diagnostics(
            stdout=raw, stderr="", mode="cli", requested_files=[Path("foo.prw")]
        )
        errors = [d for d in matched if d.severidade == "error"]
        assert len(errors) == 1
        assert "mySecret123" not in errors[0].raw
        assert "mySecret123" not in errors[0].mensagem
        assert "REDACTED" in errors[0].raw


class TestAppreIncludeNotFound:
    def test_appre_pattern_matches(self) -> None:
        raw = "Include 'xxx.ch' not found in foo.prw"
        matched, _ = parse_diagnostics(
            stdout=raw, stderr="", mode="appre", requested_files=[Path("foo.prw")]
        )
        errors = [d for d in matched if d.severidade == "error"]
        assert len(errors) == 1
        assert "xxx.ch" in errors[0].mensagem


class TestAppreCompilerCCode:
    """v0.8.1 regression: advpls escreve erros em <basename>.errprw com formato
    'APPRE41.PRW(N) Error CXXXX <mensagem>'. Esse pattern deve ser reconhecido
    e ``codigo`` populado."""

    def test_c2090_include_missing(self) -> None:
        raw = (FIXTURES / "appre_errprw_c2090.txt").read_text(encoding="utf-8")
        matched, _ = parse_diagnostics(
            stdout=raw, stderr="", mode="appre",
            requested_files=[Path("FOO.PRW")],
            force_arquivo=Path("FOO.PRW"),
        )
        errors = [d for d in matched if d.severidade == "error"]
        assert len(errors) == 1
        d = errors[0]
        assert d.codigo == "C2090"
        assert "PRTOPDEF.CH" in d.mensagem
        # force_arquivo: nome do fonte real, não APPRE41.PRW (que vem no raw)
        assert d.arquivo == "FOO.PRW"

    def test_c2006_lowercase_appre41(self) -> None:
        raw = (FIXTURES / "appre_errprw_c2006.txt").read_text(encoding="utf-8")
        matched, _ = parse_diagnostics(
            stdout=raw, stderr="", mode="appre",
            requested_files=[Path("BAR.PRW")],
            force_arquivo=Path("BAR.PRW"),
        )
        errors = [d for d in matched if d.severidade == "error"]
        assert len(errors) == 1
        assert errors[0].codigo == "C2006"
        assert errors[0].linha == 4

    def test_force_arquivo_overrides_match(self) -> None:
        """force_arquivo SEMPRE vence sobre o arquivo capturado no pattern."""
        raw = "outro.prw(99) error: bad"
        matched, _ = parse_diagnostics(
            stdout=raw, stderr="", mode="cli",
            requested_files=[Path("foo.prw")],
            force_arquivo=Path("foo.prw"),
        )
        assert len(matched) == 1
        assert matched[0].arquivo == "foo.prw"
