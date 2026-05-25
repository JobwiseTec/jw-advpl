"""Testes unit do modulo plugadvpl.tq — restart + healthcheck."""
from __future__ import annotations

import subprocess
from unittest import mock

import pytest

from plugadvpl.compile_servers import Server
from plugadvpl.tq import TqResult, _http_probe, run_tq


def _make_server(name: str = "test-srv", restart_cmd: str = "echo restart") -> Server:
    """Server de teste com defaults razoáveis."""
    return Server(
        name=name,
        host="127.0.0.1",
        port=8019,
        build="7.00.240223P",
        environments=["env_a"],
        default_environment="env_a",
        restart_cmd=restart_cmd,
    )


class TestHttpProbe:
    """_http_probe(host, port) -> (is_up, status_code)."""

    def test_returns_true_status_for_200_response(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AppServer respondendo HTTP 200 → (True, 200)."""
        fake_conn = mock.MagicMock()
        fake_conn.getresponse.return_value = mock.MagicMock(status=200)

        def fake_http_connection(host, port, timeout):  # noqa: ARG001
            return fake_conn

        monkeypatch.setattr(
            "plugadvpl.tq.http.client.HTTPConnection", fake_http_connection
        )
        is_up, status = _http_probe("127.0.0.1", 8019, timeout=2.0)
        assert is_up is True
        assert status == 200

    def test_returns_false_when_connection_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AppServer down (TCP refused) → (False, 0)."""
        def raise_refused(*args, **kwargs):  # noqa: ARG001
            raise ConnectionRefusedError("nope")
        monkeypatch.setattr(
            "plugadvpl.tq.http.client.HTTPConnection", raise_refused
        )
        is_up, status = _http_probe("127.0.0.1", 8019)
        assert is_up is False
        assert status == 0


class TestRunTq:
    """run_tq(server, timeout_s, no_healthcheck) -> TqResult."""

    def test_happy_path_restart_then_healthcheck_up(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """restart_cmd exit 0 + healthcheck retorna 200 no 3o ping → ok=True."""
        srv = _make_server(restart_cmd="echo restart")

        # Mock subprocess.run pra exit_code=0
        fake_run = mock.MagicMock(return_value=mock.MagicMock(
            returncode=0, stderr=""
        ))
        monkeypatch.setattr("plugadvpl.tq.subprocess.run", fake_run)

        # Mock _http_probe: 2 falhas + 1 sucesso
        probe_calls = [(False, 0), (False, 0), (True, 200)]
        probe_iter = iter(probe_calls)
        monkeypatch.setattr(
            "plugadvpl.tq._http_probe",
            lambda *a, **kw: next(probe_iter),
        )
        # Mock time.sleep pra não esperar de verdade
        monkeypatch.setattr("plugadvpl.tq.time.sleep", lambda s: None)

        result = run_tq(srv, timeout_s=60)
        assert result.ok is True
        assert result.healthcheck_status == "up"
        assert result.healthcheck_attempts == 3
        assert result.restart_exit_code == 0
        assert result.error == ""

    def test_empty_restart_cmd_returns_error_without_subprocess(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Server com restart_cmd vazio nao roda subprocess, retorna ok=False."""
        srv = _make_server(restart_cmd="")
        fake_run = mock.MagicMock()
        monkeypatch.setattr("plugadvpl.tq.subprocess.run", fake_run)

        result = run_tq(srv, timeout_s=60)
        assert result.ok is False
        assert "sem restart_cmd" in result.error
        assert "--set-restart-cmd" in result.error
        assert result.healthcheck_status == "not_run"
        fake_run.assert_not_called()

    def test_restart_exit_non_zero_captures_stderr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Restart cmd que falha -> ok=False com stderr capturado."""
        srv = _make_server(restart_cmd="false")
        fake_run = mock.MagicMock(return_value=mock.MagicMock(
            returncode=1, stderr="boom\n"
        ))
        monkeypatch.setattr("plugadvpl.tq.subprocess.run", fake_run)

        # Healthcheck nao deve ser chamado
        probe_mock = mock.MagicMock()
        monkeypatch.setattr("plugadvpl.tq._http_probe", probe_mock)

        result = run_tq(srv, timeout_s=60)
        assert result.ok is False
        assert result.restart_exit_code == 1
        assert result.restart_stderr == "boom"
        assert result.healthcheck_status == "not_run"
        assert "exit=1" in result.error
        probe_mock.assert_not_called()

    def test_healthcheck_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Todos os probes retornam (False, 0) -> timeout."""
        srv = _make_server(restart_cmd="echo ok")
        fake_run = mock.MagicMock(return_value=mock.MagicMock(
            returncode=0, stderr=""
        ))
        monkeypatch.setattr("plugadvpl.tq.subprocess.run", fake_run)
        monkeypatch.setattr(
            "plugadvpl.tq._http_probe",
            lambda *a, **kw: (False, 0),
        )
        monkeypatch.setattr("plugadvpl.tq.time.sleep", lambda s: None)

        # Mock time.monotonic pra avancar 0, 1, 2, ..., 61 segundos
        ts = [0.0]
        def fake_mono():
            ts[0] += 1.0
            return ts[0]
        monkeypatch.setattr("plugadvpl.tq.time.monotonic", fake_mono)

        result = run_tq(srv, timeout_s=3)
        assert result.ok is False
        assert result.healthcheck_status == "timeout"
        assert "healthcheck timeout" in result.error
        assert result.healthcheck_attempts >= 1

    def test_healthcheck_5xx_does_not_count_as_up(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Status 503 nao conta como up -- continua tentando ate timeout."""
        srv = _make_server(restart_cmd="echo ok")
        monkeypatch.setattr("plugadvpl.tq.subprocess.run",
                            mock.MagicMock(return_value=mock.MagicMock(returncode=0, stderr="")))
        # _http_probe sempre (True, 503) — porta abre mas REST quebrou
        monkeypatch.setattr(
            "plugadvpl.tq._http_probe",
            lambda *a, **kw: (True, 503),
        )
        monkeypatch.setattr("plugadvpl.tq.time.sleep", lambda s: None)
        ts = [0.0]
        def fake_mono():
            ts[0] += 1.0
            return ts[0]
        monkeypatch.setattr("plugadvpl.tq.time.monotonic", fake_mono)

        result = run_tq(srv, timeout_s=3)
        assert result.ok is False
        assert result.healthcheck_status == "timeout"

    def test_no_healthcheck_skips_loop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """no_healthcheck=True -> nao chama _http_probe nem time.sleep."""
        srv = _make_server(restart_cmd="echo ok")
        monkeypatch.setattr("plugadvpl.tq.subprocess.run",
                            mock.MagicMock(return_value=mock.MagicMock(returncode=0, stderr="")))
        probe_mock = mock.MagicMock()
        sleep_mock = mock.MagicMock()
        monkeypatch.setattr("plugadvpl.tq._http_probe", probe_mock)
        monkeypatch.setattr("plugadvpl.tq.time.sleep", sleep_mock)

        result = run_tq(srv, timeout_s=60, no_healthcheck=True)
        assert result.ok is True
        assert result.healthcheck_status == "skipped"
        assert result.healthcheck_attempts == 0
        probe_mock.assert_not_called()
        sleep_mock.assert_not_called()
