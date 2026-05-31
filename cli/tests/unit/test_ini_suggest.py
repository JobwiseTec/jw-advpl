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

    def test_duplicate_key_in_section_both_corrected(self) -> None:
        """Documenta comportamento atual: chave duplicada na mesma seção
        recebe [CORRECAO] em AMBAS linhas. Protheus na prática mantém só
        a última definição, mas preservar todas evita perder histórico.
        Se quiser dedup, mude o behavior em ini_suggest E atualize esse teste.
        """
        original = "[General]\nMaxStringSize=1\nMaxStringSize=2\n"
        out = generate_suggested_ini(
            original, [{"section": "General", "key": "MaxStringSize", "expected": "10"}]
        )
        assert out.count("[CORRECAO]") == 2
        assert "MaxStringSize=10" in out
        assert "valor anterior: 1" in out
        assert "valor anterior: 2" in out

    def test_value_with_semicolon_and_equals_preserved(self) -> None:
        """Valor com `;` e `=` (connection string típica) deve ser corrigido
        sem corromper — `;` no comment `[CORRECAO]` é separado por dois espaços
        e Protheus parsers tipicamente cortam após o primeiro `;` fora de aspas.
        """
        original = "[General]\nConnString=server=A;db=B;user=C\n"
        out = generate_suggested_ini(
            original,
            [{"section": "General", "key": "ConnString",
              "expected": "server=X;db=Y;user=Z"}],
        )
        # Valor novo preservado integralmente (com `;` e `=`)
        assert "ConnString=server=X;db=Y;user=Z" in out
        # Anterior preservado no comment (não corta no `;`)
        assert "valor anterior: server=A;db=B;user=C" in out

    def test_commented_section_treated_as_absent(self) -> None:
        """`;[General]` é seção comentada; injeção cria seção nova no fim
        sem descomentar a original (conservador — user explicitamente
        comentou)."""
        original = ";[General]\n;ConsoleLog=1\n[Drivers]\nActive=1\n"
        out = generate_suggested_ini(
            original, [{"section": "General", "key": "ConsoleLog", "expected": "1"}]
        )
        # [General] novo criado no fim, não dentro da seção comentada
        assert ";[General]" in out  # comentada preservada
        assert "[General]" in out
        assert "ConsoleLog=1  ; [ADICIONADO]" in out
        # Ordem: commented section vem antes; nova [General] vem no fim
        idx_comment = out.find(";[General]")
        idx_active = out.rfind("[General]")
        assert idx_comment < idx_active
