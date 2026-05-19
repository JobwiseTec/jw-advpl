"""Testes de plugadvpl.compile_probe (v0.8.11 fix bug 2)."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.compile_probe import probe_appserver_log


_TYPICAL_LOG = """\
[2025-10-03 08:15:32] AppServer starting
[2025-10-03 08:15:32] Loading configuration
[2025-10-03 08:15:32] * TOTVS - Build 7.00.240223P - Oct 3 2025
[2025-10-03 08:15:33] Listening on port 1234
"""


class TestResolveLogPath:
    def test_direct_log_file(self, tmp_path: Path) -> None:
        log = tmp_path / "protheus.log"
        log.write_text(_TYPICAL_LOG, encoding="cp1252")
        result = probe_appserver_log(log)
        assert result is not None
        assert result.log_path == log

    def test_finds_log_in_root_log_dir(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "log"
        log_dir.mkdir()
        log = log_dir / "protheus.log"
        log.write_text(_TYPICAL_LOG, encoding="cp1252")
        result = probe_appserver_log(tmp_path)
        assert result is not None
        assert result.log_path == log

    def test_finds_log_in_bin_appserver_log(self, tmp_path: Path) -> None:
        log_dir = tmp_path / "bin" / "Appserver" / "log"
        log_dir.mkdir(parents=True)
        log = log_dir / "protheus.log"
        log.write_text(_TYPICAL_LOG, encoding="cp1252")
        result = probe_appserver_log(tmp_path)
        assert result is not None

    def test_returns_none_if_not_found(self, tmp_path: Path) -> None:
        assert probe_appserver_log(tmp_path) is None


class TestParseBuild:
    def test_extracts_build_and_date(self, tmp_path: Path) -> None:
        log = tmp_path / "protheus.log"
        log.write_text(_TYPICAL_LOG, encoding="cp1252")
        result = probe_appserver_log(log)
        assert result is not None
        assert result.build == "7.00.240223P"
        assert result.build_date == "Oct 3 2025"

    def test_log_without_build_line_returns_empty(self, tmp_path: Path) -> None:
        log = tmp_path / "protheus.log"
        log.write_text("just some random log lines\nno totvs here\n", encoding="cp1252")
        result = probe_appserver_log(log)
        assert result is not None
        assert result.build == ""
        assert result.build_date == ""

    def test_handles_cp1252_bytes(self, tmp_path: Path) -> None:
        """Bytes acentuados de cp1252 não devem travar a leitura."""
        log = tmp_path / "protheus.log"
        log.write_bytes(
            "Configura\xe7\xe3o carregada\n".encode("cp1252") +
            "* TOTVS - Build 7.00.240223P - Oct 3 2025\n".encode("cp1252")
        )
        result = probe_appserver_log(log)
        assert result is not None
        assert result.build == "7.00.240223P"

    def test_respects_max_lines(self, tmp_path: Path) -> None:
        """Build line após max_lines não é encontrada (proteção contra GB de log)."""
        log = tmp_path / "protheus.log"
        content = "noise\n" * 10
        content += "* TOTVS - Build 7.00.240223P - Oct 3 2025\n"
        log.write_text(content, encoding="cp1252")
        result = probe_appserver_log(log, max_lines=5)
        assert result is not None
        assert result.build == ""
        assert result.lines_scanned == 6
