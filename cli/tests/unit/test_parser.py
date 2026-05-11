"""Testes de cli/plugadvpl/parsing/parser.py."""
from __future__ import annotations

from pathlib import Path

from plugadvpl.parsing.parser import add_function_ranges, extract_functions, read_file


class TestReadFile:
    def test_cp1252_fast_path(self, tmp_path: Path) -> None:
        f = tmp_path / "test.prw"
        f.write_bytes("cNome := \"João\"".encode("cp1252"))
        content, encoding = read_file(f)
        assert content == 'cNome := "João"'
        assert encoding == "cp1252"

    def test_utf8_fallback(self, tmp_path: Path) -> None:
        f = tmp_path / "test.tlpp"
        # 字 (caracter chinês) não cabe em cp1252
        f.write_text('cNome := "字"', encoding="utf-8")
        content, encoding = read_file(f)
        assert "字" in content
        assert encoding == "utf-8"

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.prw"
        f.write_bytes(b"")
        content, encoding = read_file(f)
        assert content == ""


class TestExtractFunctions:
    def test_user_function(self) -> None:
        src = "User Function FATA050()\nReturn .T."
        result = extract_functions(src)
        names = [f["nome"] for f in result]
        assert "FATA050" in names

    def test_static_function(self) -> None:
        src = "Static Function ValidaCampo(cCpo)\nReturn .T."
        result = extract_functions(src)
        names = [f["nome"] for f in result]
        assert "ValidaCampo" in names

    def test_main_function(self) -> None:
        src = "Main Function JobX()\nReturn"
        result = extract_functions(src)
        names = [f["nome"] for f in result]
        assert "JobX" in names

    def test_wsmethod(self) -> None:
        src = "WSMETHOD GET clientes WSSERVICE Vendas\nReturn"
        result = extract_functions(src)
        names = [f["nome"] for f in result]
        assert "clientes" in names

    def test_method_class(self) -> None:
        src = "METHOD New(cArg) CLASS Pedido\nReturn Self"
        result = extract_functions(src)
        funs = [(f["nome"], f.get("classe")) for f in result]
        assert ("New", "Pedido") in funs

    def test_ignores_function_in_comment(self) -> None:
        # Confirma que strip_advpl está sendo aplicado antes
        src = "// User Function CommentedOut()\nUser Function Real()\nReturn"
        result = extract_functions(src)
        names = [f["nome"] for f in result]
        assert "Real" in names
        assert "CommentedOut" not in names

    def test_returns_line_numbers(self) -> None:
        src = "// linha 1\nUser Function Foo()\nReturn .T.\n\nUser Function Bar()\nReturn .F."
        result = extract_functions(src)
        by_name = {f["nome"]: f for f in result}
        assert by_name["Foo"]["linha_inicio"] == 2
        assert by_name["Bar"]["linha_inicio"] == 5


class TestAddFunctionRanges:
    def test_ranges_set_from_next_function(self) -> None:
        src = (
            "User Function A()\n"        # linha 1
            "  Local x := 1\n"            # 2
            "Return x\n"                  # 3
            "\n"                          # 4
            "User Function B()\n"        # 5
            "Return .T.\n"                # 6
        )
        funcs = extract_functions(src)
        funcs = add_function_ranges(funcs, src)
        by_name = {f["nome"]: f for f in funcs}
        assert by_name["A"]["linha_inicio"] == 1
        assert by_name["A"]["linha_fim"] == 4  # antes do header de B
        assert by_name["B"]["linha_inicio"] == 5
        assert by_name["B"]["linha_fim"] == 6  # última linha do arquivo
