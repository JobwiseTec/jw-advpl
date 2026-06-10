"""Descoberta de arquivos ADVPL/TLPP no projeto cliente.

Usa ``os.walk`` (1 traversal) em vez de ``Path.rglob`` (N traversals por padrão),
aplicando filtros de extensão, dedup case-insensitive e limites de tamanho.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plugadvpl.ignore import IgnoreMatcher

VALID_EXTENSIONS = frozenset({".prw", ".tlpp", ".prx", ".apw"})

# Sufixos de backup tipicamente gerados por editores e ferramentas Protheus.
# Match case-sensitive — backup tools usualmente preservam o sufixo literal.
SKIP_SUFFIXES = (".bak", ".corrupted.bak", ".old", ".bak2", ".tmp", "~")

# Limite superior — fontes ADVPL legítimos raramente passam de ~500KB.
# Acima de 5MB é quase certo lixo (binário renomeado, dump, etc.).
MAX_FILE_BYTES = 5_000_000

# Diretórios ignorados durante descida (não-source ou nosso próprio índice).
_SKIP_DIRS = frozenset({".plugadvpl", ".git", "node_modules", ".venv"})


@dataclass(frozen=True)
class ScanResult:
    """Resultado de ``scan_sources_full``.

    ``files``: lista de fontes selecionadas (dedup aplicado, primeiro a vencer).
    ``collisions``: mapa ``basename_lower → [paths]`` quando 2+ arquivos
    em **diretórios diferentes** compartilham o mesmo basename. Não inclui
    falsas colisões de FS case-insensitive (mesmo arquivo, casing diferente).
    """

    files: list[Path]
    collisions: dict[str, list[Path]] = field(default_factory=dict)
    # v0.34 (#141): basenames excluídos por .plugadvplignore/--exclude (ordenado, dedup).
    ignored: list[str] = field(default_factory=list)


def scan_sources_full(root: Path, *, ignore: IgnoreMatcher | None = None) -> ScanResult:
    """Scan ``root`` recursivamente listando fontes ADVPL/TLPP, com diagnóstico
    de colisões de basename.

    Aplica os mesmos filtros de :func:`scan_sources` mas **também coleta**
    colisões reais por basename — quando dois ``.prw`` com mesmo nome moram
    em diretórios distintos (ex: ``mod1/MATA010.prw`` vs ``mod2/MATA010.prw``).

    Em Protheus isso aparece em projetos com cópias por cliente/módulo/backup
    limpo. Sem o aviso, o segundo ocorrência era silenciosamente descartada
    (esquema usa basename como PK), o que mascarava perda de fonte.

    Não conta como colisão um mesmo arquivo listado com casings diferentes
    pelo FS (filtra por ``parent``: se a pasta-pai for a mesma, é dedup
    legítimo do FS, não colisão real).
    """
    files: list[Path] = []
    seen: dict[str, Path] = {}
    collisions: dict[str, list[Path]] = {}
    ignored: list[str] = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Mutate dirnames in-place para que os.walk pule esses subdirs (não desce neles).
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

        for fname in filenames:
            # Backup suffix — endswith case-sensitive
            if any(fname.endswith(suf) for suf in SKIP_SUFFIXES):
                continue

            # Extension filter — case-insensitive
            ext = Path(fname).suffix.lower()
            if ext not in VALID_EXTENSIONS:
                continue

            full = Path(dirpath) / fname

            # .plugadvplignore / --exclude (#141): filtra arquivo a arquivo (sem podar
            # dir) pra que ``ignored`` capture os fontes — usado pelo prune do ingest.
            if ignore is not None:
                rel_f = os.path.relpath(full, root).replace(os.sep, "/")
                if ignore.matches(rel_f):
                    ignored.append(fname)
                    continue

            try:
                size = full.stat().st_size
            except OSError:
                # Permissão negada / link quebrado / race entre walk e stat — pula.
                continue
            if size == 0 or size > MAX_FILE_BYTES:
                continue

            # Dedup case-insensitive sobre basename
            key = fname.lower()
            if key in seen:
                first = seen[key]
                # Colisão REAL = mesmo basename em diretórios distintos.
                # Casing variante na mesma pasta (Windows FS quirk) não conta.
                if first.parent != full.parent:
                    if key not in collisions:
                        collisions[key] = [first]
                    collisions[key].append(full)
                continue
            seen[key] = full
            files.append(full)

    return ScanResult(
        files=sorted(files, key=lambda p: p.name.lower()),
        collisions=collisions,
        ignored=sorted(set(ignored)),
    )


def scan_sources(root: Path, *, ignore: IgnoreMatcher | None = None) -> list[Path]:
    """Scan ``root`` recursivamente listando fontes ADVPL/TLPP.

    Wrapper compatível de :func:`scan_sources_full` que retorna apenas a
    lista de arquivos. Use ``scan_sources_full`` se precisar do diagnóstico
    de colisões ou da lista de ignorados.
    """
    return scan_sources_full(root, ignore=ignore).files
