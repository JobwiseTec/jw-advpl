"""Extração de componentes-servidor empacotados (coletadb.tlpp).

O ``coletadb.tlpp`` é a fonte de verdade em ``docs/reference-impl/``; o wheel o
embarca via ``force-include`` em ``plugadvpl/server_components/``. Este módulo
resolve a fonte (wheel OU dev tree, espelhando ``_skills_root``) e copia
**byte-a-byte** pra um destino, detectando a versão pelo ``#DEFINE CDB_VERSION``.

A fonte é **LF + ASCII puro** (``.gitattributes``: ``*.tlpp text eol=lf``). A
cópia byte-a-byte preserva isso; **nunca** usar ``read_text``/``write_text`` no
``.tlpp`` (transcodificaria ou normalizaria EOL).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources as ir
from pathlib import Path

_COLETADB_NAME = "coletadb.tlpp"
_CDB_VERSION_RE = re.compile(rb'#DEFINE\s+CDB_VERSION\s+"([\d.]+)"', re.IGNORECASE)


@dataclass(frozen=True)
class ExtractResult:
    """Resultado de :func:`extract_coletadb`.

    status: ``"written"`` | ``"unchanged"`` | ``"version_mismatch"``.
    """

    status: str
    path: Path
    version_bundled: str | None
    version_existing: str | None


def _coletadb_bytes() -> bytes:
    """Bytes do ``coletadb.tlpp`` empacotado (wheel) ou em dev tree.

    Espelha ``_skills_root``: tenta ``importlib.resources`` (wheel:
    ``plugadvpl/server_components/coletadb.tlpp``); cai pro repo-root
    ``docs/reference-impl/coletadb.tlpp`` quando não empacotado (dev tree).
    """
    try:
        res = ir.files("plugadvpl") / "server_components" / _COLETADB_NAME
        return res.read_bytes()
    except (FileNotFoundError, OSError, ModuleNotFoundError):
        pass
    import plugadvpl  # noqa: PLC0415 -- lazy p/ evitar import circular

    pkg_init = Path(plugadvpl.__file__).resolve()
    dev = pkg_init.parents[2] / "docs" / "reference-impl" / _COLETADB_NAME
    return dev.read_bytes()


def coletadb_version(data: bytes) -> str | None:
    """Versão do bundle via ``#DEFINE CDB_VERSION`` (autoritativo, não o header)."""
    m = _CDB_VERSION_RE.search(data)
    return m.group(1).decode("ascii") if m else None


def extract_coletadb(dest_dir: Path, *, force: bool = False) -> ExtractResult:
    """Copia o ``coletadb.tlpp`` empacotado pra ``dest_dir`` (byte-a-byte).

    - não existe → escreve (``written``);
    - existe e bytes idênticos → no-op (``unchanged``);
    - existe e difere, sem ``force`` → não sobrescreve (``version_mismatch``);
    - ``force`` → sobrescreve (``written``).
    """
    data = _coletadb_bytes()
    ver_bundled = coletadb_version(data)
    target = dest_dir / _COLETADB_NAME

    if target.exists():
        existing = target.read_bytes()
        ver_existing = coletadb_version(existing)
        if existing == data:
            return ExtractResult("unchanged", target, ver_bundled, ver_existing)
        if not force:
            return ExtractResult("version_mismatch", target, ver_bundled, ver_existing)

    dest_dir.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return ExtractResult("written", target, ver_bundled, ver_bundled)
