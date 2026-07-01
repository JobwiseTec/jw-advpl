"""Testes do módulo exporter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plugadvpl.dtc import exporter
from plugadvpl.dtc.exporter import ExportFormat


class TestDecodeCell:
    def test_decodes_cp1252_bytes(self) -> None:
        assert exporter._decode_cell(b"C\xf3digo") == "Código"

    def test_falls_back_to_latin1_on_failure(self) -> None:
        # Sequência inválida em cp1252: byte 0x81 não existe lá
        result = exporter._decode_cell(b"\x81abc")
        assert isinstance(result, str)

    def test_strips_trailing_whitespace_from_str(self) -> None:
        assert exporter._decode_cell("foo     ") == "foo"

    def test_passes_through_non_text(self) -> None:
        assert exporter._decode_cell(42) == 42
        assert exporter._decode_cell(None) is None
        assert exporter._decode_cell(3.14) == 3.14


class TestToDataFrame:
    def test_decodes_bytes_columns(self, sample_rows: tuple[list[str], list[tuple]]) -> None:
        columns, rows = sample_rows
        df = exporter._to_dataframe(columns, rows)
        assert df.shape == (3, 5)
        assert df.loc[0, "FIELD_LABEL"] == "Código"
        assert df.loc[1, "FIELD_LABEL"] == "Nome"

    def test_strips_trailing_spaces_from_strings(
        self, sample_rows: tuple[list[str], list[tuple]]
    ) -> None:
        columns, rows = sample_rows
        df = exporter._to_dataframe(columns, rows)
        assert df.loc[0, "FIELD_CODE"] == "CUST_ID"

    def test_handles_empty_rows(self) -> None:
        df = exporter._to_dataframe(["A", "B"], [])
        assert df.shape == (0, 2)
        assert list(df.columns) == ["A", "B"]


class TestImportPandasGuard:
    def test_mensagem_amigavel_quando_extra_ausente(self, mocker) -> None:
        # Simula o extra 'dtc' nao instalado: import pandas -> ModuleNotFoundError.
        import builtins

        real_import = builtins.__import__

        def fake_import(name: str, *args: object, **kwargs: object):
            if name == "pandas":
                raise ModuleNotFoundError("No module named 'pandas'")
            return real_import(name, *args, **kwargs)

        mocker.patch("builtins.__import__", side_effect=fake_import)
        with pytest.raises(SystemExit) as exc:
            exporter._import_pandas()
        assert "plugadvpl[dtc]" in str(exc.value)


class TestExportFile:
    @pytest.fixture
    def mocked_reader(self, mocker, sample_rows: tuple[list[str], list[tuple]]):
        return mocker.patch("plugadvpl.dtc.exporter.read_all", return_value=sample_rows)

    def test_export_csv(self, mocked_reader, tmp_path: Path) -> None:
        arquivo = tmp_path / "SAMPLE.dtc"
        arquivo.write_bytes(b"\x00")
        destino = tmp_path / "saida.csv"

        result = exporter.export_file(arquivo, ExportFormat.csv, destino)

        assert result == destino
        assert destino.exists()
        content = destino.read_text(encoding="utf-8-sig")
        assert "FIELD_CODE" in content
        assert "Código" in content

    def test_export_json(self, mocked_reader, tmp_path: Path) -> None:
        arquivo = tmp_path / "SAMPLE.dtc"
        arquivo.write_bytes(b"\x00")
        destino = tmp_path / "saida.json"

        exporter.export_file(arquivo, ExportFormat.json, destino)

        assert destino.exists()
        data = json.loads(destino.read_text(encoding="utf-8"))
        assert isinstance(data, list)
        assert len(data) == 3
        assert data[0]["FIELD_LABEL"] == "Código"

    def test_export_xlsx(self, mocked_reader, tmp_path: Path) -> None:
        pytest.importorskip("openpyxl")
        arquivo = tmp_path / "SAMPLE.dtc"
        arquivo.write_bytes(b"\x00")
        destino = tmp_path / "saida.xlsx"

        exporter.export_file(arquivo, ExportFormat.xlsx, destino)

        assert destino.exists()
        assert destino.stat().st_size > 0

    def test_default_output_uses_source_stem(self, mocked_reader, tmp_path: Path) -> None:
        arquivo = tmp_path / "SAMPLE.dtc"
        arquivo.write_bytes(b"\x00")

        result = exporter.export_file(arquivo, ExportFormat.csv, None)

        assert result == arquivo.with_suffix(".csv")
        assert result.exists()

    def test_missing_source_exits(self, tmp_path: Path) -> None:
        missing = tmp_path / "x.dtc"
        with pytest.raises(SystemExit):
            exporter.export_file(missing, ExportFormat.csv, None)

    def test_keep_deleted_passed_to_reader(
        self, mocker, tmp_path: Path, sample_rows: tuple[list[str], list[tuple]]
    ) -> None:
        spy = mocker.patch("plugadvpl.dtc.exporter.read_all", return_value=sample_rows)
        arquivo = tmp_path / "SAMPLE.dtc"
        arquivo.write_bytes(b"\x00")

        exporter.export_file(arquivo, ExportFormat.csv, tmp_path / "o.csv", keep_deleted=True)

        assert spy.call_args.kwargs["keep_deleted"] is True


class TestExportFormat:
    def test_format_values(self) -> None:
        assert ExportFormat.csv.value == "csv"
        assert ExportFormat.json.value == "json"
        assert ExportFormat.xlsx.value == "xlsx"

    def test_all_formats_have_distinct_values(self) -> None:
        values = {f.value for f in ExportFormat}
        assert len(values) == 3
