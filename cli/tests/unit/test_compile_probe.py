"""Testes de plugadvpl.compile_probe (v0.8.11 log + v0.8.12 network)."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from plugadvpl.compile_probe import (
    NetworkProbeResult,
    _build_validate_ini,
    _parse_validate_output,
    is_host_port,
    probe_appserver_log,
    probe_appserver_network,
)


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


# ---------------------------------------------------------------------------
# v0.8.12: network probe via advpls cli action=validate
# ---------------------------------------------------------------------------


class TestIsHostPort:
    def test_ipv4_port_true(self) -> None:
        assert is_host_port("192.168.1.1:1234") is True

    def test_hostname_port_true(self) -> None:
        assert is_host_port("localhost:1234") is True
        assert is_host_port("hml.cliente.com:5025") is True

    def test_hostname_with_dashes_true(self) -> None:
        assert is_host_port("my-server-01:1234") is True

    def test_log_path_false(self) -> None:
        assert is_host_port("D:/TOTVS/protheus/log/protheus.log") is False
        assert is_host_port("/opt/totvs/protheus.log") is False

    def test_no_colon_false(self) -> None:
        assert is_host_port("127.0.0.1") is False
        assert is_host_port("protheus.log") is False

    def test_port_not_digits_false(self) -> None:
        assert is_host_port("localhost:abc") is False
        assert is_host_port("host:1234x") is False

    def test_existing_path_wins_over_pattern(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """v0.8.12: se path existe, prefere filesystem mesmo com regex match.

        Não criamos o path real (`:` é inválido em filename no Windows) —
        mockamos ``Path.exists`` pra simular o cenário.
        """
        monkeypatch.setattr(Path, "exists", lambda self: True)
        assert is_host_port("host:1234") is False


class TestParseValidateOutput:
    def test_extracts_build_and_secure_from_canonical_line(self) -> None:
        out = "[LOG] Appserver detected with build version: 7.00.170117A and secure: 0\n"
        build, secure = _parse_validate_output(out)
        assert build == "7.00.170117A"
        assert secure is False

    def test_extracts_secure_true(self) -> None:
        out = "build: 7.00.240223P\nsecure: 1\n"
        build, secure = _parse_validate_output(out)
        assert build == "7.00.240223P"
        assert secure is True

    def test_secure_true_false_words(self) -> None:
        out = "build: 7.00\nsecure: true\n"
        _, secure = _parse_validate_output(out)
        assert secure is True

    def test_no_match_returns_empty(self) -> None:
        out = "ERROR: connection refused\n"
        build, secure = _parse_validate_output(out)
        assert build == ""
        assert secure is None

    def test_secure_missing_returns_none(self) -> None:
        out = "build: 7.00.240223P\n"
        build, secure = _parse_validate_output(out)
        assert build == "7.00.240223P"
        assert secure is None


class TestBuildValidateIni:
    def test_minimum_fields_present(self, tmp_path: Path) -> None:
        log = tmp_path / "validate.log"
        ini = _build_validate_ini("127.0.0.1", 1234, log)
        assert "[validate]" in ini
        assert "action=validate" in ini
        assert "server=127.0.0.1" in ini
        assert "port=1234" in ini
        assert "showConsoleOutput=true" in ini

    def test_log_path_uses_forward_slash(self, tmp_path: Path) -> None:
        """advpls aceita ambos em INI, mas forward-slash evita escape ambíguo."""
        log = Path("D:\\tmp\\foo\\validate.log")
        ini = _build_validate_ini("127.0.0.1", 1234, log)
        assert "\\" not in ini.split("logToFile=", 1)[1].splitlines()[0]


class TestProbeAppserverNetwork:
    @pytest.fixture
    def fake_binary(self, tmp_path: Path) -> Path:
        """Path que parece advpls (não executado de verdade — subprocess mockado)."""
        binary = tmp_path / "advpls"
        binary.write_text("", encoding="utf-8")
        return binary

    def test_success_returns_build_and_secure(
        self, fake_binary: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_proc = MagicMock()
        fake_proc.stdout = (
            b"[LOG] Appserver detected with build version: "
            b"7.00.240223P and secure: 0\n"
        )
        fake_proc.stderr = b""
        fake_proc.returncode = 0
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake_proc)
        result = probe_appserver_network("127.0.0.1", 1234, fake_binary)
        assert result.build == "7.00.240223P"
        assert result.secure is False
        assert result.error == ""

    def test_timeout_returns_error(
        self, fake_binary: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def raise_timeout(*a: object, **kw: object) -> None:
            raise subprocess.TimeoutExpired(cmd="advpls", timeout=20)
        monkeypatch.setattr(subprocess, "run", raise_timeout)
        result = probe_appserver_network("10.0.0.1", 1234, fake_binary)
        assert result.build == ""
        assert "timed out" in result.error

    def test_binary_not_found_returns_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def raise_fnf(*a: object, **kw: object) -> None:
            raise FileNotFoundError("[Errno 2] No such file")
        monkeypatch.setattr(subprocess, "run", raise_fnf)
        result = probe_appserver_network("127.0.0.1", 1234, tmp_path / "nope")
        assert result.build == ""
        assert "not found" in result.error

    def test_unparseable_output_returns_error_with_raw(
        self, fake_binary: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_proc = MagicMock()
        fake_proc.stdout = b"connection refused\n"
        fake_proc.stderr = b""
        fake_proc.returncode = 1
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake_proc)
        result = probe_appserver_network("127.0.0.1", 9999, fake_binary)
        assert result.build == ""
        assert "exit=1" in result.error
        assert "connection refused" in result.raw_output

    def test_tempdir_is_cleaned_up_on_success(
        self, fake_binary: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Não deve deixar pasta plugadvpl-probe-* no tempdir após sucesso."""
        import tempfile as _tempfile

        fake_proc = MagicMock()
        fake_proc.stdout = b"build version: 7.00.240223P and secure: 0\n"
        fake_proc.stderr = b""
        fake_proc.returncode = 0
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: fake_proc)
        monkeypatch.setattr(_tempfile, "gettempdir", lambda: str(tmp_path))
        before = set(tmp_path.iterdir())
        probe_appserver_network("127.0.0.1", 1234, fake_binary)
        after = set(tmp_path.iterdir())
        # Diff deve ser vazio — tudo limpo
        assert before == after, f"tempdir vazou: {after - before}"
