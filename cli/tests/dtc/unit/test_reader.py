"""Testes do módulo reader."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from plugadvpl.dtc import reader
from plugadvpl.dtc.faircom import FieldDef, Layout


def _force_ctree(mocker):
    """Faz extract_layout devolver None → caminho c-tree (fallback)."""
    mocker.patch("plugadvpl.dtc.reader.faircom.extract_layout", return_value=None)


def _mock_faircom(mocker, conn, table="dtcat_sample01"):
    """Mocka o trio register/connect/unregister do caminho c-tree."""
    _force_ctree(mocker)
    target = Path("/fake/dbs") / "sample01.dtc"
    mocker.patch("plugadvpl.dtc.reader.faircom.register_isam", return_value=(target, table))
    mocker.patch("plugadvpl.dtc.reader.faircom.connect", return_value=conn)
    unreg = mocker.patch("plugadvpl.dtc.reader.faircom.unregister_isam")
    return unreg, target, table


def _protheus_layout() -> Layout:
    return Layout(
        record_length=16,
        is_fixed=True,
        fields=[
            FieldDef("D_E_L_E_T_E_D", 0, 1, "FSTRING"),
            FieldDef("R_E_C_N_O", 4, 4, "INT4U"),
            FieldDef("NOME", 8, 8, "FSTRING"),
        ],
    )


def _protheus_bytes() -> bytes:
    def rec(flag, recno, nome):
        b = bytearray(16)
        b[0:1] = flag
        b[4:8] = struct.pack("<I", recno)
        b[8:16] = nome.ljust(8)[:8]
        return bytes(b)

    return b"\xff" * 16 + rec(b" ", 1, b"Joao") + rec(b"*", 2, b"Maria")


class TestColumnsFromDescription:
    def test_maps_db_api_description(self) -> None:
        desc = [
            ("cod", int, None, 4, 10, 0, 1),
            ("nome", str, None, 16, 15, 0, 0),
        ]
        cols = reader._columns_from_description(desc)
        assert [c.name for c in cols] == ["cod", "nome"]
        assert cols[0].type == "int"
        assert cols[0].size == 10
        assert cols[0].nullable is True
        assert cols[1].nullable is False

    def test_handles_empty(self) -> None:
        assert reader._columns_from_description(None) == []


class TestParserPath:
    """Caminho principal: arquivo com assinatura Protheus → parser DODA direto."""

    def test_read_all_uses_parser(self, tmp_path: Path, mocker) -> None:
        arquivo = tmp_path / "sa1.dtc"
        arquivo.write_bytes(_protheus_bytes())
        mocker.patch("plugadvpl.dtc.reader.faircom.extract_layout", return_value=_protheus_layout())
        # nenhum mock de c-tree: se cair no fallback, quebra
        no_ctree = mocker.patch(
            "plugadvpl.dtc.reader._open_dtc", side_effect=AssertionError("usou c-tree")
        )

        cols, rows = reader.read_all(arquivo)

        assert cols == ["D_E_L_E_T_E_D", "R_E_C_N_O", "NOME"]
        assert [r[2] for r in rows] == ["Joao"]  # Maria deletada filtrada
        no_ctree.assert_not_called()

    def test_read_info_uses_parser(self, tmp_path: Path, mocker) -> None:
        from rich.console import Console

        arquivo = tmp_path / "sa1.dtc"
        arquivo.write_bytes(_protheus_bytes())
        mocker.patch("plugadvpl.dtc.reader.faircom.extract_layout", return_value=_protheus_layout())

        info = reader.read_info(arquivo, sample=5, console=Console(record=True))

        assert info.table == "sa1"
        assert info.row_count == 1  # só Joao (Maria deletada)
        assert [c.name for c in info.columns] == ["D_E_L_E_T_E_D", "R_E_C_N_O", "NOME"]

    def test_non_protheus_layout_falls_back(self, tmp_path: Path, mocker) -> None:
        # layout fixed mas sem flag de delete no offset 0 → não é Protheus
        layout = Layout(
            record_length=8,
            is_fixed=True,
            fields=[FieldDef("ID", 0, 4, "INT4U"), FieldDef("X", 4, 4, "INT4U")],
        )
        arquivo = tmp_path / "x.dtc"
        arquivo.write_bytes(b"\x00" * 8)
        mocker.patch("plugadvpl.dtc.reader.faircom.extract_layout", return_value=layout)
        cursor = mocker.MagicMock()
        cursor.description = [("ID",)]
        cursor.fetchall.return_value = []
        conn = mocker.MagicMock()
        conn.cursor.return_value = cursor
        # register/connect/unregister (sem _force_ctree, pois layout já é não-protheus)
        target = tmp_path / "x.dtc"
        mocker.patch("plugadvpl.dtc.reader.faircom.register_isam", return_value=(target, "t"))
        mocker.patch("plugadvpl.dtc.reader.faircom.connect", return_value=conn)
        mocker.patch("plugadvpl.dtc.reader.faircom.unregister_isam")

        cols, _ = reader.read_all(arquivo)
        assert cols == ["ID"]


class TestReadInfoCtree:
    def test_missing_file_exits(self, tmp_path: Path) -> None:
        from rich.console import Console

        with pytest.raises(SystemExit):
            reader.read_info(tmp_path / "ghost.dtc", sample=5, console=Console())

    def test_registers_queries_and_renders(self, tmp_path: Path, mocker) -> None:
        from rich.console import Console

        arquivo = tmp_path / "sample01.dtc"
        arquivo.write_bytes(b"\x00")

        cursor = mocker.MagicMock()
        cursor.fetchone.return_value = (42,)
        cursor.description = [
            ("FIELD_CODE", str, None, 10, 10, 0, 0),
            ("FIELD_LABEL", str, None, 30, 30, 0, 1),
        ]
        cursor.fetchmany.return_value = [("CUST001", "Cod")]
        conn = mocker.MagicMock()
        conn.cursor.return_value = cursor
        unreg, target, table = _mock_faircom(mocker, conn)

        info = reader.read_info(arquivo, sample=2, console=Console(record=True))

        assert info.table == table
        assert info.row_count == 42
        assert len(info.columns) == 2
        unreg.assert_called_once_with(target, table)


class TestReadAllCtree:
    def test_filters_deleted_by_default(self, tmp_path: Path, mocker) -> None:
        arquivo = tmp_path / "sample.dtc"
        arquivo.write_bytes(b"\x00")
        cursor = mocker.MagicMock()
        cursor.description = [("A",), ("D_E_L_E_T_",)]
        cursor.fetchall.return_value = [(1, " ")]
        conn = mocker.MagicMock()
        conn.cursor.return_value = cursor
        unreg, target, table = _mock_faircom(mocker, conn)

        cols, _rows = reader.read_all(arquivo)

        assert cols == ["A", "D_E_L_E_T_"]
        executed = cursor.execute.call_args[0][0]
        assert "D_E_L_E_T_" in executed
        unreg.assert_called_once_with(target, table)

    def test_keep_deleted_omits_filter(self, tmp_path: Path, mocker) -> None:
        arquivo = tmp_path / "sample.dtc"
        arquivo.write_bytes(b"\x00")
        cursor = mocker.MagicMock()
        cursor.description = [("A",)]
        cursor.fetchall.return_value = []
        conn = mocker.MagicMock()
        conn.cursor.return_value = cursor
        _mock_faircom(mocker, conn)

        reader.read_all(arquivo, keep_deleted=True)

        executed = cursor.execute.call_args[0][0]
        assert "D_E_L_E_T_" not in executed

    def test_unregister_runs_even_on_error(self, tmp_path: Path, mocker) -> None:
        arquivo = tmp_path / "sample.dtc"
        arquivo.write_bytes(b"\x00")
        cursor = mocker.MagicMock()
        cursor.execute.side_effect = RuntimeError("boom")
        conn = mocker.MagicMock()
        conn.cursor.return_value = cursor
        unreg, target, table = _mock_faircom(mocker, conn)

        with pytest.raises(RuntimeError):
            reader.read_all(arquivo)

        unreg.assert_called_once_with(target, table)
        conn.close.assert_called_once()
