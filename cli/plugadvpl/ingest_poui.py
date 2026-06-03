"""Ingestão de projetos PO UI: descobre package.json com @po-ui/*, persiste.

Cache por hash+mtime (modelo ingest_ini). Ignora node_modules/dist/.angular.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from plugadvpl.parsing.poui import parse_poui_package_json

if TYPE_CHECKING:
    import sqlite3
    from pathlib import Path

_SKIP_DIRS = {"node_modules", "dist", ".angular", ".git", "tmp"}


@dataclass(slots=True)
class IngestPouiResult:
    ingested: int = 0
    skipped: int = 0


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
        res.ingested += 1
    conn.commit()
    return res
