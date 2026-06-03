"""Ingestão de projetos PO UI: descobre package.json com @po-ui/*, persiste.

Cache por hash+mtime (modelo ingest_ini). Ignora node_modules/dist/.angular.
Fase 2: também extrai chamadas HttpClient dos .ts -> poui_datasources.
Fase 3b: também extrai uso de componentes <po-*> dos .html -> poui_componentes_uso.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from plugadvpl.parsing.poui import (
    extract_angular_http_calls,
    extract_poui_template_usage,
    parse_poui_package_json,
)

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

_SKIP_DIRS = {"node_modules", "dist", ".angular", ".git", "tmp"}


@dataclass(slots=True)
class IngestPouiResult:
    ingested: int = 0
    skipped: int = 0


def _ingest_datasources(conn: sqlite3.Connection, proj_root: Path) -> None:
    """Varre .ts do projeto, extrai HttpClient calls -> poui_datasources.

    Limpa as do projeto antes (rebuild atômico por projeto)."""
    proj_abs = str(proj_root.resolve())
    conn.execute("DELETE FROM poui_datasources WHERE caminho LIKE ?", (proj_abs + "%",))
    for ts in proj_root.rglob("*.ts"):
        if any(part in _SKIP_DIRS for part in ts.relative_to(proj_root).parts):
            continue
        try:
            txt = ts.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for call in extract_angular_http_calls(txt):
            conn.execute(
                "INSERT INTO poui_datasources (caminho, linha, verbo, url_raw, path_norm) "
                "VALUES (?, ?, ?, ?, ?)",
                (str(ts.resolve()), call["linha"], call["verbo"], call["url"], call["path_norm"]),
            )


def _ingest_template_usage(conn: sqlite3.Connection, proj_root: Path) -> None:
    """Varre .html do projeto, extrai uso de componentes po-* -> poui_componentes_uso.

    Limpa os do projeto antes (rebuild atômico por projeto)."""
    proj_abs = str(proj_root.resolve())
    conn.execute("DELETE FROM poui_componentes_uso WHERE caminho LIKE ?", (proj_abs + "%",))
    for html in proj_root.rglob("*.html"):
        if any(part in _SKIP_DIRS for part in html.relative_to(proj_root).parts):
            continue
        try:
            txt = html.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for usage in extract_poui_template_usage(txt):
            conn.execute(
                "INSERT INTO poui_componentes_uso (caminho, linha, componente, binding, kind) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    str(html.resolve()),
                    usage["linha"],
                    usage["componente"],
                    usage["binding"],
                    usage["kind"],
                ),
            )


def _discover(root: Path) -> list[Path]:
    out: list[Path] = []
    for pkg in root.rglob("package.json"):
        # Só poda dirs de skip ABAIXO de root — um ancestral homônimo (ex: root
        # dentro de .../tmp/) não pode mascarar o projeto. (cf. scan.py/ingest.py)
        rel = pkg.relative_to(root)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        out.append(pkg)
    return out


def ingest_poui_dir(
    conn: sqlite3.Connection, root: Path, *, force: bool = False
) -> IngestPouiResult:
    res = IngestPouiResult()
    for pkg_path in _discover(root):
        try:
            raw = pkg_path.read_bytes()
        except OSError:
            continue
        proj = parse_poui_package_json(raw.decode("utf-8", errors="replace"))
        if proj is None:
            continue
        caminho = str(pkg_path.resolve())
        h = hashlib.sha256(raw).hexdigest()
        mtime = pkg_path.stat().st_mtime_ns
        if not force:
            cur = conn.execute(
                "SELECT hash, mtime_ns FROM poui_projetos WHERE caminho = ?", (caminho,)
            ).fetchone()
            if cur and cur[0] == h and cur[1] == mtime:
                res.skipped += 1
                continue
        conn.execute(
            """
            INSERT INTO poui_projetos
                (caminho, poui_version, poui_major, angular_version, angular_major,
                 compativel, pacotes_json, hash, mtime_ns)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(caminho) DO UPDATE SET
                poui_version=excluded.poui_version, poui_major=excluded.poui_major,
                angular_version=excluded.angular_version, angular_major=excluded.angular_major,
                compativel=excluded.compativel, pacotes_json=excluded.pacotes_json,
                hash=excluded.hash, mtime_ns=excluded.mtime_ns,
                indexed_at=datetime('now')
            """,
            (
                caminho,
                proj.poui_version,
                proj.poui_major,
                proj.angular_version,
                proj.angular_major,
                1 if proj.compativel else 0,
                json.dumps(proj.poui_packages, ensure_ascii=False),
                h,
                mtime,
            ),
        )
        _ingest_datasources(conn, pkg_path.parent)
        _ingest_template_usage(conn, pkg_path.parent)
        res.ingested += 1
    conn.commit()
    return res
