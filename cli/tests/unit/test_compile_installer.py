"""Testes do plugadvpl.compile_installer (v0.8.6)."""
from __future__ import annotations

import io
import os
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from plugadvpl.compile_installer import (
    InstallPlan,
    InstallResult,
    execute_copy,
    execute_download,
    installed_binary_path,
    is_installed,
    plan_copy,
    plan_download,
)


class TestPaths:
    def test_installed_path_under_home(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        p = installed_binary_path()
        assert tmp_path in p.parents
        assert ".plugadvpl" in str(p)
        assert "advpls" in p.name

    def test_is_installed_false_when_missing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert is_installed() is False


class TestPlanCopy:
    def test_plan_contains_source_target_and_size(self, tmp_path: Path) -> None:
        src = tmp_path / "advpls.exe"
        src.write_bytes(b"x" * (5 * 1024 * 1024))  # 5MB fake binary
        plan = plan_copy(src)
        assert plan.action == "copy"
        assert str(src.parent) in plan.source
        assert plan.estimated_size_mb >= 5
        assert plan.needs_network is False
        # Description não vaza nada secreto
        assert "MB" in plan.description


class TestPlanDownload:
    def test_plan_has_marketplace_url(self) -> None:
        plan = plan_download()
        assert plan.action == "download"
        assert "marketplace.visualstudio.com" in plan.source
        assert plan.estimated_size_mb == 118
        assert plan.needs_network is True


class TestExecuteCopy:
    def test_copies_binary_and_companions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Setup: source dir com advpls + 1 dll companion
        src_dir = tmp_path / "source_bin"
        src_dir.mkdir()
        bin_name = "advpls.exe" if os.name == "nt" else "advpls"
        src_bin = src_dir / bin_name
        src_bin.write_bytes(b"fake binary content")
        companion = src_dir / "qt_libs.dll"
        companion.write_bytes(b"fake companion lib")

        monkeypatch.setattr(Path, "home", lambda: tmp_path / "fake_home")
        plan = plan_copy(src_bin)
        result = execute_copy(plan)

        assert result.ok is True
        assert result.binary_path is not None
        assert result.binary_path.is_file()
        assert result.binary_path.name == bin_name
        # Companion também foi copiado
        assert (result.binary_path.parent / "qt_libs.dll").is_file()
        # Bytes contabilizados
        assert result.bytes_written > 0

    def test_copy_fails_if_binary_missing_in_source(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # source_dir só tem companion, sem o binário esperado
        src_dir = tmp_path / "bad_source"
        src_dir.mkdir()
        (src_dir / "qt_libs.dll").write_bytes(b"only dll")
        fake_bin = src_dir / "advpls.exe"  # path informado mas arquivo inexistente
        # plan_copy precisa que source_binary exista pra ler tamanho — vamos
        # construir plan manualmente apontando pra binário que não chegará
        # depois (simulando edge case onde source_dir não tem o nome esperado)
        bin_name = "advpls.exe" if os.name == "nt" else "advpls"
        target = tmp_path / "fake_home" / ".plugadvpl" / "advpls" / "bin" / "x" / bin_name
        plan = InstallPlan(
            action="copy", source=str(src_dir), target_binary=target,
            estimated_size_mb=1, needs_network=False, description="test",
        )
        result = execute_copy(plan)
        assert result.ok is False
        assert "não chegou" in result.error or "não chegou" in result.error.lower()


class TestExecuteDownload:
    def _make_fake_vsix(self, tmp_path: Path) -> Path:
        """Cria .vsix fake com layout esperado da tds-vscode."""
        vsix = tmp_path / "fake.vsix"
        os_sub = {"nt": "windows", "posix": "linux"}.get(os.name, "linux")
        if os.name == "nt":
            os_sub = "windows"
        bin_in_vsix = (
            f"extension/node_modules/@totvs/tds-ls/bin/{os_sub}/"
            f"advpls{'.exe' if os.name == 'nt' else ''}"
        )
        companion_in_vsix = f"extension/node_modules/@totvs/tds-ls/bin/{os_sub}/qt.dll"

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(bin_in_vsix, b"fake advpls binary")
            zf.writestr(companion_in_vsix, b"fake companion")
            # Lixo que deve ser ignorado
            zf.writestr("extension/package.json", b'{"name": "tds-vscode"}')
            zf.writestr("extension.vsixmanifest", b"<?xml ?>")
        vsix.write_bytes(buf.getvalue())
        return vsix

    def test_download_extracts_only_bin_subdir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_vsix = self._make_fake_vsix(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "fake_home")

        plan = plan_download()
        # Mock urlretrieve pra usar fake_vsix
        def fake_retrieve(url: str, dst: str) -> tuple[str, object]:
            import shutil
            shutil.copy(fake_vsix, dst)
            return dst, None

        with patch("plugadvpl.compile_installer.urllib.request.urlretrieve",
                   side_effect=fake_retrieve):
            result = execute_download(plan)

        assert result.ok is True, result.error
        assert result.binary_path is not None
        assert result.binary_path.is_file()
        # Companion foi extraído também
        assert (result.binary_path.parent / "qt.dll").is_file()
        # Pasta-mãe NÃO tem package.json (extração só de bin/<os>/)
        assert not (result.binary_path.parent / "package.json").exists()

    def test_download_handles_corrupt_vsix(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path / "fake_home")
        plan = plan_download()
        def fake_retrieve(url: str, dst: str) -> tuple[str, object]:
            Path(dst).write_bytes(b"not a zip")
            return dst, None
        with patch("plugadvpl.compile_installer.urllib.request.urlretrieve",
                   side_effect=fake_retrieve):
            result = execute_download(plan)
        assert result.ok is False
        assert "corromp" in result.error.lower() or "zip" in result.error.lower()
