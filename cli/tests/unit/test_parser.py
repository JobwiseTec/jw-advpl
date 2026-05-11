"""Testes de cli/plugadvpl/parsing/parser.py."""
from __future__ import annotations

from pathlib import Path

from plugadvpl.parsing.parser import (
    add_function_ranges,
    extract_functions,
    extract_params,
    extract_perguntas,
    extract_tables,
    read_file,
)


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


class TestExtractTables:
    def test_dbselectarea(self) -> None:
        src = 'DbSelectArea("SA1")'
        tables = extract_tables(src)
        assert "SA1" in tables["read"]

    def test_alias_arrow_read(self) -> None:
        src = "cNome := SA1->A1_NOME"
        tables = extract_tables(src)
        assert "SA1" in tables["read"]

    def test_xfilial_read(self) -> None:
        src = 'cFil := xFilial("SC5")'
        tables = extract_tables(src)
        assert "SC5" in tables["read"]

    def test_reclock_write(self) -> None:
        src = 'RecLock("SA1", .T.)\nReplace A1_NOME With "X"\nMsUnlock()'
        tables = extract_tables(src)
        assert "SA1" in tables["reclock"]
        assert "SA1" in tables["write"]

    def test_dbappend_write(self) -> None:
        src = "SA1->(dbAppend())"
        tables = extract_tables(src)
        assert "SA1" in tables["write"]

    def test_custom_table_za1(self) -> None:
        src = "DbSelectArea('ZA1')"
        tables = extract_tables(src)
        assert "ZA1" in tables["read"]

    def test_ignores_invalid_table_codes(self) -> None:
        src = 'cFoo := "ABC"->bar'
        tables = extract_tables(src)
        assert "ABC" not in tables["read"]  # ABC não é código Protheus válido


class TestExtractParams:
    def test_supergetmv(self) -> None:
        src = 'cVal := SuperGetMV("MV_LOCALIZA", .F., "01")'
        params = extract_params(src)
        names = {(p["nome"], p["modo"]) for p in params}
        assert ("MV_LOCALIZA", "read") in names

    def test_getmv(self) -> None:
        src = 'cMoeda := GetMv("MV_SIMB1")'
        params = extract_params(src)
        names = {p["nome"] for p in params}
        assert "MV_SIMB1" in names

    def test_getnewpar(self) -> None:
        src = 'cVal := GetNewPar("MV_FOO", "default")'
        params = extract_params(src)
        names = {(p["nome"], p["default_decl"]) for p in params}
        assert ("MV_FOO", "default") in names

    def test_putmv_write(self) -> None:
        src = 'PutMV("MV_X", "newvalue")'
        params = extract_params(src)
        names = {(p["nome"], p["modo"]) for p in params}
        assert ("MV_X", "write") in names


class TestExtractPerguntas:
    def test_pergunte(self) -> None:
        src = 'Pergunte("FAT050", .F.)'
        assert "FAT050" in extract_perguntas(src)

    def test_fwgetsx1(self) -> None:
        src = 'aGrp := FWGetSX1("FIN001")'
        assert "FIN001" in extract_perguntas(src)

    def test_ignores_in_comment(self) -> None:
        src = '// Pergunte("FAKE")\nPergunte("REAL", .F.)'
        result = extract_perguntas(src)
        assert "REAL" in result
        assert "FAKE" not in result
