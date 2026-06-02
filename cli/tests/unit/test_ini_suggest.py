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
            [{"section": "General", "key": "ConnString", "expected": "server=X;db=Y;user=Z"}],
        )
        # Valor novo preservado integralmente (com `;` e `=`)
        assert "ConnString=server=X;db=Y;user=Z" in out
        # Anterior preservado no comment (não corta no `;`)
        assert "valor anterior: server=A;db=B;user=C" in out

    def test_unknown_key_commented_with_revisar(self) -> None:
        """Chave fora do catálogo é comentada com [REVISAR], preservando valor."""
        original = "[protheus]\ntomate=1\nSourcePath=/apo\n"
        out = generate_suggested_ini(
            original,
            [],
            unknown_keys=[{"section": "protheus", "key_name": "tomate"}],
        )
        assert ";tomate=1  ; [REVISAR] chave nao reconhecida" in out
        # chave reconhecida intocada
        assert "SourcePath=/apo" in out

    def test_warning_missing_not_injected(self) -> None:
        """Warning ausente NÃO é injetado (só crítico ausente vira [ADICIONADO])."""
        original = "[General]\nConsoleLog=1\n"
        out = generate_suggested_ini(
            original,
            [
                {
                    "section": "General",
                    "key": "LogTimeStamp",
                    "expected": "1",
                    "severidade": "warning",
                }
            ],
        )
        assert "[ADICIONADO]" not in out
        assert "LogTimeStamp" not in out

    def test_warning_mismatch_still_corrected(self) -> None:
        """Warning PRESENTE com valor divergente ainda recebe [CORRECAO]."""
        original = "[General]\nLogTimeStamp=0\n"
        out = generate_suggested_ini(
            original,
            [
                {
                    "section": "General",
                    "key": "LogTimeStamp",
                    "expected": "1",
                    "severidade": "warning",
                }
            ],
        )
        assert "LogTimeStamp=1  ; [CORRECAO] valor anterior: 0" in out

    def test_critical_missing_injected_with_severidade(self) -> None:
        """Crítico ausente é injetado mesmo com severidade explícita."""
        original = "[General]\nConsoleLog=1\n"
        out = generate_suggested_ini(
            original,
            [
                {
                    "section": "General",
                    "key": "MaxStringSize",
                    "expected": "10",
                    "severidade": "critical",
                }
            ],
        )
        assert "MaxStringSize=10  ; [ADICIONADO]" in out

    def test_placeholder_value_with_description_in_comment(self) -> None:
        """Crítico obrigatório sem valor → ``<CONFIGURAR>``; a descrição da regra
        vai no comentário ``[ADICIONADO]``."""
        original = "[protheus_cmp]\nRootPath=/data\n"
        out = generate_suggested_ini(
            original,
            [
                {
                    "section": "protheus_cmp",
                    "key": "SourcePath",
                    "expected": "<CONFIGURAR>",
                    "severidade": "critical",
                    "descricao": "Diretório dos fontes RPO.",
                }
            ],
        )
        assert "SourcePath=<CONFIGURAR>  ; [ADICIONADO] Diretório dos fontes RPO." in out

    def test_addition_without_description_trims_trailing_space(self) -> None:
        """Sem descrição, o comentário termina em ``[ADICIONADO]`` (sem espaço sobrando)."""
        original = "[General]\nConsoleLog=1\n"
        out = generate_suggested_ini(
            original,
            [
                {
                    "section": "General",
                    "key": "MaxStringSize",
                    "expected": "10",
                    "severidade": "critical",
                    "descricao": "",
                }
            ],
        )
        assert "MaxStringSize=10  ; [ADICIONADO]" in out
        assert "[ADICIONADO] " not in out  # sem espaço pendurado

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
