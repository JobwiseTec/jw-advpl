"""Banco de dados SQLite — abertura, PRAGMAs, migrations, network share detection."""
from __future__ import annotations

from pathlib import Path


def _is_network_share(path: Path) -> bool:
    """Detecta se um path está em network share (SMB/CIFS/UNC).

    WAL não funciona em network filesystem (docs SQLite oficiais —
    https://sqlite.org/wal.html). Quando True, ``open_db`` usa
    ``journal_mode=DELETE`` em vez de WAL.

    Detecta:

    - UNC paths Windows: ``\\\\server\\share`` (backslash-backslash prefix).
    - POSIX-style UNC: ``//server/share`` (forward-slash prefix).
    - Mapped drives em Windows (Z: apontando para share) NÃO são detectados
      aqui por simplicidade — usuário recebe warning explícito se WAL falhar
      durante uso (SQLite retorna erro nesse caso).
    """
    s = str(path)
    return s.startswith("\\\\") or s.startswith("//")
