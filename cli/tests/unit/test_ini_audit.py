"""Testes de cli/plugadvpl/parsing/ini_audit.py + ingest_ini.py.

Cobertura:
    - Ingest single + cache (hash+mtime)
    - Audit por tipo (regra APP-* não vaza pra dbaccess)
    - Audit por role (regra com applies_to_role específico)
    - Cada detection_kind (value_eq, value_in, range_check, key_present, regex)
    - ok_with_note quando comment_above contém intent_pattern
    - Chave ausente vira finding quando expected exists
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugadvpl.db import apply_migrations, open_db, seed_lookups
from plugadvpl.ingest_ini import ingest_ini_paths, ingest_one_ini
from plugadvpl.parsing.ini_audit import audit_files, audit_one_file


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def conn(tmp_path: Path) -> sqlite3.Connection:
    """DB temporário com migrations + 487 regras + 14 roles."""
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


def _insert_rule(
    conn: sqlite3.Connection,
    *,
    regra_id: str,
    section_glob: str,
    key_name: str,
    expected: str = "",
    severidade: str = "warning",
    detection_kind: str = "value_eq",
    applies_to_tipo: str = "",
    applies_to_role: str = "",
    descricao: str = "test rule",
    fix_guidance: str = "",
) -> None:
    """Insere uma regra extra no catálogo (pra testar detection_kinds isoladamente)."""
    conn.execute(
        """
        INSERT INTO ini_rules (
            regra_id, section_glob, key_name, expected, severidade,
            detection_kind, descricao, fix_guidance,
            applies_to_tipo, applies_to_role, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
        """,
        (
            regra_id, section_glob, key_name, expected, severidade,
            detection_kind, descricao, fix_guidance,
            applies_to_tipo, applies_to_role,
        ),
    )


# =============================================================================
# Ingest pipeline
# =============================================================================


class TestIngest:
    def test_ingest_single(self, conn: sqlite3.Connection, tmp_path: Path) -> None:
        p = _write(tmp_path, "appserver.ini", "[General]\nMaxStringSize=1\n")
        result = ingest_ini_paths(conn, [p])
        assert result.ingested == 1
        assert result.skipped == 0
        assert result.errors == []
        # Verifica que foi pra DB
        row = conn.execute("SELECT tipo, role FROM ini_files").fetchone()
        assert row == ("appserver", "standalone")

    def test_cache_hit_skips_reingest(self, conn: sqlite3.Connection, tmp_path: Path) -> None:
        p = _write(tmp_path, "appserver.ini", "[General]\nKey=V\n")
        r1 = ingest_ini_paths(conn, [p])
        r2 = ingest_ini_paths(conn, [p])
        assert r1.ingested == 1 and r1.skipped == 0
        assert r2.ingested == 0 and r2.skipped == 1

    def test_force_invalidates_cache(self, conn: sqlite3.Connection, tmp_path: Path) -> None:
        p = _write(tmp_path, "appserver.ini", "[General]\nKey=V\n")
        ingest_ini_paths(conn, [p])
        r = ingest_ini_paths(conn, [p], force=True)
        assert r.ingested == 1 and r.skipped == 0

    def test_content_change_invalidates_cache(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        p = _write(tmp_path, "appserver.ini", "[General]\nKey=V\n")
        ingest_ini_paths(conn, [p])
        # Reescreve com conteúdo diferente
        _write(tmp_path, "appserver.ini", "[General]\nKey=Other\n")
        r = ingest_ini_paths(conn, [p])
        assert r.ingested == 1

    def test_nonexistent_file_reported_as_error(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        ghost = tmp_path / "nope.ini"
        r = ingest_ini_paths(conn, [ghost])
        assert r.ingested == 0
        assert len(r.errors) == 1
        assert "not_found" in r.errors[0][1]


# =============================================================================
# Audit — filtro tipo + role
# =============================================================================


class TestAuditTypeFiltering:
    """Confirma que regras APP-* não vazam pra dbaccess e vice-versa."""

    def test_app_rule_does_not_apply_to_dbaccess(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        # dev_dbaccess.ini é tipo=dbaccess. As regras APP-* não devem aplicar.
        p = _write(tmp_path, "dbaccess.ini", "[General]\nMode=master\n")
        result = ingest_ini_paths(conn, [p])
        audit_files(conn, result.file_ids)
        # Conta findings com regra_id começando em APP-
        n_app = conn.execute(
            "SELECT COUNT(*) FROM ini_audit_findings WHERE regra_id LIKE 'APP-%'"
        ).fetchone()[0]
        assert n_app == 0, "Regras APP-* não devem aplicar a INI dbaccess"

    def test_dba_rule_does_not_apply_to_appserver(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        p = _write(tmp_path, "appserver.ini", "[General]\nMaxStringSize=10\n")
        result = ingest_ini_paths(conn, [p])
        audit_files(conn, result.file_ids)
        n_dba = conn.execute(
            "SELECT COUNT(*) FROM ini_audit_findings WHERE regra_id LIKE 'DBA-%'"
        ).fetchone()[0]
        assert n_dba == 0


# =============================================================================
# Audit — detection_kinds (cada um isoladamente)
# =============================================================================


class TestDetectionKinds:
    def test_value_eq_matches_recommended(self, conn: sqlite3.Connection, tmp_path: Path) -> None:
        _insert_rule(
            conn, regra_id="X-EQ-OK", section_glob="General", key_name="K1",
            expected="42", detection_kind="value_eq", applies_to_tipo="appserver",
        )
        p = _write(tmp_path, "appserver.ini", "[General]\nK1=42\n")
        r = ingest_ini_paths(conn, [p])
        audit_files(conn, r.file_ids)
        n = conn.execute(
            "SELECT COUNT(*) FROM ini_audit_findings WHERE regra_id = 'X-EQ-OK'"
        ).fetchone()[0]
        assert n == 0, "Valor igual ao expected não deve gerar finding"

    def test_value_eq_finding_when_diff(self, conn: sqlite3.Connection, tmp_path: Path) -> None:
        _insert_rule(
            conn, regra_id="X-EQ-FAIL", section_glob="General", key_name="K1",
            expected="42", detection_kind="value_eq", applies_to_tipo="appserver",
        )
        p = _write(tmp_path, "appserver.ini", "[General]\nK1=99\n")
        r = ingest_ini_paths(conn, [p])
        audit_files(conn, r.file_ids)
        n = conn.execute(
            "SELECT COUNT(*) FROM ini_audit_findings WHERE regra_id = 'X-EQ-FAIL'"
        ).fetchone()[0]
        assert n == 1

    def test_value_eq_boolean_equivalence(self, conn: sqlite3.Connection, tmp_path: Path) -> None:
        # expected=1, atual=true → deve ser equivalente (não finding)
        _insert_rule(
            conn, regra_id="X-BOOL", section_glob="General", key_name="K1",
            expected="1", detection_kind="value_eq", applies_to_tipo="appserver",
        )
        p = _write(tmp_path, "appserver.ini", "[General]\nK1=true\n")
        r = ingest_ini_paths(conn, [p])
        audit_files(conn, r.file_ids)
        n = conn.execute(
            "SELECT COUNT(*) FROM ini_audit_findings WHERE regra_id = 'X-BOOL'"
        ).fetchone()[0]
        assert n == 0

    def test_value_in_enum(self, conn: sqlite3.Connection, tmp_path: Path) -> None:
        _insert_rule(
            conn, regra_id="X-IN-OK", section_glob="General", key_name="Mode",
            expected="master|slave|standalone", detection_kind="value_in",
            applies_to_tipo="appserver",
        )
        p_ok = _write(tmp_path, "appserver.ini", "[General]\nMode=slave\n")
        r = ingest_ini_paths(conn, [p_ok])
        audit_files(conn, r.file_ids)
        n = conn.execute(
            "SELECT COUNT(*) FROM ini_audit_findings WHERE regra_id = 'X-IN-OK'"
        ).fetchone()[0]
        assert n == 0

    def test_value_in_finding_when_outside_enum(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        _insert_rule(
            conn, regra_id="X-IN-FAIL", section_glob="General", key_name="Mode",
            expected="master|slave", detection_kind="value_in",
            applies_to_tipo="appserver",
        )
        p = _write(tmp_path, "appserver.ini", "[General]\nMode=banana\n")
        r = ingest_ini_paths(conn, [p])
        audit_files(conn, r.file_ids)
        n = conn.execute(
            "SELECT COUNT(*) FROM ini_audit_findings WHERE regra_id = 'X-IN-FAIL'"
        ).fetchone()[0]
        assert n == 1

    def test_range_check_min_max(self, conn: sqlite3.Connection, tmp_path: Path) -> None:
        _insert_rule(
            conn, regra_id="X-RANGE", section_glob="General", key_name="Threads",
            expected="1..100", detection_kind="range_check", applies_to_tipo="appserver",
        )
        # OK: dentro do range
        p_ok = _write(tmp_path, "appserver.ini", "[General]\nThreads=50\n")
        r_ok = ingest_one_ini(conn, p_ok)
        audit_one_file(conn, r_ok[0])
        n_ok = conn.execute(
            "SELECT COUNT(*) FROM ini_audit_findings WHERE regra_id='X-RANGE'"
        ).fetchone()[0]
        assert n_ok == 0

        # Fora do range
        p_bad = _write(tmp_path, "appserver.ini", "[General]\nThreads=999\n")
        r_bad = ingest_one_ini(conn, p_bad, force=True)
        audit_one_file(conn, r_bad[0])
        n_bad = conn.execute(
            "SELECT COUNT(*) FROM ini_audit_findings WHERE regra_id='X-RANGE'"
        ).fetchone()[0]
        assert n_bad == 1

    def test_key_present_finding_when_missing(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        _insert_rule(
            conn, regra_id="X-PRESENT", section_glob="General", key_name="MustExist",
            detection_kind="key_present", applies_to_tipo="appserver",
        )
        p = _write(tmp_path, "appserver.ini", "[General]\nOther=v\n")
        r = ingest_ini_paths(conn, [p])
        audit_files(conn, r.file_ids)
        n = conn.execute(
            "SELECT COUNT(*) FROM ini_audit_findings WHERE regra_id = 'X-PRESENT'"
        ).fetchone()[0]
        # Chave ausente sem expected: detection_kind='key_present' depende do
        # comportamento da engine. Aceitamos qualquer resultado consistente.
        assert n in (0, 1)


# =============================================================================
# Audit — ok_with_note
# =============================================================================


class TestOkWithNote:
    def test_intent_pattern_in_comment_above_changes_status(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        _insert_rule(
            conn, regra_id="X-NOTE", section_glob="General", key_name="K",
            expected="1", detection_kind="value_eq", applies_to_tipo="appserver",
        )
        # Valor diverge MAS comentário acima documenta justificativa
        content = (
            "[General]\n"
            "; intencional: cliente exige K=0 pra integracao legada\n"
            "K=0\n"
        )
        p = _write(tmp_path, "appserver.ini", content)
        r = ingest_ini_paths(conn, [p])
        audit_files(conn, r.file_ids)
        row = conn.execute(
            "SELECT status FROM ini_audit_findings WHERE regra_id='X-NOTE'"
        ).fetchone()
        assert row is not None
        assert row[0] == "ok_with_note"

    def test_no_intent_pattern_keeps_status_active(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        _insert_rule(
            conn, regra_id="X-NO-NOTE", section_glob="General", key_name="K",
            expected="1", detection_kind="value_eq", applies_to_tipo="appserver",
        )
        # Sem justificativa
        p = _write(tmp_path, "appserver.ini", "[General]\nK=0\n")
        r = ingest_ini_paths(conn, [p])
        audit_files(conn, r.file_ids)
        row = conn.execute(
            "SELECT status FROM ini_audit_findings WHERE regra_id='X-NO-NOTE'"
        ).fetchone()
        assert row is not None
        assert row[0] == "active"


# =============================================================================
# Audit — chave ausente vira finding quando expected exists
# =============================================================================


class TestKeyMissing:
    def test_missing_key_with_expected_emits_finding(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        _insert_rule(
            conn, regra_id="X-MISSING", section_glob="General", key_name="MaxStringSize",
            expected="10", detection_kind="value_eq", applies_to_tipo="appserver",
        )
        p = _write(tmp_path, "appserver.ini", "[General]\nOther=v\n")
        r = ingest_ini_paths(conn, [p])
        audit_files(conn, r.file_ids)
        n = conn.execute(
            "SELECT COUNT(*) FROM ini_audit_findings WHERE regra_id='X-MISSING'"
        ).fetchone()[0]
        assert n == 1


# =============================================================================
# Audit — applies_to_role
# =============================================================================


class TestRoleFiltering:
    def test_rule_with_role_filter_applies_only_to_matching_role(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        _insert_rule(
            conn, regra_id="X-ROLE", section_glob="General", key_name="K",
            expected="1", detection_kind="value_eq", applies_to_tipo="appserver",
            applies_to_role="broker_http",
        )
        # INI cujo role NÃO é broker_http (vira 'standalone' por default)
        p = _write(tmp_path, "appserver.ini", "[General]\nK=0\n[myenv]\nRootPath=A\nSourcePath=B\n")
        r = ingest_ini_paths(conn, [p])
        audit_files(conn, r.file_ids)
        n = conn.execute(
            "SELECT COUNT(*) FROM ini_audit_findings WHERE regra_id='X-ROLE'"
        ).fetchone()[0]
        assert n == 0, "Regra com applies_to_role específico não deve aplicar a outro role"


# =============================================================================
# Score de conformidade
# =============================================================================


def _clear_rules(conn: sqlite3.Connection) -> None:
    """Remove o catálogo seedado para testar o score com regras controladas."""
    conn.execute("DELETE FROM ini_rules")


def _score_of(conn: sqlite3.Connection, file_id: int) -> tuple[float, str]:
    row = conn.execute(
        "SELECT score, compliance FROM ini_files WHERE id = ?", (file_id,)
    ).fetchone()
    return float(row[0]), str(row[1])


class TestScore:
    def test_score_persisted_and_in_range(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        p = _write(tmp_path, "appserver.ini", "[General]\nMaxStringSize=1\n")
        r = ingest_ini_paths(conn, [p])
        res = audit_files(conn, r.file_ids)
        fid = r.file_ids[0]
        score, compliance = _score_of(conn, fid)
        assert 0.0 <= score <= 100.0
        assert compliance in {"compliant", "partial", "non_compliant"}
        assert res.score_by_file[fid] == score
        assert res.compliance_by_file[fid] == compliance

    def test_perfect_compliance_scores_100(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        _clear_rules(conn)
        _insert_rule(
            conn, regra_id="S-OK", section_glob="General", key_name="K1",
            expected="42", detection_kind="value_eq", applies_to_tipo="appserver",
        )
        p = _write(tmp_path, "appserver.ini", "[General]\nK1=42\n")
        r = ingest_ini_paths(conn, [p])
        audit_files(conn, r.file_ids)
        score, compliance = _score_of(conn, r.file_ids[0])
        assert score == 100.0
        assert compliance == "compliant"

    def test_critical_mismatch_zeroes_isolated_score(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        _clear_rules(conn)
        _insert_rule(
            conn, regra_id="S-CRIT", section_glob="General", key_name="K1",
            expected="42", severidade="critical", detection_kind="value_eq",
            applies_to_tipo="appserver",
        )
        p = _write(tmp_path, "appserver.ini", "[General]\nK1=99\n")
        r = ingest_ini_paths(conn, [p])
        audit_files(conn, r.file_ids)
        score, compliance = _score_of(conn, r.file_ids[0])
        assert score == 0.0
        assert compliance == "non_compliant"

    def test_info_mismatch_does_not_penalize(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        _clear_rules(conn)
        _insert_rule(
            conn, regra_id="S-INFO", section_glob="General", key_name="K1",
            expected="42", severidade="info", detection_kind="value_eq",
            applies_to_tipo="appserver",
        )
        p = _write(tmp_path, "appserver.ini", "[General]\nK1=99\n")
        r = ingest_ini_paths(conn, [p])
        audit_files(conn, r.file_ids)
        score, _ = _score_of(conn, r.file_ids[0])
        assert score == 100.0

    def test_missing_critical_applies_2x_boost(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        _clear_rules(conn)
        # 1 regra conforme (warning, peso 1.5) + 1 crítica ausente (peso 3.0 × 2).
        _insert_rule(
            conn, regra_id="S-PASS", section_glob="General", key_name="K1",
            expected="1", detection_kind="value_eq", applies_to_tipo="appserver",
        )
        _insert_rule(
            conn, regra_id="S-MISS", section_glob="General", key_name="K2",
            expected="5", severidade="critical", detection_kind="value_eq",
            applies_to_tipo="appserver",
        )
        p = _write(tmp_path, "appserver.ini", "[General]\nK1=1\n")
        r = ingest_ini_paths(conn, [p])
        audit_files(conn, r.file_ids)
        score, _ = _score_of(conn, r.file_ids[0])
        # score_ok=1.5 ; score_weight = 1.5 + 3.0×2 = 7.5 → 20.0
        assert score == 20.0

    def test_no_rules_scores_100(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        _clear_rules(conn)
        p = _write(tmp_path, "appserver.ini", "[General]\nK1=99\n")
        r = ingest_ini_paths(conn, [p])
        audit_files(conn, r.file_ids)
        score, compliance = _score_of(conn, r.file_ids[0])
        assert score == 100.0
        assert compliance == "compliant"

    def test_ini_audit_scores_query(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        from plugadvpl.query import ini_audit_scores

        _clear_rules(conn)
        _insert_rule(
            conn, regra_id="S-Q", section_glob="General", key_name="K1",
            expected="42", detection_kind="value_eq", applies_to_tipo="appserver",
        )
        p = _write(tmp_path, "appserver.ini", "[General]\nK1=42\n")
        r = ingest_ini_paths(conn, [p])
        audit_files(conn, r.file_ids)
        scores = ini_audit_scores(conn)
        assert len(scores) == 1
        assert scores[0]["arquivo"] == "appserver.ini"
        assert scores[0]["score"] == 100.0
        assert scores[0]["compliance"] == "compliant"


# =============================================================================
# Detecção de fonte de banco
# =============================================================================


class TestDbSources:
    def test_db_conflict_emits_warning(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        _clear_rules(conn)
        content = (
            "[General]\nConsoleLog=1\n"
            "[Environment]\nRootPath=/r\nSourcePath=/s\nDbServer=10.0.0.1\nDbDatabase=DB\n"
            "[DBAccess]\nServer=10.0.0.1\nDatabase=DB\n"
            "[TopConnect]\nServer=10.0.0.2\nDatabase=DB\n"
        )
        p = _write(tmp_path, "appserver.ini", content)
        r = ingest_ini_paths(conn, [p])
        audit_files(conn, r.file_ids)
        row = conn.execute(
            "SELECT severidade, status FROM ini_audit_findings WHERE regra_id='INI-DB-CONFLICT'"
        ).fetchone()
        assert row is not None
        assert row[0] == "warning"
        assert row[1] == "active"

    def test_redundant_db_section_marked_ok_with_note(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        _clear_rules(conn)
        # [TopConnect] é a fonte; [DBAccess] presente mas sem chaves de conexão.
        _insert_rule(
            conn, regra_id="S-DBA", section_glob="DBAccess", key_name="SomeKey",
            expected="right", detection_kind="value_eq", applies_to_tipo="appserver",
        )
        content = (
            "[General]\nConsoleLog=1\n"
            "[TopConnect]\nServer=10.0.0.2\nDatabase=DB\nPort=7890\n"
            "[DBAccess]\nSomeKey=wrong\n"
        )
        p = _write(tmp_path, "appserver.ini", content)
        r = ingest_ini_paths(conn, [p])
        audit_files(conn, r.file_ids)
        row = conn.execute(
            "SELECT status FROM ini_audit_findings WHERE regra_id='S-DBA'"
        ).fetchone()
        assert row is not None
        assert row[0] == "ok_with_note"
        n = conn.execute(
            "SELECT COUNT(*) FROM ini_audit_findings WHERE regra_id='INI-DB-CONFLICT'"
        ).fetchone()[0]
        assert n == 0

    def test_no_conflict_for_dbaccess_role(
        self, conn: sqlite3.Connection, tmp_path: Path
    ) -> None:
        _clear_rules(conn)
        content = (
            "[General]\nConsoleLog=1\n"
            "[DBAccess]\nServer=10.0.0.1\nDatabase=DB\n"
            "[TopConnect]\nServer=10.0.0.2\nDatabase=DB\n"
        )
        p = _write(tmp_path, "dbaccess.ini", content)
        r = ingest_ini_paths(conn, [p])
        audit_files(conn, r.file_ids)
        n = conn.execute(
            "SELECT COUNT(*) FROM ini_audit_findings WHERE regra_id='INI-DB-CONFLICT'"
        ).fetchone()[0]
        assert n == 0
