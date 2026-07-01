"""BP-009/010/011 — guard de sintaxe ADVPL (issue #176, porta determinística).

Productiza o guard determinístico do PoC de geração de código: pega o que o lint
ainda não cobria — keyword de outra linguagem (`Then`/`EndFunction`) e o limite de
10 chars do identificador em `.prw`. 100% determinístico, sem LLM. `strip_advpl`
evita falso-positivo em string/comentário (o pulo do gato p/ não quebrar base real).
"""

from __future__ import annotations

from typing import Any

from plugadvpl.parsing.lint import lint_source
from plugadvpl.parsing.parser import (
    add_function_ranges,
    extract_functions,
    extract_sql_embedado,
)


def _parsed_for(content: str, arquivo: str = "test.prw") -> dict[str, Any]:
    funcs = add_function_ranges(extract_functions(content), content)
    return {"arquivo": arquivo, "funcoes": funcs, "sql_embedado": extract_sql_embedado(content)}


def _ids(findings: list[dict[str, Any]]) -> list[str]:
    return [f["regra_id"] for f in findings]


def _by(findings: list[dict[str, Any]], rid: str) -> list[dict[str, Any]]:
    return [f for f in findings if f["regra_id"] == rid]


# --- BP-009: `Then` em condicional (ADVPL usa If/EndIf) ----------------------
class TestBP009Then:
    def test_positive_then_in_conditional(self) -> None:
        src = "User Function FOO()\n  If nX > 0 Then\n    nX := 1\n  EndIf\nReturn\n"
        f = _by(lint_source(_parsed_for(src), src), "BP-009")
        assert len(f) == 1
        assert f[0]["severidade"] == "warning"

    def test_negative_if_without_then(self) -> None:
        src = "User Function FOO()\n  If nX > 0\n    nX := 1\n  EndIf\nReturn\n"
        assert "BP-009" not in _ids(lint_source(_parsed_for(src), src))

    def test_negative_then_in_string(self) -> None:
        src = 'User Function FOO()\n  cMsg := "press Then to continue"\nReturn\n'
        assert "BP-009" not in _ids(lint_source(_parsed_for(src), src))

    def test_negative_then_in_comment(self) -> None:
        src = "User Function FOO()\n  // and Then do this\n  nX := 1\nReturn\n"
        assert "BP-009" not in _ids(lint_source(_parsed_for(src), src))

    def test_negative_sql_case_when_then(self) -> None:
        # `THEN` de SQL `CASE WHEN ... THEN` (BeginSql) NÃO é If ADVPL — não flag.
        src = (
            "User Function FOO()\n"
            "  BeginSql Alias 'TRB'\n"
            "    SELECT CASE WHEN A1_COD = ' ' THEN 1 ELSE 2 END AS TIPO\n"
            "    FROM %table:SA1% SA1\n"
            "  EndSql\n"
            "Return\n"
        )
        assert "BP-009" not in _ids(lint_source(_parsed_for(src), src))

    def test_positive_elseif_then(self) -> None:
        src = "User Function FOO()\n  If nX > 0\n  ElseIf nX < 0 Then\n  EndIf\nReturn\n"
        assert "BP-009" in _ids(lint_source(_parsed_for(src), src))


# --- BP-010: `EndFunction` (ADVPL fecha com Return) --------------------------
class TestBP010EndFunction:
    def test_positive_endfunction(self) -> None:
        src = "User Function FOO()\n  nX := 1\nEndFunction\n"
        f = _by(lint_source(_parsed_for(src), src), "BP-010")
        assert len(f) == 1
        assert f[0]["severidade"] == "warning"

    def test_negative_return(self) -> None:
        src = "User Function FOO()\n  nX := 1\nReturn\n"
        assert "BP-010" not in _ids(lint_source(_parsed_for(src), src))

    def test_negative_endfunction_in_comment(self) -> None:
        src = "User Function FOO()\n  // nao usar EndFunction aqui\nReturn\n"
        assert "BP-010" not in _ids(lint_source(_parsed_for(src), src))


# --- BP-011: limite de 10 chars do identificador em .prw --------------------
class TestBP011TenCharLimit:
    def test_positive_user_function_over_8_in_prw(self) -> None:
        # 'ProcessAll' = 10 chars > 8 (U_ProcessAll = 12 > 10 do compilador)
        src = "User Function ProcessAll()\nReturn\n"
        f = _by(lint_source(_parsed_for(src, "x.prw"), src), "BP-011")
        assert len(f) == 1
        assert f[0]["severidade"] == "info"
        assert f[0]["funcao"] == "PROCESSALL"

    def test_negative_user_function_8_or_less(self) -> None:
        src = "User Function MTA010()\nReturn\n"  # 6 chars
        assert "BP-011" not in _ids(lint_source(_parsed_for(src, "x.prw"), src))

    def test_boundary_user_function_exactly_8_ok(self) -> None:
        src = "User Function ProcOrde()\nReturn\n"  # 8 chars -> ok
        assert "BP-011" not in _ids(lint_source(_parsed_for(src, "x.prw"), src))

    def test_negative_long_name_in_tlpp_exempt(self) -> None:
        # .tlpp NAO tem limite de 10
        src = "User Function ProcessAll()\nReturn\n"
        assert "BP-011" not in _ids(lint_source(_parsed_for(src, "x.tlpp"), src))

    def test_static_function_over_10(self) -> None:
        # 'HelperRoutine' = 13 > 10 (sem U_, limite cheio de 10)
        src = "Static Function HelperRoutine()\nReturn\n"
        f = _by(lint_source(_parsed_for(src, "x.prw"), src), "BP-011")
        assert len(f) == 1

    def test_static_function_10_or_less_ok(self) -> None:
        src = "Static Function HelperFn()\nReturn\n"  # 8 chars
        assert "BP-011" not in _ids(lint_source(_parsed_for(src, "x.prw"), src))
