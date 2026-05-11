"""Testes de cli/plugadvpl/db.py."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.db import _is_network_share


class TestIsNetworkShare:
    def test_local_drive_windows(self) -> None:
        assert _is_network_share(Path("C:/Users/foo")) is False
        assert _is_network_share(Path("customizados-local")) is False

    def test_unc_path_windows(self) -> None:
        assert _is_network_share(Path(r"\\server\share\folder")) is True
        assert _is_network_share(Path("//server/share/folder")) is True

    def test_local_unix(self) -> None:
        assert _is_network_share(Path("/home/user/project")) is False
        assert _is_network_share(Path("/var/tmp")) is False
