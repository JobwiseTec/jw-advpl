"""Testes unit do módulo plugadvpl.apply_patch — aplicação de .PTM (U6, issue #4).

Cobre os achados do smoke 2026-06-16 que viraram requisito:
- parse de log (applied/partial/failed) — NÃO confiar no exit code;
- `secure` numérico no .ini;
- idempotência por hash;
- ZIP descompactado internamente em ordem alfabética;
- lock exclusivo por env;
- orquestrador (happy path / skip idempotente / abort no failed).
"""
from __future__ import annotations

import sqlite3
import zipfile
from pathlib import Path

import pytest

from plugadvpl.apply_patch import (
    ApplyPatchResult,
    build_patch_ini,
    discover_ptms,
    env_lock,
    extract_build,
    is_applied,
    parse_patch_log,
    run_apply_patch,
    sha256_file,
)
from plugadvpl.compile_servers import Server
from plugadvpl.db import apply_migrations, open_db

# --------------------------------------------------------------------------- #
# Snippets de log REAIS (extraídos do smoke 2026-06-16)
# --------------------------------------------------------------------------- #
_LOG_APPLIED = """\
[INFO] Appserver detected with build version: 7.00.240223P without secure connection
[INFO] User authenticated successfully.
[INFO] Applying patch file: /x/foo.ptm
[INFO] Patch (foo.ptm) successfully applied.
[INFO] Apply patch finished.
"""

_LOG_PARTIAL = """\
[INFO] Appserver detected with build version: 7.00.240223P without secure connection
[WARN] Outdated sources and/or resources detected.
[INFO] 'applyOldProgram' was NOT set. Only new sources are being applied.
[INFO] Applying patch file: /x/foo.ptm
[INFO] Patch (foo.ptm) successfully applied.
"""

_LOG_STOI = "[ERROR] stoi\n"

_LOG_FAILED_WITH_BENIGN = """\
[ERROR] Unable to connect to the server. Check if the IP:port is correct.
[INFO] Appserver detected with build version: 7.00.240223P
[ERROR] Patch file is corrupted.
"""


def _make_server(*, secure: bool = False, is_prod: bool = False) -> Server:
    return Server(
        name="qa",
        host="127.0.0.1",
        port=1234,
        build="AUTO",
        environments=["protheus_cmp"],
        default_environment="protheus_cmp",
        secure=secure,
        is_prod=is_prod,
    )


def _db(tmp_path: Path) -> sqlite3.Connection:
    conn = open_db(tmp_path / "index.db")
    apply_migrations(conn)
    return conn


def _ptm(path: Path, content: bytes = b"PATCHDATA") -> Path:
    path.write_bytes(content)
    return path


# --------------------------------------------------------------------------- #
# parse_patch_log — o achado central do smoke
# --------------------------------------------------------------------------- #
class TestParsePatchLog:
    def test_applied(self) -> None:
        assert parse_patch_log(_LOG_APPLIED) == ("applied", "")

    def test_partial_when_only_new_sources(self) -> None:
        status, detail = parse_patch_log(_LOG_PARTIAL)
        assert status == "partial"
        assert "Only new sources" in detail

    def test_failed_stoi_gives_secure_hint(self) -> None:
        status, detail = parse_patch_log(_LOG_STOI)
        assert status == "failed"
        assert "secure" in detail.lower()

    def test_failed_ignores_benign_connect_error(self) -> None:
        status, detail = parse_patch_log(_LOG_FAILED_WITH_BENIGN)
        assert status == "failed"
        # pega o erro REAL, não o benigno de conexão
        assert "corrupted" in detail
        assert "Unable to connect" not in detail

    def test_failed_when_no_success_marker(self) -> None:
        status, _ = parse_patch_log("[INFO] nada de útil aqui\n")
        assert status == "failed"


class TestExtractBuild:
    def test_extracts_build_version(self) -> None:
        assert extract_build(_LOG_APPLIED) == "7.00.240223P"

    def test_empty_when_absent(self) -> None:
        assert extract_build("nada") == ""


# --------------------------------------------------------------------------- #
# build_patch_ini — secure numérico + defrag
# --------------------------------------------------------------------------- #
class TestBuildPatchIni:
    def test_secure_is_numeric_zero(self, tmp_path: Path) -> None:
        ini = build_patch_ini(
            _make_server(secure=False), "protheus_cmp", "admin", "pwd",
            tmp_path / "p.ptm", tmp_path / "log.txt",
        )
        assert "secure=0" in ini
        assert "secure=false" not in ini.lower()

    def test_secure_numeric_one_when_true(self, tmp_path: Path) -> None:
        ini = build_patch_ini(
            _make_server(secure=True), "protheus_cmp", "admin", "pwd",
            tmp_path / "p.ptm", tmp_path / "log.txt",
        )
        assert "secure=1" in ini

    def test_defrag_only_when_requested(self, tmp_path: Path) -> None:
        base = (_make_server(), "protheus_cmp", "admin", "pwd", tmp_path / "p.ptm", tmp_path / "l")
        assert "[defragRPO]" not in build_patch_ini(*base, with_defrag=False)
        assert "[defragRPO]" in build_patch_ini(*base, with_defrag=True)

    def test_apply_old_toggles_flag(self, tmp_path: Path) -> None:
        base = (_make_server(), "protheus_cmp", "admin", "pwd", tmp_path / "p.ptm", tmp_path / "l")
        assert "applyOldProgram=False" in build_patch_ini(*base, apply_old=False)
        assert "applyOldProgram=True" in build_patch_ini(*base, apply_old=True)


# --------------------------------------------------------------------------- #
# discover_ptms — zip híbrido + ordem alfabética
# --------------------------------------------------------------------------- #
class TestDiscoverPtms:
    def test_single_ptm(self, tmp_path: Path) -> None:
        p = _ptm(tmp_path / "x.ptm")
        assert discover_ptms(p, tmp_path / "wd") == [p]

    def test_dir_alphabetical(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        _ptm(src / "b.ptm")
        _ptm(src / "a.ptm")
        _ptm(src / "ignore.txt")
        got = [p.name for p in discover_ptms(src, tmp_path / "wd")]
        assert got == ["a.ptm", "b.ptm"]

    def test_zip_extracted_internally(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "pack.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("2_second_tttm120.ptm", "B")
            zf.writestr("1_first_tttm120.ptm", "A")
            zf.writestr("leiame.txt", "ignore")
        wd = tmp_path / "wd"
        got = [p.name for p in discover_ptms(zip_path, wd)]
        assert got == ["1_first_tttm120.ptm", "2_second_tttm120.ptm"]

    def test_rejects_unknown_input(self, tmp_path: Path) -> None:
        bad = _ptm(tmp_path / "x.foo")
        with pytest.raises(ValueError, match="não suportado"):
            discover_ptms(bad, tmp_path / "wd")


# --------------------------------------------------------------------------- #
# Idempotência (DB real)
# --------------------------------------------------------------------------- #
class TestIdempotency:
    def test_is_applied_false_then_true_after_record(self, tmp_path: Path) -> None:
        conn = _db(tmp_path)
        h = sha256_file(_ptm(tmp_path / "x.ptm"))
        assert not is_applied(conn, "protheus_cmp", h)
        conn.execute(
            "INSERT INTO patches_applied (env, ptm_name, ptm_hash, status, applied_at) "
            "VALUES (?, ?, ?, 'applied', '2026-06-16T00:00:00Z')",
            ("protheus_cmp", "x.ptm", h),
        )
        conn.commit()
        assert is_applied(conn, "protheus_cmp", h)

    def test_unique_env_hash_blocks_dupes(self, tmp_path: Path) -> None:
        conn = _db(tmp_path)
        args = ("protheus_cmp", "x.ptm", "abc", "applied", "2026-06-16T00:00:00Z")
        conn.execute(
            "INSERT OR IGNORE INTO patches_applied (env, ptm_name, ptm_hash, status, applied_at) VALUES (?,?,?,?,?)",
            args,
        )
        conn.execute(
            "INSERT OR IGNORE INTO patches_applied (env, ptm_name, ptm_hash, status, applied_at) VALUES (?,?,?,?,?)",
            args,
        )
        conn.commit()
        n = conn.execute("SELECT COUNT(*) FROM patches_applied").fetchone()[0]
        assert n == 1


# --------------------------------------------------------------------------- #
# Lock por env
# --------------------------------------------------------------------------- #
class TestEnvLock:
    def test_exclusive(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "plugadvpl.apply_patch._lock_path", lambda env: tmp_path / f"{env}.lock"
        )
        with env_lock("e1"):
            with pytest.raises(RuntimeError, match="lock ocupado"):  # noqa: PT012, SIM117
                with env_lock("e1"):
                    pass

    def test_released_after_context(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "plugadvpl.apply_patch._lock_path", lambda env: tmp_path / f"{env}.lock"
        )
        with env_lock("e1"):
            pass
        # libera — segunda aquisição funciona
        with env_lock("e1"):
            pass


# --------------------------------------------------------------------------- #
# Orquestrador (advpls fake via monkeypatch)
# --------------------------------------------------------------------------- #
class TestRunApplyPatch:
    def _patch_advpls(self, monkeypatch: pytest.MonkeyPatch, logs: list[str]) -> None:
        """Substitui _run_advpls por um fake que devolve logs em sequência."""
        seq = iter(logs)

        def fake(_binary: Path, _ini: Path) -> str:
            return next(seq)

        monkeypatch.setattr("plugadvpl.apply_patch._run_advpls", fake)

    def test_happy_path_records_and_ok(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_advpls(monkeypatch, [_LOG_APPLIED])
        conn = _db(tmp_path)
        res = run_apply_patch(
            input_path=_ptm(tmp_path / "foo.ptm"),
            server=_make_server(),
            environment="protheus_cmp",
            user="admin",
            password="protheus",
            binary=Path("/fake/advpls"),
            conn=conn,
            audit_base=tmp_path / "audit",
        )
        assert isinstance(res, ApplyPatchResult)
        assert res.ok
        assert res.summary["applied"] == 1
        assert res.build == "7.00.240223P"
        assert is_applied(conn, "protheus_cmp", sha256_file(tmp_path / "foo.ptm"))

    def test_second_run_is_idempotent_skip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_advpls(monkeypatch, [_LOG_APPLIED, _LOG_APPLIED])
        conn = _db(tmp_path)
        ptm = _ptm(tmp_path / "foo.ptm")
        kw = {
            "server": _make_server(), "environment": "protheus_cmp",
            "user": "admin", "password": "protheus",
            "binary": Path("/fake/advpls"), "conn": conn, "audit_base": tmp_path / "audit",
        }
        run_apply_patch(input_path=ptm, **kw)
        res2 = run_apply_patch(input_path=ptm, **kw)
        assert res2.summary["skipped"] == 1
        assert res2.summary["applied"] == 0

    def test_partial_status_propagated(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_advpls(monkeypatch, [_LOG_PARTIAL])
        conn = _db(tmp_path)
        res = run_apply_patch(
            input_path=_ptm(tmp_path / "foo.ptm"),
            server=_make_server(), environment="protheus_cmp",
            user="admin", password="protheus", binary=Path("/fake/advpls"),
            conn=conn, audit_base=tmp_path / "audit",
        )
        assert res.ok  # partial não zera ok
        assert res.summary["partial"] == 1

    def test_failed_aborts_sequence(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # primeiro patch (a.ptm) falha -> b.ptm nem é tentado
        self._patch_advpls(monkeypatch, [_LOG_STOI, _LOG_APPLIED])
        src = tmp_path / "src"
        src.mkdir()
        _ptm(src / "a.ptm", b"A")
        _ptm(src / "b.ptm", b"B")
        conn = _db(tmp_path)
        res = run_apply_patch(
            input_path=src, server=_make_server(), environment="protheus_cmp",
            user="admin", password="protheus", binary=Path("/fake/advpls"),
            conn=conn, audit_base=tmp_path / "audit",
        )
        assert not res.ok
        assert res.summary["failed"] == 1
        assert len(res.patches) == 1  # b.ptm não foi tentado (abort)
