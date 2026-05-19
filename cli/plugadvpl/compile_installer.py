"""Gerencia instalação do binário advpls em pasta interna do plugadvpl.

UX: SEMPRE explica o que vai fazer e pede confirmação antes de qualquer
operação destrutiva ou pesada (download de ~118MB, cópia de pasta inteira).

Estrutura final em ``~/.plugadvpl/advpls/bin/<os>/advpls[.exe]``:
- Windows: ``%USERPROFILE%\\.plugadvpl\\advpls\\bin\\windows\\advpls.exe``
- Linux:   ``$HOME/.plugadvpl/advpls/bin/linux/advpls``
- macOS:   ``$HOME/.plugadvpl/advpls/bin/mac/advpls``

``_detect_advpls()`` em ``compile_doctor.py`` checa esse path com prioridade
alta, depois de env var e antes da extensão tds-vscode.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_MARKETPLACE_VSIX_URL = (
    "https://marketplace.visualstudio.com/_apis/public/gallery/publishers/"
    "TOTVS/vsextensions/tds-vscode/latest/vspackage"
)

# Subdir do binário dentro do .vsix extraído
_VSIX_ADVPLS_REL = "extension/node_modules/@totvs/tds-ls/bin"


def install_dir() -> Path:
    """``~/.plugadvpl/advpls/`` — pasta interna do plugadvpl pra advpls."""
    return Path.home() / ".plugadvpl" / "advpls"


def _os_subdir() -> str:
    """Subdir conforme OS (alinhado com layout da extensão tds-vscode)."""
    if os.name == "nt":
        return "windows"
    if sys.platform == "darwin":
        return "mac"
    return "linux"


def _binary_filename() -> str:
    return "advpls.exe" if os.name == "nt" else "advpls"


def installed_binary_path() -> Path:
    """Path esperado do advpls instalado pelo plugadvpl. Pode não existir ainda."""
    return install_dir() / "bin" / _os_subdir() / _binary_filename()


def is_installed() -> bool:
    """True se advpls já está instalado na pasta interna."""
    return installed_binary_path().is_file()


@dataclass(frozen=True)
class InstallPlan:
    """Plano de instalação. Mostre ao usuário ANTES de executar."""

    action: str  # "copy" | "download"
    source: str  # path ou URL
    target_binary: Path
    estimated_size_mb: int
    needs_network: bool
    description: str  # multi-line, mostrar pro user


@dataclass(frozen=True)
class InstallResult:
    """Resultado pós-instalação."""

    ok: bool
    binary_path: Path | None
    bytes_written: int
    error: str = ""


def plan_copy(source_binary: Path) -> InstallPlan:
    """Cria plano de cópia de um advpls existente pra pasta interna.

    ``source_binary`` deve ser o path completo do ``advpls[.exe]``. A função
    também copia outros arquivos da mesma pasta (DLLs/SOs que advpls pode
    precisar). Não toca em filesystem ainda — só monta o plano.
    """
    target = installed_binary_path()
    source_dir = source_binary.parent
    # Estima tamanho da pasta inteira (pode ter DLLs companion)
    total = sum(f.stat().st_size for f in source_dir.iterdir() if f.is_file())
    size_mb = max(1, total // (1024 * 1024))
    return InstallPlan(
        action="copy",
        source=str(source_dir),
        target_binary=target,
        estimated_size_mb=size_mb,
        needs_network=False,
        description=(
            f"COPIAR de:    {source_dir}\n"
            f"  para:       {target.parent}\n"
            f"  binário:    {target.name}\n"
            f"  tamanho:    ~{size_mb} MB (pasta inteira — inclui DLLs companion)\n"
            f"  sem rede:   operação 100% local"
        ),
    )


def plan_download() -> InstallPlan:
    """Cria plano de download da extensão tds-vscode do Marketplace VSCode."""
    target = installed_binary_path()
    return InstallPlan(
        action="download",
        source=_MARKETPLACE_VSIX_URL,
        target_binary=target,
        estimated_size_mb=118,
        needs_network=True,
        description=(
            f"BAIXAR de:    Marketplace VSCode público (Microsoft)\n"
            f"  URL:        {_MARKETPLACE_VSIX_URL}\n"
            f"  tamanho:    ~118 MB (extensão completa .vsix)\n"
            f"  extrair:    binário advpls e companions (~40 MB) pra {target.parent}\n"
            f"  descartar:  resto do .vsix após extração\n"
            f"  precisa:    conexão internet"
        ),
    )


def execute_copy(
    plan: InstallPlan,
    progress: Callable[[str], None] | None = None,
) -> InstallResult:
    """Executa cópia (plano gerado por ``plan_copy``).

    ``progress`` opcional: callback recebendo strings de status.
    """
    if plan.action != "copy":
        return InstallResult(ok=False, binary_path=None, bytes_written=0,
                             error="execute_copy requer action='copy'")
    source_dir = Path(plan.source)
    target_dir = plan.target_binary.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    if progress:
        progress(f"copiando {source_dir} → {target_dir}")

    written = 0
    for src_file in source_dir.iterdir():
        if not src_file.is_file():
            continue
        dst_file = target_dir / src_file.name
        shutil.copy2(src_file, dst_file)
        written += dst_file.stat().st_size

    # Em POSIX, garante exec bit no binário
    if os.name == "posix" and plan.target_binary.is_file():
        cur = plan.target_binary.stat().st_mode
        plan.target_binary.chmod(cur | 0o755)

    if not plan.target_binary.is_file():
        return InstallResult(
            ok=False, binary_path=None, bytes_written=written,
            error=f"binário {plan.target_binary.name} não chegou ao destino — "
                  f"verifique se {source_dir} continha {plan.target_binary.name}",
        )
    return InstallResult(
        ok=True, binary_path=plan.target_binary, bytes_written=written,
    )


def execute_download(
    plan: InstallPlan,
    progress: Callable[[str], None] | None = None,
) -> InstallResult:
    """Executa download + extração (plano gerado por ``plan_download``).

    Baixa .vsix do Marketplace, extrai só ``bin/<os>/`` pra pasta interna,
    descarta o resto.
    """
    if plan.action != "download":
        return InstallResult(ok=False, binary_path=None, bytes_written=0,
                             error="execute_download requer action='download'")

    target = plan.target_binary
    target_dir = target.parent
    target_dir.mkdir(parents=True, exist_ok=True)

    if progress:
        progress(f"baixando .vsix de {plan.source[:60]}...")

    with tempfile.TemporaryDirectory(prefix="plugadvpl-vsix-") as td:
        td_path = Path(td)
        vsix_path = td_path / "tds-vscode.vsix"
        try:
            urllib.request.urlretrieve(plan.source, str(vsix_path))
        except urllib.error.URLError as exc:
            return InstallResult(
                ok=False, binary_path=None, bytes_written=0,
                error=f"falha de rede ao baixar .vsix: {exc}",
            )

        if progress:
            progress(f"extraindo binário advpls do .vsix ({vsix_path.stat().st_size // 1024 // 1024} MB)")

        # Extrai apenas a subpasta bin/<os>/ — descarta o resto pra economizar espaço
        prefix = f"{_VSIX_ADVPLS_REL}/{_os_subdir()}/"
        try:
            with zipfile.ZipFile(vsix_path) as zf:
                members = [m for m in zf.namelist() if m.startswith(prefix)]
                if not members:
                    return InstallResult(
                        ok=False, binary_path=None, bytes_written=0,
                        error=f"vsix não contém {prefix} — formato mudou? "
                              f"Reporte bug em https://github.com/JoniPraia/plugadvpl",
                    )
                for member in members:
                    # member ex: extension/node_modules/.../bin/windows/advpls.exe
                    rel = member[len(prefix):]
                    if not rel:  # entry da pasta vazia
                        continue
                    dst = target_dir / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(dst, "wb") as out:
                        shutil.copyfileobj(src, out)
        except zipfile.BadZipFile as exc:
            return InstallResult(
                ok=False, binary_path=None, bytes_written=0,
                error=f".vsix baixado está corrompido: {exc}",
            )

    if os.name == "posix" and target.is_file():
        cur = target.stat().st_mode
        target.chmod(cur | 0o755)

    if not target.is_file():
        return InstallResult(
            ok=False, binary_path=None, bytes_written=0,
            error=f"extração OK mas binário {target.name} não encontrado em {target_dir}",
        )

    written = sum(
        f.stat().st_size
        for f in target_dir.iterdir() if f.is_file()
    )
    return InstallResult(ok=True, binary_path=target, bytes_written=written)
