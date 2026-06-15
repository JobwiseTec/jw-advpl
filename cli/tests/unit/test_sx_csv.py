"""Unit dos parsers SX — colunas novas (Sub-projeto 1 do spec SX completo).

Ver docs/superpowers/specs/2026-06-15-sx-completo-chave-indice-design.md.
"""

from __future__ import annotations

from pathlib import Path

from plugadvpl.parsing.sx_csv import parse_sx2, parse_sx3, parse_sx9


class TestParseSx2NewColumns:
    def test_extracts_unico_modoun_modoemp(self, tmp_path: Path) -> None:
        f = tmp_path / "sx2.csv"
        f.write_text(
            '"X2_CHAVE","X2_NOME","X2_MODO","X2_UNICO","X2_MODOUN","X2_MODOEMP"\n'
            '"ZX1","Pedidos","C","ZX1_FILIAL+ZX1_NUM","1","2"\n',
            encoding="utf-8",
        )
        r = parse_sx2(f)[0]
        assert r["unico"] == "ZX1_FILIAL+ZX1_NUM"
        assert r["modo_unico"] == "1"
        assert r["modo_emp"] == "2"

    def test_missing_columns_default_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "sx2.csv"
        f.write_text('"X2_CHAVE","X2_NOME","X2_MODO"\n"ZX1","Pedidos","C"\n', encoding="utf-8")
        r = parse_sx2(f)[0]
        assert r["unico"] == ""
        assert r["modo_unico"] == ""
        assert r["modo_emp"] == ""


class TestParseSx3NewColumns:
    def test_extracts_ordem_inibrw_relacao(self, tmp_path: Path) -> None:
        f = tmp_path / "sx3.csv"
        # X3_INIT presente E X3_RELACAO presente: 'relacao' deve capturar X3_RELACAO
        # mesmo com X3_INIT (antes era perdido — inicializador prioriza X3_INIT).
        f.write_text(
            '"X3_ARQUIVO","X3_CAMPO","X3_TIPO","X3_ORDEM","X3_INIBRW","X3_INIT","X3_RELACAO"\n'
            '"ZX1","ZX1_STATUS","C","05","S","\'1\'","POSICIONE(\'ZX2\')"\n',
            encoding="utf-8",
        )
        r = parse_sx3(f)[0]
        assert r["ordem"] == "05"
        assert r["inibrw"] == "S"
        assert r["relacao"] == "POSICIONE('ZX2')"
        assert r["inicializador"] == "'1'"  # X3_INIT preservado, distinto de relacao

    def test_missing_columns_default_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "sx3.csv"
        f.write_text(
            '"X3_ARQUIVO","X3_CAMPO","X3_TIPO"\n"ZX1","ZX1_STATUS","C"\n',
            encoding="utf-8",
        )
        r = parse_sx3(f)[0]
        assert r["ordem"] == ""
        assert r["inibrw"] == ""
        assert r["relacao"] == ""


class TestParseSx9NewColumns:
    def test_extracts_usefil_vinfil_chvfor(self, tmp_path: Path) -> None:
        f = tmp_path / "sx9.csv"
        f.write_text(
            '"X9_DOM","X9_IDENT","X9_CDOM","X9_USEFIL","X9_VINFIL","X9_CHVFOR"\n'
            '"ZX1","001","ZX2","S","N","ZX2_FILIAL+ZX2_NUM"\n',
            encoding="utf-8",
        )
        r = parse_sx9(f)[0]
        assert r["usa_filial"] == "S"
        assert r["vincula_filial"] == "N"
        assert r["chave_estrangeira"] == "ZX2_FILIAL+ZX2_NUM"

    def test_missing_columns_default_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "sx9.csv"
        f.write_text('"X9_DOM","X9_IDENT","X9_CDOM"\n"ZX1","001","ZX2"\n', encoding="utf-8")
        r = parse_sx9(f)[0]
        assert r["usa_filial"] == ""
        assert r["vincula_filial"] == ""
        assert r["chave_estrangeira"] == ""
