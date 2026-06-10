"""Testes de cli/plugadvpl/scan.py."""
from __future__ import annotations

from pathlib import Path
from unittest import mock

from plugadvpl.scan import MAX_FILE_BYTES, scan_sources, scan_sources_full


def _touch(path: Path, content: bytes = b"x") -> Path:
    """Cria arquivo com conteúdo dado, criando diretórios se necessário."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


class TestScanSources:
    def test_scans_valid_extensions(self, tmp_path: Path) -> None:
        _touch(tmp_path / "a.prw", b"User Function A() Return\n")
        _touch(tmp_path / "b.tlpp", b"User Function B() Return\n")
        _touch(tmp_path / "c.prx", b"User Function C() Return\n")
        _touch(tmp_path / "d.apw", b"User Function D() Return\n")
        # Não-fontes devem ser ignorados
        _touch(tmp_path / "readme.txt", b"hello")
        _touch(tmp_path / "config.json", b"{}")

        result = scan_sources(tmp_path)
        names = sorted(p.name for p in result)
        assert names == ["a.prw", "b.tlpp", "c.prx", "d.apw"]

    def test_skips_backup_files(self, tmp_path: Path) -> None:
        _touch(tmp_path / "a.prw", b"User Function A() Return\n")
        _touch(tmp_path / "a.prw.bak", b"old content")
        _touch(tmp_path / "b.prw.old", b"older content")
        _touch(tmp_path / "c.prw.tmp", b"temp content")
        _touch(tmp_path / "d.prw~", b"emacs bak")
        _touch(tmp_path / "e.prw.corrupted.bak", b"corrupted")
        _touch(tmp_path / "f.prw.bak2", b"bak2")

        result = scan_sources(tmp_path)
        names = sorted(p.name for p in result)
        # Apenas o "a.prw" cru deve aparecer; todos os outros têm suffix de backup
        assert names == ["a.prw"]

    def test_skips_oversized_files(self, tmp_path: Path) -> None:
        f_big = tmp_path / "big.prw"
        f_small = tmp_path / "small.prw"
        _touch(f_small, b"User Function S() Return\n")
        # Cria arquivo válido mas vamos stub-ar st_size > MAX_FILE_BYTES.
        _touch(f_big, b"User Function B() Return\n")

        real_stat = Path.stat

        def fake_stat(self: Path, *args: object, **kwargs: object) -> object:
            real = real_stat(self, *args, **kwargs)
            if self.name == "big.prw":
                # Simula arquivo gigante via objeto stub.
                class _S:
                    st_size = MAX_FILE_BYTES + 1
                    st_mtime_ns = real.st_mtime_ns

                return _S()
            return real

        with mock.patch.object(Path, "stat", fake_stat):
            result = scan_sources(tmp_path)
        names = sorted(p.name for p in result)
        assert names == ["small.prw"]

    def test_skips_empty_files(self, tmp_path: Path) -> None:
        _touch(tmp_path / "ok.prw", b"User Function A() Return\n")
        _touch(tmp_path / "empty.prw", b"")

        result = scan_sources(tmp_path)
        names = sorted(p.name for p in result)
        assert names == ["ok.prw"]

    def test_dedup_case_insensitive_basename(self, tmp_path: Path) -> None:
        # Em Windows o FS é case-insensitive — não conseguimos criar tanto FATA050.prw
        # quanto FATA050.PRW no mesmo dir. Simulamos os.walk retornando ambos.
        target_file = tmp_path / "FATA050.prw"
        _touch(target_file, b"User Function FATA050() Return\n")

        real_walk = __import__("os").walk

        def fake_walk(top: Path | str) -> object:
            for dirpath, dirnames, filenames in real_walk(top):
                # Adiciona variante uppercase para simular FS case-insensitive listando duplo
                augmented = (
                    [*list(filenames), "FATA050.PRW"]
                    if "FATA050.prw" in filenames
                    else filenames
                )
                yield dirpath, dirnames, augmented

        with mock.patch("plugadvpl.scan.os.walk", fake_walk):
            result = scan_sources(tmp_path)
        names = [p.name for p in result]
        assert len(names) == 1  # Dedup garantido

    def test_skips_plugadvpl_subdir(self, tmp_path: Path) -> None:
        _touch(tmp_path / "real.prw", b"User Function R() Return\n")
        _touch(tmp_path / ".plugadvpl" / "index.db", b"fake-db-content")
        _touch(tmp_path / ".plugadvpl" / "cache.prw", b"User Function C() Return\n")
        # Não fonte ADVPL mesmo — também devemos garantir que nem desceríamos
        _touch(tmp_path / ".git" / "stuff.prw", b"User Function X() Return\n")
        _touch(tmp_path / "node_modules" / "lib.prw", b"User Function Y() Return\n")
        _touch(tmp_path / ".venv" / "lib.prw", b"User Function Z() Return\n")

        result = scan_sources(tmp_path)
        names = sorted(p.name for p in result)
        assert names == ["real.prw"]


class TestScanSourcesFullCollisions:
    """v0.9.5 (QA PERF 2026-05-18 #2): colisao real de basename em diretorios
    distintos era silenciosamente descartada. ``scan_sources_full`` deve
    detectar e reportar.
    """

    def test_no_collision_when_unique_basenames(self, tmp_path: Path) -> None:
        _touch(tmp_path / "mod1" / "FOO.prw", b"User Function FOO() Return\n")
        _touch(tmp_path / "mod2" / "BAR.prw", b"User Function BAR() Return\n")

        result = scan_sources_full(tmp_path)
        assert len(result.files) == 2
        assert result.collisions == {}

    def test_detects_real_collision_across_dirs(self, tmp_path: Path) -> None:
        # mod1/MATA010.prw e mod2/MATA010.prw — colisao real em diretorios
        # distintos. Cenario classico em projetos Protheus com copia por modulo.
        _touch(tmp_path / "mod1" / "MATA010.prw", b"User Function A() Return\n")
        _touch(tmp_path / "mod2" / "MATA010.prw", b"User Function A() Return\n")
        _touch(tmp_path / "mod3" / "MATA010.prw", b"User Function A() Return\n")

        result = scan_sources_full(tmp_path)
        # Apenas o primeiro encontrado entra em files (dedup mantido).
        assert len(result.files) == 1
        # Mas todos os 3 ficam registrados em collisions.
        assert "mata010.prw" in result.collisions
        assert len(result.collisions["mata010.prw"]) == 3

    def test_fs_case_variant_same_dir_is_not_collision(
        self, tmp_path: Path
    ) -> None:
        """Windows FS case-insensitive listando ``FATA050.prw`` e
        ``FATA050.PRW`` na MESMA pasta nao deve contar como colisao real.
        Simula via os.walk monkey-patch."""
        target_file = tmp_path / "FATA050.prw"
        _touch(target_file, b"User Function FATA050() Return\n")

        real_walk = __import__("os").walk

        def fake_walk(top: Path | str) -> object:
            for dirpath, dirnames, filenames in real_walk(top):
                augmented = (
                    [*list(filenames), "FATA050.PRW"]
                    if "FATA050.prw" in filenames
                    else filenames
                )
                yield dirpath, dirnames, augmented

        with mock.patch("plugadvpl.scan.os.walk", fake_walk):
            result = scan_sources_full(tmp_path)
        # Mesma pasta → dedup do FS → NAO conta como colisao real.
        assert len(result.files) == 1
        assert result.collisions == {}

    def test_wrapper_scan_sources_still_returns_list(self, tmp_path: Path) -> None:
        """Backward-compat: ``scan_sources`` ainda retorna ``list[Path]``
        (os 3 callers em cli.py / ingest.py / docs nao quebram)."""
        _touch(tmp_path / "mod1" / "DUP.prw", b"User Function D() Return\n")
        _touch(tmp_path / "mod2" / "DUP.prw", b"User Function D() Return\n")

        result = scan_sources(tmp_path)
        assert isinstance(result, list)
        assert len(result) == 1  # Dedup ainda silencioso aqui — wrapper compat.


class TestScanWithIgnore:
    """scan_sources_full(root, ignore=...) — issue #141."""

    def test_ignore_excludes_directory(self, tmp_path: Path) -> None:
        from plugadvpl.ignore import IgnoreMatcher
        _touch(tmp_path / "ativo" / "A.prw", b"User Function A() Return\n")
        _touch(tmp_path / "descontinuado" / "B.prw", b"User Function B() Return\n")
        res = scan_sources_full(tmp_path, ignore=IgnoreMatcher(["descontinuado/"]))
        assert {p.name for p in res.files} == {"A.prw"}

    def test_ignore_basename_glob(self, tmp_path: Path) -> None:
        from plugadvpl.ignore import IgnoreMatcher
        _touch(tmp_path / "X.prw", b"User Function X() Return\n")
        _touch(tmp_path / "X_old.prw", b"User Function Y() Return\n")
        res = scan_sources_full(tmp_path, ignore=IgnoreMatcher(["*_old.prw"]))
        assert {p.name for p in res.files} == {"X.prw"}

    def test_ignored_list_populated_and_sorted(self, tmp_path: Path) -> None:
        from plugadvpl.ignore import IgnoreMatcher
        _touch(tmp_path / "ativo" / "A.prw", b"User Function A() Return\n")
        _touch(tmp_path / "descontinuado" / "B.prw", b"User Function B() Return\n")
        res = scan_sources_full(tmp_path, ignore=IgnoreMatcher(["descontinuado/"]))
        assert res.ignored == ["B.prw"]   # ordenado + dedup, consistente com files

    def test_no_ignore_is_unchanged(self, tmp_path: Path) -> None:
        _touch(tmp_path / "descontinuado" / "B.prw", b"User Function B() Return\n")
        res = scan_sources_full(tmp_path)        # default None → byte-idêntico ao de hoje
        assert {p.name for p in res.files} == {"B.prw"}
        assert res.ignored == []
