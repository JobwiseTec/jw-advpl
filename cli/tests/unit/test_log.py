"""Testes de cli/plugadvpl/parsing/log.py.

Cobertura:
    - Parser core (4 formatos de header, body preservado, eventos consecutivos)
    - Encoding detection (BOM utf-8, utf-8 puro, cp1252, ascii)
    - Detecção de tipo (console/error/profile/compile/outro)
    - Extração de metadata [key: value]
    - Métricas (memória OS/App, start time)
    - Helpers (find_latest_timestamp com mistura naive/aware, is_noise)
"""
from __future__ import annotations

import pytest

from plugadvpl.parsing.log import (
    decode_log_bytes,
    detect_log_encoding,
    detect_log_type,
    extract_header_metadata,
    find_latest_timestamp,
    is_noise,
    is_protheus_log_filename,
    parse_log_file,
    scan_metrics,
    tokenize_events,
)


# =============================================================================
# Encoding
# =============================================================================


class TestEncoding:
    def test_ascii(self) -> None:
        assert detect_log_encoding(b"plain ASCII content") == "ascii"

    def test_utf8_bom(self) -> None:
        assert detect_log_encoding(b"\xef\xbb\xbf[INFO] start") == "utf-8-bom"

    def test_utf8_without_bom(self) -> None:
        assert detect_log_encoding("Usuário entrou".encode("utf-8")) == "utf-8"

    def test_cp1252_fallback(self) -> None:
        # 0xE9 = é em CP1252, inválido em UTF-8
        assert detect_log_encoding(b"User=Jos\xe9") == "cp1252"

    def test_decode_strips_bom(self) -> None:
        assert decode_log_bytes(b"\xef\xbb\xbfhello").startswith("hello")

    def test_decode_cp1252_fallback(self) -> None:
        decoded = decode_log_bytes(b"Usu\xe1rio")
        assert "Usuário" in decoded


# =============================================================================
# Tipo de log
# =============================================================================


class TestLogType:
    @pytest.mark.parametrize("name,expected", [
        ("console.log", "console"),
        ("dev_console.log", "console"),
        ("error.log", "error"),
        ("prd_error.log", "error"),
        ("profile.log", "profile"),
        ("compila.log", "compile"),
        ("compile.log", "compile"),
        ("appserver_qa.log", "outro"),  # contém appserver mas não tem token de tipo específico
        ("random.log", "outro"),
    ])
    def test_detect(self, name: str, expected: str) -> None:
        assert detect_log_type(name) == expected


class TestIsProtheusLogFilename:
    @pytest.mark.parametrize("name", [
        "console.log", "console_error.log", "dev_console.log",
        "error.log", "profile.log", "compila.log", "appserver.log", "tss.log",
    ])
    def test_accepted(self, name: str) -> None:
        assert is_protheus_log_filename(name) is True

    @pytest.mark.parametrize("name", [
        "config.txt", "random.log", "build.json", "console.txt",
    ])
    def test_rejected(self, name: str) -> None:
        assert is_protheus_log_filename(name) is False


# =============================================================================
# is_noise
# =============================================================================


class TestIsNoise:
    @pytest.mark.parametrize("line", [
        "deleting thread Pool",
        "deleting server, instance 5",
        "Deleting jobs from Threadpool",
        "Function 'MyVeryLongFunc' has more than 10 characters",
    ])
    def test_noise_patterns(self, line: str) -> None:
        assert is_noise(line) is True

    def test_non_noise(self) -> None:
        assert is_noise("THREAD ERROR ([123], FOO, BAR) 01/01/2026 00:00:00") is False


# =============================================================================
# Tokenize events (Stage 1)
# =============================================================================


class TestTokenize:
    def test_iso_thread_header(self) -> None:
        content = "2026-05-21T08:15:00.123-03:00 1648| AppServer started\n"
        events = tokenize_events(content)
        assert len(events) == 1
        assert events[0].thread_id == "1648"
        assert events[0].timestamp is not None
        assert events[0].timestamp.year == 2026

    def test_thread_error_ptbr_header(self) -> None:
        content = (
            "THREAD ERROR ([31716], TIRETPIN, THIS)   06/05/2026   22:42:06\n"
            "type mismatch on array assign\n"
            "Called from TIRETPIN(L:234)\n"
        )
        events = tokenize_events(content)
        assert len(events) == 1
        assert events[0].thread_id == "31716"
        assert events[0].timestamp.day == 6
        assert events[0].timestamp.month == 5
        # Body preservado
        assert "type mismatch" in events[0].body
        assert "TIRETPIN(L:234)" in events[0].body

    def test_ptbr_timestamp_header(self) -> None:
        content = "[06/05/2026 22:45:33] CheckAuth ERROR: invalid signature\n"
        events = tokenize_events(content)
        assert len(events) == 1
        assert events[0].timestamp.day == 6

    def test_bracket_severity_header(self) -> None:
        content = "[ERROR] AppServer fail to start\n[INFO] retrying\n"
        events = tokenize_events(content)
        assert len(events) == 2
        # Bracket headers não têm timestamp
        assert events[0].timestamp is None

    def test_orphan_lines_before_first_header_discarded(self) -> None:
        content = (
            "orphan line 1\n"
            "orphan line 2\n"
            "2026-05-21T08:15:00.123-03:00 1648| actual event\n"
        )
        events = tokenize_events(content)
        assert len(events) == 1
        assert events[0].thread_id == "1648"

    def test_consecutive_events_separated_correctly(self) -> None:
        content = (
            "2026-05-21T08:15:00.123-03:00 1648| event 1 header\n"
            "  body of event 1 line 1\n"
            "  body of event 1 line 2\n"
            "2026-05-21T08:16:00.456-03:00 1700| event 2 header\n"
            "  body of event 2\n"
        )
        events = tokenize_events(content)
        assert len(events) == 2
        assert "body of event 1" in events[0].body
        assert "body of event 1" not in events[1].body
        assert "body of event 2" in events[1].body

    def test_max_lines_cap(self) -> None:
        lines = [f"2026-05-21T08:15:{i:02d}.000-03:00 100| msg {i}" for i in range(50)]
        content = "\n".join(lines) + "\n"
        events = tokenize_events(content, max_lines=10)
        # Cap em 10 linhas = no máximo 10 eventos (cada linha tem header)
        assert len(events) <= 10


# =============================================================================
# Header metadata
# =============================================================================


class TestHeaderMetadata:
    def test_extracts_known_keys(self) -> None:
        content = (
            "[build: 7.00.240223P-20240223]\n"
            "[platform: Linux]\n"
            "[environment: protheus_prd]\n"
            "[thread: 31716]\n"
            "[appversion: 12.1.2410]\n"
            "\nactual log starts...\n"
        )
        md = extract_header_metadata(content)
        assert md.build == "7.00.240223P-20240223"
        assert md.environment == "protheus_prd"
        assert md.thread == "31716"
        # appversion vai pra extra
        assert "appversion" in md.extra or md.extra.get("appversion") == "12.1.2410"

    def test_skips_na_values(self) -> None:
        content = "[environment: N/A]\n[build: ND]\n[platform: Linux]\n"
        md = extract_header_metadata(content)
        assert md.environment == ""

    def test_empty_input(self) -> None:
        md = extract_header_metadata("")
        assert md.environment == ""
        assert md.extra == {}


# =============================================================================
# Métricas
# =============================================================================


class TestScanMetrics:
    def test_memory_os(self) -> None:
        content = "Physical memory . 16384.0 MB. Used 8192.5 MB. Free 8191.5 MB\n"
        m = scan_metrics(content)
        assert m.memory_total_mb == "16384.0"
        assert m.memory_used_mb == "8192.5"
        assert m.memory_free_mb == "8191.5"

    def test_memory_app(self) -> None:
        content = "Service Resident Memory ... 1234.5 MB\n"
        m = scan_metrics(content)
        assert m.memory_resident_mb == "1234.5"

    def test_start_time(self) -> None:
        content = "Application Server Start Time: 12.5 s\n"
        m = scan_metrics(content)
        assert m.start_time_s == "12.5"


# =============================================================================
# Timestamp normalization
# =============================================================================


class TestTimestamp:
    def test_mixed_naive_aware_normalizes(self) -> None:
        from plugadvpl.parsing.log import LogEvent
        from datetime import datetime, timezone
        aware = datetime(2026, 5, 21, 10, 0, 0, tzinfo=timezone.utc)
        naive = datetime(2026, 5, 21, 11, 0, 0)
        events = [
            LogEvent(line_number=1, header_line="x", timestamp=aware),
            LogEvent(line_number=2, header_line="y", timestamp=naive),
        ]
        # Deve normalizar e não levantar TypeError
        latest = find_latest_timestamp(events)
        assert latest is not None
        # Maior é naive 11:00 vs aware 10:00 — stripping tz mantém 11:00 vencedor
        assert latest.hour == 11

    def test_empty_returns_none(self) -> None:
        assert find_latest_timestamp([]) is None


# =============================================================================
# Parser top-level
# =============================================================================


class TestParseLogFile:
    def test_full_pipeline(self) -> None:
        content = (
            "[environment: prd]\n"
            "[build: 7.00.240223P]\n"
            "\n"
            "2026-05-21T08:00:00.000-03:00 100| Totvs Application Server is running\n"
            "2026-05-21T08:30:00.000-03:00 200| THREAD ERROR ([200], FOO, BAR)   21/05/2026   08:30:00\n"
            "  type mismatch\n"
        )
        p = parse_log_file(content, filename="console.log")
        assert p.tipo == "console"
        assert p.metadata.environment == "prd"
        assert p.metadata.build == "7.00.240223P"
        assert len(p.events) >= 2
        assert p.first_ts is not None
        assert p.last_ts is not None

    def test_accepts_bytes(self) -> None:
        raw = b"2026-05-21T08:00:00.000-03:00 100| server up\n"
        p = parse_log_file(raw, filename="console.log")
        assert p.encoding in {"ascii", "utf-8"}
        assert len(p.events) == 1

    def test_empty_input(self) -> None:
        p = parse_log_file("", filename="empty.log")
        assert p.events == []
        assert p.first_ts is None
