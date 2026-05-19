"""Testes do plugadvpl.compile_servers (v0.8.7)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from plugadvpl.compile_servers import (
    Server,
    ServersRegistry,
    add_server,
    default_server,
    get_server,
    import_from_tds_vscode,
    list_servers,
    load_registry,
    registry_path,
    remove_server,
    save_registry,
    tds_vscode_servers_path,
)


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Mock Path.home() pra evitar tocar no registry real do user."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


class TestPaths:
    def test_registry_under_home(self, fake_home: Path) -> None:
        assert fake_home in registry_path().parents
        assert registry_path().name == "servers.json"

    def test_tds_path_under_home(self, fake_home: Path) -> None:
        assert fake_home in tds_vscode_servers_path().parents


class TestLoadSave:
    def test_load_empty_when_no_file(self, fake_home: Path) -> None:
        r = load_registry()
        assert r.default == ""
        assert r.servers == []

    def test_load_after_save_roundtrip(self, fake_home: Path) -> None:
        s = Server(
            name="dev", host="127.0.0.1", port=1234, build="7.00.240223P",
            environments=["P2510"], default_environment="P2510",
        )
        save_registry(ServersRegistry(default="dev", servers=[s]))
        loaded = load_registry()
        assert loaded.default == "dev"
        assert len(loaded.servers) == 1
        assert loaded.servers[0].name == "dev"
        assert loaded.servers[0].port == 1234

    def test_load_malformed_json_returns_empty(self, fake_home: Path) -> None:
        path = registry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not valid json {{{", encoding="utf-8")
        r = load_registry()
        assert r.servers == []


class TestAddRemove:
    def test_add_first_becomes_default(self, fake_home: Path) -> None:
        s = Server(name="a", host="h", port=1234, build="b",
                   environments=["e"], default_environment="e")
        add_server(s)
        assert default_server() is not None
        assert default_server().name == "a"

    def test_add_replaces_same_name(self, fake_home: Path) -> None:
        s1 = Server(name="a", host="h1", port=1234, build="b",
                    environments=["e"], default_environment="e")
        s2 = Server(name="a", host="h2", port=5678, build="b",
                    environments=["e"], default_environment="e")
        add_server(s1)
        add_server(s2)
        servers = list_servers()
        assert len(servers) == 1
        assert servers[0].host == "h2"
        assert servers[0].port == 5678

    def test_add_make_default_changes_default(self, fake_home: Path) -> None:
        s1 = Server(name="a", host="h", port=1, build="b",
                    environments=["e"], default_environment="e")
        s2 = Server(name="b", host="h", port=2, build="b",
                    environments=["e"], default_environment="e")
        add_server(s1)
        add_server(s2, make_default=True)
        assert default_server().name == "b"

    def test_remove_existing_returns_true(self, fake_home: Path) -> None:
        s = Server(name="x", host="h", port=1, build="b",
                   environments=["e"], default_environment="e")
        add_server(s)
        assert remove_server("x") is True
        assert list_servers() == []

    def test_remove_missing_returns_false(self, fake_home: Path) -> None:
        assert remove_server("nonexistent") is False

    def test_remove_default_promotes_first_remaining(self, fake_home: Path) -> None:
        s1 = Server(name="a", host="h", port=1, build="b",
                    environments=["e"], default_environment="e")
        s2 = Server(name="b", host="h", port=2, build="b",
                    environments=["e"], default_environment="e")
        add_server(s1, make_default=True)
        add_server(s2)
        remove_server("a")
        assert default_server().name == "b"


class TestGetServer:
    def test_get_existing(self, fake_home: Path) -> None:
        s = Server(name="x", host="h", port=1, build="b",
                   environments=["e"], default_environment="e")
        add_server(s)
        result = get_server("x")
        assert result is not None
        assert result.host == "h"

    def test_get_missing_returns_none(self, fake_home: Path) -> None:
        assert get_server("nonexistent") is None


class TestImportTdsVscode:
    def test_returns_empty_when_file_missing(self, fake_home: Path) -> None:
        assert import_from_tds_vscode() == []

    def test_imports_tds_vscode_format(self, fake_home: Path) -> None:
        """Formato real do TDS-VSCode servers.json."""
        tds_path = tds_vscode_servers_path()
        tds_path.parent.mkdir(parents=True, exist_ok=True)
        tds_path.write_text(json.dumps({
            "version": "0.2.0",
            "configurations": [
                {
                    "id": "uuid1",
                    "type": "totvs_server_protheus",
                    "name": "dev-local",
                    "address": "127.0.0.1",
                    "port": 1234,
                    "build": "7.00.240223P",
                    "secure": 0,
                    "environments": [
                        {"name": "P2510", "id": "env1"},
                        {"name": "TEST", "id": "env2"},
                    ],
                },
                {
                    "id": "uuid2",
                    "type": "totvs_server_protheus",
                    "name": "hml-vps",
                    "address": "vps.example.com",
                    "port": 1234,
                    "build": "7.00.240223P",
                    "secure": 1,
                    "environments": [{"name": "HML", "id": "envh"}],
                },
            ],
        }), encoding="utf-8")

        imported = import_from_tds_vscode()
        assert len(imported) == 2
        dev = next(s for s in imported if s.name == "dev-local")
        assert dev.host == "127.0.0.1"
        assert dev.port == 1234
        assert dev.build == "7.00.240223P"
        assert dev.environments == ["P2510", "TEST"]
        assert dev.default_environment == "P2510"
        assert dev.secure is False
        hml = next(s for s in imported if s.name == "hml-vps")
        assert hml.secure is True

    def test_skips_entries_without_name(self, fake_home: Path) -> None:
        tds_path = tds_vscode_servers_path()
        tds_path.parent.mkdir(parents=True, exist_ok=True)
        tds_path.write_text(json.dumps({
            "configurations": [
                {"id": "x", "address": "1.2.3.4", "port": 1234},  # sem name
            ],
        }), encoding="utf-8")
        assert import_from_tds_vscode() == []

    def test_handles_malformed_json(self, fake_home: Path) -> None:
        tds_path = tds_vscode_servers_path()
        tds_path.parent.mkdir(parents=True, exist_ok=True)
        tds_path.write_text("invalid", encoding="utf-8")
        assert import_from_tds_vscode() == []

    def test_reads_buildVersion_field_v0_8_11(self, fake_home: Path) -> None:
        """v0.8.11 bug 1: TDS-VSCode usa 'buildVersion', não 'build'.

        Regressão: antes do fix, build vinha vazio e --use-server quebrava.
        """
        tds_path = tds_vscode_servers_path()
        tds_path.parent.mkdir(parents=True, exist_ok=True)
        tds_path.write_text(json.dumps({
            "configurations": [
                {
                    "name": "from-tds",
                    "address": "127.0.0.1",
                    "port": 1234,
                    "buildVersion": "7.00.240223P",  # campo correto do TDS
                    "environments": [{"name": "P2510"}],
                },
            ],
        }), encoding="utf-8")
        imported = import_from_tds_vscode()
        assert len(imported) == 1
        assert imported[0].build == "7.00.240223P"

    def test_imports_includes_from_tds_v0_8_11(self, fake_home: Path) -> None:
        """v0.8.11 bug 1: TDS-VSCode tem 'includes', plugin perdia antes."""
        tds_path = tds_vscode_servers_path()
        tds_path.parent.mkdir(parents=True, exist_ok=True)
        tds_path.write_text(json.dumps({
            "configurations": [
                {
                    "name": "with-includes",
                    "address": "127.0.0.1",
                    "port": 1234,
                    "buildVersion": "7.00.240223P",
                    "environments": [{"name": "P2510"}],
                    "includes": [
                        "D:/TOTVS/protheus/Include",
                        "D:/Custom/Include",
                    ],
                },
            ],
        }), encoding="utf-8")
        imported = import_from_tds_vscode()
        assert len(imported) == 1
        assert imported[0].includes == [
            "D:/TOTVS/protheus/Include",
            "D:/Custom/Include",
        ]

    def test_includes_default_empty_when_missing(self, fake_home: Path) -> None:
        tds_path = tds_vscode_servers_path()
        tds_path.parent.mkdir(parents=True, exist_ok=True)
        tds_path.write_text(json.dumps({
            "configurations": [
                {
                    "name": "no-includes",
                    "address": "127.0.0.1",
                    "port": 1234,
                    "buildVersion": "7.00.240223P",
                    "environments": [{"name": "P2510"}],
                },
            ],
        }), encoding="utf-8")
        imported = import_from_tds_vscode()
        assert imported[0].includes == []
