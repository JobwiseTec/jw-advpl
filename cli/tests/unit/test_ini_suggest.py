"""Testes de cli/plugadvpl/parsing/ini_suggest.py (geração do INI sugerido)."""
from __future__ import annotations

from plugadvpl.parsing.ini_suggest import generate_suggested_ini


class TestGenerateSuggestedIni:
    def test_correction_replaces_value(self) -> None:
        original = "[General]\nMaxStringSize=1\n"
        out = generate_suggested_ini(
            original, [{"section": "General", "key": "MaxStringSize", "expected": "10"}]
        )
        assert "MaxStringSize=10" in out
        assert "[CORRECAO] valor anterior: 1" in out

    def test_addition_injected_in_existing_section_no_duplicate(self) -> None:
        original = "[JOB_WS]\nType=WEBEX\n\n[General]\nConsoleLog=1\n"
        out = generate_suggested_ini(
            original, [{"section": "JOB_WS", "key": "Main", "expected": "WS_START"}]
        )
        # Main injetado DENTRO do [JOB_WS] existente, sem recriar a seção
        assert out.count("[JOB_WS]") == 1
        assert "Main=WS_START  ; [ADICIONADO]" in out
        job_block = out.split("[General]")[0]
        assert "Main=WS_START" in job_block

    def test_addition_new_section_appended(self) -> None:
        original = "[General]\nConsoleLog=1\n"
        out = generate_suggested_ini(
            original, [{"section": "SSLConfigure", "key": "TLS1_2", "expected": "1"}]
        )
        assert "[SSLConfigure]" in out
        assert "TLS1_2=1  ; [ADICIONADO]" in out

    def test_preserves_comments_and_strips_bom(self) -> None:
        original = "﻿; comentario importante\n[General]\nKey=old\n"
        out = generate_suggested_ini(
            original, [{"section": "General", "key": "Key", "expected": "new"}]
        )
        assert not out.startswith("﻿")
        assert "; comentario importante" in out
        assert "Key=new" in out

    def test_no_items_returns_original_without_bom(self) -> None:
        original = "[General]\nKey=v\n"
        out = generate_suggested_ini(original, [])
        assert "Key=v" in out
        assert "[CORRECAO]" not in out
        assert "[ADICIONADO]" not in out

    def test_empty_expected_ignored(self) -> None:
        original = "[General]\nKey=v\n"
        out = generate_suggested_ini(
            original, [{"section": "General", "key": "Key", "expected": ""}]
        )
        assert "[CORRECAO]" not in out
