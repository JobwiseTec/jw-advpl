"""Testes de cli/plugadvpl/parsing/log_diagnose.py + ingest_log.py.

Cobertura:
    - Ingest single + cache (hash+mtime)
    - Diagnose com regras seedadas (LOG-DB-ORA, LOG-THREAD-ERROR, etc.)
    - Janela ``--since`` relativa ao último timestamp
    - Filtro por severidade
    - Correction tips cruzadas via log_tips
    - Categoria fallback quando nenhum tip específica casa
    - Curto-circuito: 1 finding por evento (não cumulativo)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugadvpl.db import apply_migrations, open_db, seed_lookups
from plugadvpl.ingest_log import ingest_log_paths, ingest_one_log
from plugadvpl.parsing.log_diagnose import diagnose_files, diagnose_one_file


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    """DB temporário com migrations + log_rules + log_tips + log_categories."""
    db_path = tmp_path / "test_index.db"
    c = open_db(db_path)
    apply_migrations(c)
    seed_lookups(c)
    yield c
    c.close()


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# =============================================================================
# Ingest
# =============================================================================


class TestIngest:
    def test_ingest_single(self, conn: sqlite3.Connection, tmp_path: Path) -> None:
        p = _write(tmp_path, "console.log",
                   "2026-05-21T08:00:00.000-03:00 100| server up\n")
        result = ingest_log_paths(conn, [p])
        assert result.ingested == 1
        assert result.skipped == 0
        row = conn.execute(
            "SELECT tipo, total_events FROM log_files"
        ).fetchone()
        assert row[0] == "console"
        assert row[1] == 1

    def test_cache_hit_skips_reingest(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        p = _write(tmp_path, "console.log",
                   "2026-05-21T08:00:00.000-03:00 100| up\n")
        r1 = ingest_log_paths(conn, [p])
        r2 = ingest_log_paths(conn, [p])
        assert r1.ingested == 1
        assert r2.skipped == 1

    def test_force_invalidates_cache(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        p = _write(tmp_path, "console.log",
                   "2026-05-21T08:00:00.000-03:00 100| up\n")
        ingest_log_paths(conn, [p])
        r = ingest_log_paths(conn, [p], force=True)
        assert r.ingested == 1

    def test_content_change_invalidates(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        p = _write(tmp_path, "console.log",
                   "2026-05-21T08:00:00.000-03:00 100| v1\n")
        ingest_log_paths(conn, [p])
        _write(tmp_path, "console.log",
               "2026-05-21T08:00:00.000-03:00 100| v2 changed\n")
        r = ingest_log_paths(conn, [p])
        assert r.ingested == 1

    def test_truncated_log_reports_warning(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Review #4: log que excede max_lines no parser não pode falhar
        silenciosamente — precisa virar warning visível em LogIngestResult.warnings."""
        # Gera 1500 linhas de header válido; força tokenização com max_lines baixo
        # via monkey-patch da função tokenize.
        from plugadvpl.parsing import log as log_mod

        lines = [
            f"2026-05-21T08:{i // 60:02d}:{i % 60:02d}.000-03:00 100| evento {i}"
            for i in range(1500)
        ]
        p = _write(tmp_path, "console.log", "\n".join(lines) + "\n")

        # Patch temporário do default de max_lines pra forçar truncamento
        original = log_mod.tokenize_events_with_meta

        def low_cap(content: str, max_lines: int = 1000) -> tuple:
            return original(content, max_lines=1000)

        log_mod.tokenize_events_with_meta = low_cap  # type: ignore[assignment]
        try:
            r = ingest_log_paths(conn, [p])
        finally:
            log_mod.tokenize_events_with_meta = original  # type: ignore[assignment]

        # 1 ingerido + 1 warning visível
        assert r.ingested == 1
        assert len(r.warnings) == 1
        assert "truncated_at_line" in r.warnings[0][1]
        # Eventos disponíveis ainda podem ser diagnosticados
        diagnose_files(conn, r.file_ids)

    def test_metadata_extracted_from_error_log(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        content = (
            "[environment: protheus_prd]\n"
            "[build: 7.00.240223P]\n"
            "\n"
            "THREAD ERROR ([100], FOO, BAR)   21/05/2026   08:00:00\n"
        )
        p = _write(tmp_path, "error.log", content)
        ingest_log_paths(conn, [p])
        row = conn.execute(
            "SELECT environment, build, tipo FROM log_files"
        ).fetchone()
        assert row[0] == "protheus_prd"
        assert row[1] == "7.00.240223P"
        assert row[2] == "error"


# =============================================================================
# Diagnose — regras seedadas
# =============================================================================


class TestDiagnose:
    def test_ora_error_detected(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        content = (
            "2026-05-21T08:00:00.000-03:00 100| ORA-00942: table not found\n"
        )
        p = _write(tmp_path, "console.log", content)
        r = ingest_log_paths(conn, [p])
        diagnose_files(conn, r.file_ids)
        row = conn.execute(
            "SELECT rule_id, severity, category, message, ora_code, correction_tip, tdn_url "
            "FROM log_findings WHERE file_id = ?", (r.file_ids[0],),
        ).fetchone()
        assert row is not None
        assert row[0] == "LOG-DB-ORA"
        assert row[1] == "critical"
        assert row[2] == "database"
        assert "ORA-00942" in row[3]
        assert row[4] == "ORA-00942"
        # Correction tip carregado de log_tips (pode bater regra genérica de ORA)
        assert row[5] != ""

    def test_thread_error_detected(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        content = (
            "THREAD ERROR ([31716], TIRETPIN, THIS)   06/05/2026   22:42:06\n"
            "type mismatch on array assign\n"
        )
        p = _write(tmp_path, "error.log", content)
        r = ingest_log_paths(conn, [p])
        diagnose_files(conn, r.file_ids)
        row = conn.execute(
            "SELECT rule_id, category, message, thread_id FROM log_findings"
        ).fetchone()
        assert row[0] == "LOG-THREAD-ERROR"
        assert row[1] == "thread_error"
        assert "TIRETPIN" in row[2]
        assert row[3] == "31716"

    def test_checkauth_detected(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        p = _write(tmp_path, "error.log",
                   "[06/05/2026 22:45:33] CheckAuth ERROR: invalid signature\n")
        r = ingest_log_paths(conn, [p])
        diagnose_files(conn, r.file_ids)
        row = conn.execute(
            "SELECT rule_id, category FROM log_findings"
        ).fetchone()
        assert row[0] == "LOG-RPO-CHECKAUTH"
        assert row[1] == "rpo"

    def test_inactivity_warning(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        p = _write(tmp_path, "console.log",
                   "2026-05-21T08:00:00.000-03:00 100| Connection finished by inactivity\n")
        r = ingest_log_paths(conn, [p])
        diagnose_files(conn, r.file_ids)
        row = conn.execute(
            "SELECT rule_id, severity FROM log_findings"
        ).fetchone()
        assert row[0] == "LOG-CONN-INACTIVITY"
        assert row[1] == "warning"

    def test_running_info(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        p = _write(tmp_path, "console.log",
                   "2026-05-21T08:00:00.000-03:00 100| Totvs Application Server is running\n")
        r = ingest_log_paths(conn, [p])
        diagnose_files(conn, r.file_ids)
        row = conn.execute(
            "SELECT rule_id, severity FROM log_findings"
        ).fetchone()
        assert row[0] == "LOG-LIFECYCLE-RUNNING"
        assert row[1] == "info"


# =============================================================================
# Filtros
# =============================================================================


class TestFilters:
    def test_severity_filter_does_not_swallow_higher_priority_match(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """Regressão do review #1 (Joni): com ``--severity critical``, uma rule
        warning de prioridade BAIXA não pode descartar o evento e impedir uma
        rule critical de prioridade MAIOR de casar.

        Cenário: insere 2 rules custom no mesmo padrão de texto:
            - X-WARN-LOW   (warning, priority 1) — sempre testada primeiro
            - X-CRIT-HIGH  (critical, priority 2)

        Evento contém o padrão. Filtro ``--severity critical`` deve emitir
        finding de X-CRIT-HIGH (não silêncio).
        """
        # Insere 2 rules ad-hoc que casam o mesmo token
        conn.execute(
            """INSERT INTO log_rules
               (rule_id, category, severidade, pattern, message_template,
                case_insensitive, multiline, priority, status)
               VALUES (?, ?, ?, ?, ?, 0, 0, ?, 'active')""",
            ("X-WARN-LOW", "application", "warning", r"SAMEEVENT", "warn match", 1),
        )
        conn.execute(
            """INSERT INTO log_rules
               (rule_id, category, severidade, pattern, message_template,
                case_insensitive, multiline, priority, status)
               VALUES (?, ?, ?, ?, ?, 0, 0, ?, 'active')""",
            ("X-CRIT-HIGH", "database", "critical", r"SAMEEVENT", "crit match", 2),
        )
        conn.commit()

        p = _write(tmp_path, "console.log",
                   "2026-05-21T08:00:00.000-03:00 100| linha com SAMEEVENT no corpo\n")
        r = ingest_log_paths(conn, [p])

        # Sem filtro: warning vence (priority menor)
        diagnose_files(conn, r.file_ids)
        row = conn.execute(
            "SELECT rule_id FROM log_findings WHERE file_id = ?", (r.file_ids[0],),
        ).fetchone()
        assert row[0] == "X-WARN-LOW"

        # Com --severity critical: warning NÃO pode descartar; critical deve casar
        diagnose_files(conn, r.file_ids, severity_filter=["critical"])
        row = conn.execute(
            "SELECT rule_id, severity FROM log_findings WHERE file_id = ?",
            (r.file_ids[0],),
        ).fetchone()
        assert row is not None, "Filtro --severity critical não pode silenciar finding"
        assert row[0] == "X-CRIT-HIGH"
        assert row[1] == "critical"

    def test_severity_filter_excludes_others(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # Inclui 1 critical + 1 warning + 1 info
        content = (
            "2026-05-21T08:00:00.000-03:00 100| ORA-00942: x\n"
            "2026-05-21T08:01:00.000-03:00 100| Connection finished by inactivity\n"
            "2026-05-21T08:02:00.000-03:00 100| Totvs Application Server is running\n"
        )
        p = _write(tmp_path, "console.log", content)
        r = ingest_log_paths(conn, [p])
        diagnose_files(conn, r.file_ids, severity_filter=["critical"])
        # Só o ORA-00942 deve aparecer
        rows = conn.execute(
            "SELECT rule_id FROM log_findings WHERE file_id = ?", (r.file_ids[0],),
        ).fetchall()
        rule_ids = {row[0] for row in rows}
        assert "LOG-DB-ORA" in rule_ids
        assert "LOG-CONN-INACTIVITY" not in rule_ids
        assert "LOG-LIFECYCLE-RUNNING" not in rule_ids


# =============================================================================
# Janela --since (relativa ao último timestamp)
# =============================================================================


class TestSince:
    def test_since_keeps_recent_events_only(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # 3 eventos: 10h, 9h e 1h antes do último
        content = (
            "2026-05-21T07:00:00.000-03:00 100| ORA-00001: old\n"
            "2026-05-21T08:00:00.000-03:00 100| ORA-00002: middle\n"
            "2026-05-21T08:30:00.000-03:00 100| ORA-00003: recent\n"
        )
        p = _write(tmp_path, "console.log", content)
        r = ingest_log_paths(conn, [p])
        diagnose_files(conn, r.file_ids, since="45m")  # mantém só os últimos 45m
        rows = conn.execute(
            "SELECT message FROM log_findings ORDER BY line_number",
        ).fetchall()
        # Filtra: 08:30 menos 45m = 07:45. Eventos válidos: 08:00 e 08:30.
        msgs = " ".join(r[0] for r in rows)
        assert "ORA-00003" in msgs
        assert "ORA-00002" in msgs
        assert "ORA-00001" not in msgs

    def test_since_invalid_format_ignored(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        p = _write(tmp_path, "console.log",
                   "2026-05-21T08:00:00.000-03:00 100| ORA-00042: x\n")
        r = ingest_log_paths(conn, [p])
        # "invalido" não casa o regex de _parse_since → ignora janela
        diagnose_files(conn, r.file_ids, since="invalido")
        n = conn.execute("SELECT COUNT(*) FROM log_findings").fetchone()[0]
        assert n == 1


# =============================================================================
# Short-circuit (1 finding por evento)
# =============================================================================


class TestShortCircuit:
    def test_one_finding_per_event(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # Evento com 2 padrões que casariam (ORA + WARNING)
        content = (
            "2026-05-21T08:00:00.000-03:00 100| ORA-00942 occurred [WARNING] also relevant\n"
        )
        p = _write(tmp_path, "console.log", content)
        r = ingest_log_paths(conn, [p])
        diagnose_files(conn, r.file_ids)
        # Curto-circuita após o primeiro match → exatamente 1 finding
        n = conn.execute("SELECT COUNT(*) FROM log_findings").fetchone()[0]
        assert n == 1


# =============================================================================
# Correction tip lookup
# =============================================================================


class TestFormatMessage:
    """Review #6: ``_format_message`` deve ser à prova de capture group contendo
    literal ``{N}`` (que sequenciais ``str.replace`` corromperiam)."""

    def test_capture_with_literal_placeholder_not_corrupted(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # Rule cujo capture group 1 conterá literalmente "{2}"
        conn.execute(
            """INSERT INTO log_rules
               (rule_id, category, severidade, pattern, message_template,
                case_insensitive, multiline, priority, status)
               VALUES (?, ?, ?, ?, ?, 0, 0, ?, 'active')""",
            ("X-FMT", "application", "warning",
             r"USER=([^\s]+)\s+EXTRA=(\w+)",
             "user={1} extra={2}", 50),
        )
        conn.commit()

        # capture(1) = "value{2}data" — contém literal {2}
        # capture(2) = "real"
        # Esperado: "user=value{2}data extra=real"
        # Bug antigo: sequential replace transformaria em "user=valuerealdata extra=real"
        p = _write(tmp_path, "console.log",
                   "2026-05-21T08:00:00.000-03:00 100| USER=value{2}data EXTRA=real\n")
        r = ingest_log_paths(conn, [p])
        diagnose_files(conn, r.file_ids)

        msg = conn.execute(
            "SELECT message FROM log_findings WHERE rule_id = 'X-FMT'"
        ).fetchone()[0]
        # O literal {2} dentro do group 1 deve sobreviver intacto
        assert msg == "user=value{2}data extra=real"


class TestCorrectionTip:
    def test_specific_tip_matched_for_too_many_users(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        p = _write(tmp_path, "console.log",
                   "2026-05-21T08:00:00.000-03:00 100| "
                   "Error - TOPCONN - TOO_MANY_USERS - No licenses available\n")
        r = ingest_log_paths(conn, [p])
        diagnose_files(conn, r.file_ids)
        row = conn.execute(
            "SELECT correction_tip, tdn_url FROM log_findings"
        ).fetchone()
        # Tip deve conter referência a LicenseLimit/License Server
        assert "License" in row[0] or "licenc" in row[0].lower()

    def test_category_fallback_when_no_specific_tip(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # Evento de application/WARNING não casa nenhum tip específico (depende
        # do conteúdo da mensagem), então deve cair pra fallback da categoria
        p = _write(tmp_path, "console.log",
                   "2026-05-21T08:00:00.000-03:00 100| [WARNING] some random advpl warning xyz\n")
        r = ingest_log_paths(conn, [p])
        diagnose_files(conn, r.file_ids)
        row = conn.execute(
            "SELECT correction_tip FROM log_findings"
        ).fetchone()
        # Tip presente (fallback ou específico) — não vazia
        assert row[0] != ""
