"""Testes do módulo server."""

from __future__ import annotations

import platform
from pathlib import Path

import pytest
from rich.console import Console

from plugadvpl.dtc import faircom, server


def _server_bin_name() -> str:
    """Nome do binário do servidor que a descoberta procura no SO atual."""
    table = faircom._SERVER_BINARIES
    return table.get(platform.system(), table["_default"])[0]


def _ctstop_name() -> str:
    """Nome do ctstop que a descoberta procura no SO atual (.exe no Windows)."""
    return "ctstop.exe" if platform.system() == "Windows" else "ctstop"


def _mk_home(tmp_path: Path, *, with_ctstop: bool = True) -> Path:
    """Cria um FAIRCOM_HOME mínimo com binário do servidor (+ctstop opcional)."""
    srv = tmp_path / "server"
    srv.mkdir(parents=True, exist_ok=True)
    binary = srv / _server_bin_name()
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    if with_ctstop:
        tools = tmp_path / "tools"
        tools.mkdir(parents=True, exist_ok=True)
        ctstop = tools / _ctstop_name()
        ctstop.write_text("#!/bin/sh\n")
        ctstop.chmod(0o755)
    return tmp_path


class TestServerStart:
    def test_fails_when_no_binary(self, mocker, isolated_pid_file: Path) -> None:
        mocker.patch("plugadvpl.dtc.server.faircom.find_faircom_home", return_value=None)
        with pytest.raises(SystemExit):
            server.server_start(Console(record=True))

    def test_aborts_when_pid_file_exists(self, isolated_pid_file: Path, mocker) -> None:
        isolated_pid_file.parent.mkdir(parents=True, exist_ok=True)
        isolated_pid_file.write_text("12345")
        spy = mocker.patch("plugadvpl.dtc.server.faircom.server_binary")
        server.server_start(Console(record=True))
        spy.assert_not_called()

    def test_spawns_and_writes_pid(self, mocker, isolated_pid_file: Path, tmp_path: Path) -> None:
        home = _mk_home(tmp_path)
        mocker.patch("plugadvpl.dtc.server.faircom.find_faircom_home", return_value=home)
        fake_proc = mocker.Mock(pid=4242)
        popen = mocker.patch("plugadvpl.dtc.server.subprocess.Popen", return_value=fake_proc)

        server.server_start(Console(record=True))

        popen.assert_called_once()
        # roda a partir do diretório do binário
        assert popen.call_args.kwargs["cwd"] == (home / "server")
        assert isolated_pid_file.read_text() == "4242"


class TestServerStop:
    def test_noop_when_no_pid_file(self, isolated_pid_file: Path) -> None:
        server.server_stop(Console(record=True))

    def test_uses_ctstop_when_available(
        self, mocker, isolated_pid_file: Path, tmp_path: Path
    ) -> None:
        isolated_pid_file.parent.mkdir(parents=True, exist_ok=True)
        isolated_pid_file.write_text("4242")
        home = _mk_home(tmp_path, with_ctstop=True)
        mocker.patch("plugadvpl.dtc.server.faircom.find_faircom_home", return_value=home)
        run = mocker.patch("plugadvpl.dtc.server.subprocess.run")

        server.server_stop(Console(record=True))

        run.assert_called_once()
        args = run.call_args[0][0]
        assert str(home / "tools" / _ctstop_name()) == args[0]
        assert "-AUTO" in args
        assert not isolated_pid_file.exists()

    def test_falls_back_to_kill_on_linux(
        self, mocker, isolated_pid_file: Path, tmp_path: Path
    ) -> None:
        isolated_pid_file.parent.mkdir(parents=True, exist_ok=True)
        isolated_pid_file.write_text("4242")
        home = _mk_home(tmp_path, with_ctstop=False)
        mocker.patch("plugadvpl.dtc.server.faircom.find_faircom_home", return_value=home)
        mocker.patch("plugadvpl.dtc.server.platform.system", return_value="Linux")
        kill = mocker.patch("plugadvpl.dtc.server.os.kill")

        server.server_stop(Console(record=True))

        kill.assert_called_once()
        assert not isolated_pid_file.exists()

    def test_tolerates_dead_pid(self, mocker, isolated_pid_file: Path, tmp_path: Path) -> None:
        isolated_pid_file.parent.mkdir(parents=True, exist_ok=True)
        isolated_pid_file.write_text("4242")
        home = _mk_home(tmp_path, with_ctstop=False)
        mocker.patch("plugadvpl.dtc.server.faircom.find_faircom_home", return_value=home)
        mocker.patch("plugadvpl.dtc.server.platform.system", return_value="Linux")
        mocker.patch("plugadvpl.dtc.server.os.kill", side_effect=ProcessLookupError)

        server.server_stop(Console(record=True))

        assert not isolated_pid_file.exists()


class TestServerStatus:
    def test_no_pid_file(self, isolated_pid_file: Path) -> None:
        server.server_status(Console(record=True))  # smoke

    def test_alive_process(self, mocker, isolated_pid_file: Path) -> None:
        isolated_pid_file.parent.mkdir(parents=True, exist_ok=True)
        isolated_pid_file.write_text("4242")
        mocker.patch("plugadvpl.dtc.server._pid_alive", return_value=True)
        server.server_status(Console(record=True))
        assert isolated_pid_file.exists()  # não limpa

    def test_dead_process_cleans_pid_file(self, mocker, isolated_pid_file: Path) -> None:
        isolated_pid_file.parent.mkdir(parents=True, exist_ok=True)
        isolated_pid_file.write_text("4242")
        mocker.patch("plugadvpl.dtc.server._pid_alive", return_value=False)
        server.server_status(Console(record=True))
        assert not isolated_pid_file.exists()


class TestPidAlive:
    def test_unix_alive(self, mocker) -> None:
        mocker.patch("plugadvpl.dtc.server.platform.system", return_value="Linux")
        mocker.patch("plugadvpl.dtc.server.os.kill")
        assert server._pid_alive(4242) is True

    def test_unix_dead(self, mocker) -> None:
        mocker.patch("plugadvpl.dtc.server.platform.system", return_value="Linux")
        mocker.patch("plugadvpl.dtc.server.os.kill", side_effect=ProcessLookupError)
        assert server._pid_alive(4242) is False

    def test_windows_alive(self, mocker) -> None:
        mocker.patch("plugadvpl.dtc.server.platform.system", return_value="Windows")
        result = mocker.Mock(stdout="dtcat 4242 ...")
        mocker.patch("plugadvpl.dtc.server.subprocess.run", return_value=result)
        assert server._pid_alive(4242) is True

    def test_windows_dead(self, mocker) -> None:
        mocker.patch("plugadvpl.dtc.server.platform.system", return_value="Windows")
        result = mocker.Mock(stdout="INFO: No tasks found")
        mocker.patch("plugadvpl.dtc.server.subprocess.run", return_value=result)
        assert server._pid_alive(4242) is False
