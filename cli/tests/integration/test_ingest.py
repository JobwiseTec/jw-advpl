"""Integration tests for the full ingest pipeline.

Verifica end-to-end: scan -> parse -> write -> FTS rebuild. Foca no caminho
serial (workers=0) que é determinístico em todos os SOs. Caminho paralelo
tem 1 teste smoke (clamp para serial em datasets pequenos é o caso comum).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from plugadvpl.ingest import ingest


@pytest.fixture
def synthetic_dir(tmp_path: Path) -> Path:
    """Cria 3 fontes ADVPL sintéticos cobrindo MVC, MV_*, REST/TLPP."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "FATA050.prw").write_bytes(
        b"User Function FATA050()\n"
        b'  DbSelectArea("SC5")\n'
        b'  RecLock("SC5", .T.)\n'
        b'  Replace C5_NUM With "001"\n'
        b"  MsUnlock()\n"
        b"Return .T.\n"
    )
    (src / "MATA010.prw").write_bytes(
        b"User Function MATA010()\n"
        b'  Local cMV := SuperGetMV("MV_LOCALIZA", .F., "")\n'
        b"Return\n"
    )
    (src / "WSReg.tlpp").write_bytes(
        b"Namespace api\n"
        b"User Function WSReg()\n"
        b'  HttpPost("http://api.foo/x", oJson)\n'
        b"Return\n"
    )
    return src


def _connect(db_path: Path) -> sqlite3.Connection:
    """Abre o DB read-only num context manager local."""
    return sqlite3.connect(str(db_path))


class TestIngest:
    def test_ingest_creates_db_and_counts(self, synthetic_dir: Path) -> None:
        counters = ingest(synthetic_dir, workers=0)
        db = synthetic_dir / ".plugadvpl" / "index.db"
        assert db.exists()
        assert counters["arquivos_total"] == 3
        assert counters["arquivos_ok"] == 3
        assert counters["arquivos_failed"] == 0
        assert counters["duration_ms"] >= 0

    def test_ingest_populates_fontes_table(self, synthetic_dir: Path) -> None:
        ingest(synthetic_dir, workers=0)
        conn = _connect(synthetic_dir / ".plugadvpl" / "index.db")
        try:
            n = conn.execute("SELECT COUNT(*) FROM fontes").fetchone()[0]
            assert n == 3

            # FATA050 deve referenciar SC5 em tabelas_ref (modo write — RecLock).
            row = conn.execute(
                "SELECT tabelas_ref, write_tables, reclock_tables FROM fontes "
                "WHERE arquivo='FATA050.prw'"
            ).fetchone()
            tabelas_ref = json.loads(row[0])
            write_tables = json.loads(row[1])
            reclock_tables = json.loads(row[2])
            # tabelas_ref = read; write_tables / reclock_tables incluem SC5
            assert "SC5" in (tabelas_ref + write_tables + reclock_tables)

            # fonte_tabela normalizada também deve ter (FATA050.prw, SC5, *).
            ft_rows = conn.execute(
                "SELECT modo FROM fonte_tabela WHERE arquivo='FATA050.prw' AND tabela='SC5'"
            ).fetchall()
            assert len(ft_rows) >= 1

            # caminho_relativo deve usar forward slash, relativo a root.
            rel = conn.execute(
                "SELECT caminho_relativo FROM fontes WHERE arquivo='FATA050.prw'"
            ).fetchone()[0]
            assert "/" in rel or rel == "FATA050.prw"
            assert "\\" not in rel
        finally:
            conn.close()

    def test_ingest_populates_fts5(self, synthetic_dir: Path) -> None:
        ingest(synthetic_dir, workers=0)
        conn = _connect(synthetic_dir / ".plugadvpl" / "index.db")
        try:
            # FTS5 deve permitir busca por RecLock no content de FATA050.
            rows = conn.execute(
                "SELECT arquivo FROM fonte_chunks_fts WHERE fonte_chunks_fts MATCH 'RecLock'"
            ).fetchall()
            assert any("FATA050" in r[0] for r in rows), f"got: {rows}"

            # Trigram FTS deve achar substring 'SuperGetMV'
            rows_tri = conn.execute(
                "SELECT rowid FROM fonte_chunks_fts_tri "
                "WHERE fonte_chunks_fts_tri MATCH 'SuperGetMV'"
            ).fetchall()
            assert len(rows_tri) >= 1
        finally:
            conn.close()

    def test_ingest_incremental_skips_unchanged(self, synthetic_dir: Path) -> None:
        first = ingest(synthetic_dir, workers=0)
        assert first["arquivos_ok"] == 3
        # 2ª ingest sem mudança no FS: nada deve ser re-parseado.
        second = ingest(synthetic_dir, workers=0, incremental=True)
        assert second["arquivos_total"] == 3
        assert second["arquivos_skipped"] == 3
        assert second["arquivos_ok"] == 0

    def test_ingest_no_content_mode(self, synthetic_dir: Path) -> None:
        ingest(synthetic_dir, workers=0, no_content=True)
        conn = _connect(synthetic_dir / ".plugadvpl" / "index.db")
        try:
            rows = conn.execute("SELECT content FROM fonte_chunks").fetchall()
            assert rows, "deve haver pelo menos uma chunk"
            assert all(r[0] in ("", None) for r in rows)
        finally:
            conn.close()

    def test_ingest_no_content_metrics_still_correct_v0_9_2(
        self, tmp_path: Path
    ) -> None:
        """v0.9.2 (QA PERF #3): métricas devem ser corretas mesmo com --no-content.

        Antes: chunk_content="" → body=""→ extract_function_metrics em string
        vazia → CC=1, nesting=0 silenciosamente (corrompia métricas em modo
        privacy).
        """
        src = tmp_path / "src"
        src.mkdir()
        # Função com complexidade real: 4 IFs aninhados + 1 WHILE + 1 OR.
        # Mínimo esperado: CC ~6+, nesting ~3+.
        (src / "ComplexFunc.prw").write_bytes(
            b"User Function MyComplex()\n"
            b"  Local i\n"
            b"  If A == 1 .Or. B == 2\n"
            b"    If C == 3\n"
            b"      While i < 10\n"
            b"        If D == 4\n"
            b"          i++\n"
            b"        EndIf\n"
            b"      EndDo\n"
            b"    EndIf\n"
            b"  EndIf\n"
            b"Return\n"
        )
        ingest(src, workers=0, no_content=True)
        conn = _connect(src / ".plugadvpl" / "index.db")
        try:
            row = conn.execute(
                "SELECT cc, nesting, loc FROM fonte_metrics WHERE funcao='MyComplex'"
            ).fetchone()
            assert row is not None, "fonte_metrics deve ter a função MyComplex"
            cc, nesting, loc = row
            # Antes do fix: cc=1, nesting=0, loc=12 (LOC sempre correto, vinha de linha_inicio/fim)
            # Depois: cc deve refletir os 4 IFs + WHILE + OR (CC >= 5)
            assert cc >= 5, f"CC esperado >=5, veio {cc} (bug v0.9.2 não corrigido)"
            assert nesting >= 3, f"nesting esperado >=3, veio {nesting}"
            assert loc == 12
            # Confirma que o content do chunk continua vazio (modo privacy ativo)
            content_row = conn.execute(
                "SELECT content FROM fonte_chunks WHERE funcao='MyComplex'"
            ).fetchone()
            assert content_row[0] in ("", None)
        finally:
            conn.close()

    def test_ingest_redact_secrets(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "Secret.prw").write_bytes(
            b"User Function Secret()\n"
            b'  HttpPost("http://user:p4ssw0rd@api.foo/x", oJson)\n'
            b'  Local cTok := "abcdef0123456789abcdef0123456789abcdef0123"\n'
            b"Return\n"
        )
        ingest(src, workers=0, redact_secrets=True)
        conn = _connect(src / ".plugadvpl" / "index.db")
        try:
            urls = conn.execute("SELECT url_literal FROM http_calls").fetchall()
            assert urls
            # URL com creds deve ter sido redacted.
            assert all("p4ssw0rd" not in u[0] for u in urls)
            assert any("REDACTED" in u[0] for u in urls)
        finally:
            conn.close()

    def test_ingest_populates_lint_findings_and_meta(
        self, synthetic_dir: Path
    ) -> None:
        ingest(synthetic_dir, workers=0)
        conn = _connect(synthetic_dir / ".plugadvpl" / "index.db")
        try:
            # Meta deve refletir totais e parser_version.
            valor_parser = conn.execute(
                "SELECT valor FROM meta WHERE chave='parser_version'"
            ).fetchone()
            assert valor_parser is not None
            assert valor_parser[0].startswith("p")

            valor_total = conn.execute(
                "SELECT valor FROM meta WHERE chave='total_arquivos'"
            ).fetchone()
            assert int(valor_total[0]) == 3

            # indexed_at gravado
            iat = conn.execute(
                "SELECT valor FROM meta WHERE chave='indexed_at'"
            ).fetchone()
            assert iat is not None and iat[0]
        finally:
            conn.close()

    def test_ingest_parallel_streams_results_v0_9_5(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """QA PERF 2026-05-18 #4: _ingest_parallel deve iterar pool.map
        lazy (writes acontecem DURANTE a iteração), não materializar
        ``list(pool.map(...))`` antes do primeiro write. Reduz pico de RAM
        em monorepos grandes.

        Teste smoking-gun: instrumenta pool.map pra marcar
        ``iter_finished`` quando o iterador fecha, e ``_write_parsed`` pra
        contar writes ANTES desse marcador. Código antigo (``list(...)``)
        exauria o iterador primeiro → 0 writes durante iteração. Código
        novo (iter direto) → N writes durante iteração.
        """
        from concurrent.futures import ProcessPoolExecutor

        from plugadvpl import ingest as ing

        src = tmp_path / "src"
        src.mkdir()
        for i in range(4):
            (src / f"f{i}.prw").write_bytes(
                f"User Function F{i}()\nReturn\n".encode("cp1252")
            )

        monkeypatch.setattr(ing, "_PARALLEL_THRESHOLD", 2)
        monkeypatch.setattr(ing, "_PARALLEL_MIN_FILES", 2)

        iter_finished = [False]
        writes_during_iteration = [0]

        original_write = ing._write_parsed

        def tracking_write(*args: object, **kwargs: object) -> None:
            if not iter_finished[0]:
                writes_during_iteration[0] += 1
            return original_write(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(ing, "_write_parsed", tracking_write)

        original_map = ProcessPoolExecutor.map

        def tracking_map(self: ProcessPoolExecutor, *args: object, **kwargs: object) -> object:
            inner = original_map(self, *args, **kwargs)  # type: ignore[arg-type]

            def wrapped() -> object:
                try:
                    for item in inner:  # type: ignore[union-attr]
                        yield item
                finally:
                    iter_finished[0] = True

            return wrapped()

        monkeypatch.setattr(ProcessPoolExecutor, "map", tracking_map)

        counters = ing.ingest(src, workers=2)
        assert counters["arquivos_ok"] == 4
        assert writes_during_iteration[0] >= 1, (
            f"Streaming quebrado: writes_during_iteration="
            f"{writes_during_iteration[0]}, iter_finished="
            f"{iter_finished[0]}. Código antigo chamava list(pool.map(...)) "
            f"e exauria o iterador antes de qualquer write."
        )


class TestIngestIgnore:
    """ingest respeita .plugadvplignore + --exclude (issue #141)."""

    def _db(self, root: Path) -> Path:
        return root / ".plugadvpl" / "index.db"

    def test_plugadvplignore_excludes_dir(self, tmp_path: Path) -> None:
        (tmp_path / "ativo").mkdir()
        (tmp_path / "ativo" / "A.prw").write_text("User Function A()\nReturn\n", encoding="utf-8")
        (tmp_path / "descontinuado").mkdir()
        (tmp_path / "descontinuado" / "B.prw").write_text(
            "User Function B()\nReturn\n", encoding="utf-8"
        )
        (tmp_path / ".plugadvplignore").write_text("descontinuado/\n", encoding="utf-8")

        counters = ingest(tmp_path, workers=0, incremental=False)

        conn = _connect(self._db(tmp_path))
        rows = {r[0] for r in conn.execute("SELECT arquivo FROM fontes")}
        assert rows == {"A.prw"}
        assert counters["arquivos_ignorados"] == 1

    def test_reingest_prunes_newly_ignored(self, tmp_path: Path) -> None:
        (tmp_path / "B.prw").write_text("User Function B()\nReturn\n", encoding="utf-8")
        ingest(tmp_path, workers=0, incremental=False)
        assert {
            r[0] for r in _connect(self._db(tmp_path)).execute("SELECT arquivo FROM fontes")
        } == {"B.prw"}

        (tmp_path / ".plugadvplignore").write_text("B.prw\n", encoding="utf-8")
        counters = ingest(tmp_path, workers=0, incremental=True)
        assert {
            r[0] for r in _connect(self._db(tmp_path)).execute("SELECT arquivo FROM fontes")
        } == set()
        assert counters["arquivos_ignorados_removidos"] == 1

    def test_exclude_param(self, tmp_path: Path) -> None:
        (tmp_path / "A.prw").write_text("User Function A()\nReturn\n", encoding="utf-8")
        (tmp_path / "poc-x.prw").write_text("User Function P()\nReturn\n", encoding="utf-8")
        counters = ingest(tmp_path, workers=0, incremental=False, exclude=["poc-*"])
        rows = {r[0] for r in _connect(self._db(tmp_path)).execute("SELECT arquivo FROM fontes")}
        assert rows == {"A.prw"}
        assert counters["arquivos_ignorados"] == 1
