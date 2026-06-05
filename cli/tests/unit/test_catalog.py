"""Testes de plugadvpl/catalog.py (#75) — ingest-tsv + catalog cross-query.

Fixtures 100% fictícias (sem conteúdo de cliente).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugadvpl.catalog import (
    _normalize_funcao_expr,
    _parse_filter,
    catalog_list,
    catalog_query,
    ingest_tsv,
    parse_tabular,
)
from plugadvpl.ingest import ingest


class TestParseTabular:
    def test_tsv_basico(self) -> None:
        raw = b"A\tB\n1\t2\n3\t4\n"
        cols, rows, enc, delim = parse_tabular(raw)
        assert cols == ["A", "B"]
        assert rows == [{"A": "1", "B": "2"}, {"A": "3", "B": "4"}]
        assert delim == "tab"

    def test_csv_sniff(self) -> None:
        cols, rows, _, delim = parse_tabular(b"A,B\n1,2\n")
        assert cols == ["A", "B"]
        assert delim == "csv"

    def test_delimiter_override(self) -> None:
        # conteúdo com vírgula mas forçado tab -> 1 coluna só
        cols, _, _, delim = parse_tabular(b"A,B\n1,2\n", delimiter="tab")
        assert cols == ["A,B"]
        assert delim == "tab"

    def test_encoding_cp1252(self) -> None:
        raw = "NOME\nJo\xe3o\n".encode("cp1252")  # ã em cp1252
        cols, rows, enc, _ = parse_tabular(raw)
        assert rows[0]["NOME"] == "João"

    def test_pula_linha_em_branco(self) -> None:
        _, rows, _, _ = parse_tabular(b"A\n1\n\n2\n")
        assert [r["A"] for r in rows] == ["1", "2"]

    def test_linha_curta_preenche_vazio(self) -> None:
        _, rows, _, _ = parse_tabular(b"A\tB\tC\n1\t2\n")
        assert rows[0] == {"A": "1", "B": "2", "C": ""}


class TestParseFilter:
    def test_igualdade(self) -> None:
        pred = _parse_filter("X='1'")
        assert pred({"X": "1"}) and not pred({"X": "2"})

    def test_diferente(self) -> None:
        pred = _parse_filter("X!='1'")
        assert pred({"X": "2"}) and not pred({"X": "1"})

    def test_and(self) -> None:
        pred = _parse_filter("X='1' AND Y='2'")
        assert pred({"X": "1", "Y": "2"}) and not pred({"X": "1", "Y": "9"})

    def test_or(self) -> None:
        pred = _parse_filter("X='1' OR X='2'")
        assert pred({"X": "2"}) and not pred({"X": "3"})

    def test_numerico(self) -> None:
        pred = _parse_filter("N>5")
        assert pred({"N": "10"}) and not pred({"N": "3"})

    def test_like(self) -> None:
        pred = _parse_filter("X LIKE '%abc%'")
        assert pred({"X": "xxABCxx"}) and not pred({"X": "zzz"})

    def test_invalido_levanta(self) -> None:
        with pytest.raises(ValueError, match="filtro inválido"):
            _parse_filter("DROP TABLE x")


class TestNormalizeFuncaoExpr:
    """#78: extrai o nome da função de uma expressão de chamada (sem args)."""

    def test_call_com_arg(self) -> None:
        assert _normalize_funcao_expr('U_MODxxx("88")') == "U_MODxxx"

    def test_call_multi_arg_com_espacos(self) -> None:
        assert _normalize_funcao_expr("U_MODxxx( 88, .T. )") == "U_MODxxx"

    def test_nome_puro(self) -> None:
        assert _normalize_funcao_expr("U_MODxxx") == "U_MODxxx"

    def test_literal_falso(self) -> None:
        assert _normalize_funcao_expr(".F.") == ".F."

    def test_vazio(self) -> None:
        assert _normalize_funcao_expr("") == ""


class TestCatalogIntegration:
    @pytest.fixture
    def db_cat(self, tmp_path: Path) -> sqlite3.Connection:
        src = tmp_path / "src"
        src.mkdir()
        (src / "ABCFN1.prw").write_bytes(b"User Function ABCFN1()\nReturn .T.\n")
        ingest(src, workers=0)
        conn = sqlite3.connect(str(src / ".plugadvpl" / "index.db"))
        # campos p/ decode-cbox (SZT.ZT_TIPO) — arquivo SZT.tsv resolve sx_table=SZT
        conn.execute(
            "INSERT INTO campos (tabela, campo, tipo, tamanho, cbox) "
            "VALUES ('SZT', 'ZT_TIPO', 'C', 1, '1=Fiscal;2=Financeiro')"
        )
        conn.commit()
        tsv = tmp_path / "SZT.tsv"
        tsv.write_bytes(
            b"ZT_COD\tZT_TIPO\tZT_FUNCAO\tZT_FILIAL\n"
            b"001\t1\tU_ABCFN1\t01\n002\t1\tU_ABCFN1\t01\n003\t2\t.F.\t02\n"
        )
        ingest_tsv(conn, tsv, "regras")
        return conn

    def test_list(self, db_cat: sqlite3.Connection) -> None:
        cats = catalog_list(db_cat)
        assert cats[0]["alias"] == "regras"
        assert cats[0]["row_count"] == 3
        assert cats[0]["sx_table"] == "SZT"  # resolvido pelo nome do arquivo

    def test_lista_tudo(self, db_cat: sqlite3.Connection) -> None:
        assert len(catalog_query(db_cat, "regras")) == 3

    def test_filter(self, db_cat: sqlite3.Connection) -> None:
        assert len(catalog_query(db_cat, "regras", filter_expr="ZT_FILIAL='01'")) == 2

    def test_group_count(self, db_cat: sqlite3.Connection) -> None:
        out = catalog_query(db_cat, "regras", group_by="ZT_TIPO", count=True)
        assert {r["ZT_TIPO"]: r["count"] for r in out} == {"1": 2, "2": 1}

    def test_group_count_multi(self, db_cat: sqlite3.Connection) -> None:
        out = catalog_query(db_cat, "regras", group_by="ZT_FILIAL,ZT_TIPO", count=True)
        assert any(r["ZT_FILIAL"] == "01" and r["ZT_TIPO"] == "1" and r["count"] == 2 for r in out)

    def test_decode_cbox(self, db_cat: sqlite3.Connection) -> None:
        out = catalog_query(db_cat, "regras", group_by="ZT_TIPO", count=True, decode_cbox=True)
        vals = {r["ZT_TIPO"] for r in out}
        assert "1=Fiscal" in vals and "2=Financeiro" in vals

    def test_resolve_callers(self, db_cat: sqlite3.Connection) -> None:
        out = catalog_query(db_cat, "regras", funcao_field="ZT_FUNCAO", resolve_callers=True)
        by = {r["ZT_FUNCAO"]: r for r in out}
        assert by["U_ABCFN1"]["fonte"] == "ABCFN1.prw"
        assert by["U_ABCFN1"]["count_no_dump"] == 2
        assert by[".F."]["fonte"].startswith("(literal")  # não resolve

    def test_resolve_callers_soma_args(
        self, db_cat: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # #78: U_ABCFN1("88") + ("89") + (...) somam no nome U_ABCFN1 -> ABCFN1.prw
        tsv = tmp_path / "comargs.tsv"
        tsv.write_bytes(
            b'ZT_FUNCAO\nU_ABCFN1("88")\nU_ABCFN1("89")\nU_ABCFN1( 01 , .T. )\n.F.\n'
        )
        ingest_tsv(db_cat, tsv, "comargs")
        by = {
            r["ZT_FUNCAO"]: r
            for r in catalog_query(db_cat, "comargs", funcao_field="ZT_FUNCAO", resolve_callers=True)
        }
        assert by["U_ABCFN1"]["fonte"] == "ABCFN1.prw"
        assert by["U_ABCFN1"]["count_no_dump"] == 3  # somou os 3 args distintos
        # a visão distinta-por-argumento continua disponível via --group-by
        distinto = catalog_query(db_cat, "comargs", group_by="ZT_FUNCAO", count=True)
        assert len(distinto) == 4  # 3 exprs distintas + .F.

    def test_alias_inexistente(self, db_cat: sqlite3.Connection) -> None:
        assert catalog_query(db_cat, "naoexiste") == []

    def test_reingest_sobrescreve(self, db_cat: sqlite3.Connection, tmp_path: Path) -> None:
        tsv2 = tmp_path / "outro.tsv"
        tsv2.write_bytes(b"A\tB\n9\t9\n")
        meta = ingest_tsv(db_cat, tsv2, "regras")
        assert meta["overwritten"] is True
        assert meta["rows"] == 1
        assert len(catalog_query(db_cat, "regras")) == 1

    def test_csv_utf8(self, db_cat: sqlite3.Connection, tmp_path: Path) -> None:
        csv_f = tmp_path / "x.csv"
        csv_f.write_text("A,B\nção,2\n", encoding="utf-8")
        meta = ingest_tsv(db_cat, csv_f, "csvtest")
        assert meta["delimiter"] == "csv"
        assert catalog_query(db_cat, "csvtest")[0]["A"] == "ção"
