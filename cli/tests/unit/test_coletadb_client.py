"""Testes do cliente HTTP do COLETADB (U5 / Fase 3b).

Mock via monkeypatch em ``urllib.request.urlopen`` — sem dep nova
(httpx/respx evitados, projeto ja usa stdlib urllib em compile_installer).

Cobertura:

- health/tables/dump/table endpoints OK
- auth bearer + basic
- 401/403/404/5xx error handling
- timeout
- paginacao (has_more loop)
- retry exponencial em 5xx
"""
from __future__ import annotations

import io
import json
from typing import Any
from unittest import mock

import pytest

from plugadvpl.coletadb_client import (
    ColetaDBClient,
    ColetaDBError,
    HealthResponse,
)


def _fake_response(status: int, body: dict | str, headers: dict[str, str] | None = None) -> Any:
    """Cria um fake response compativel com urllib.request.urlopen()."""
    if isinstance(body, dict):
        body_bytes = json.dumps(body).encode("utf-8")
    else:
        body_bytes = body.encode("utf-8")

    fake = mock.MagicMock()
    fake.status = status
    fake.read.return_value = body_bytes
    fake.headers = headers or {}
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    return fake


def _urlopen_returning(status: int, body: dict | str, headers: dict[str, str] | None = None):
    """Retorna funcao mock pra urlopen que devolve sempre o mesmo response."""
    def _mock_urlopen(req, **kwargs):  # noqa: ARG001
        if status >= 400:
            from urllib.error import HTTPError
            raise HTTPError(
                url=req.full_url if hasattr(req, "full_url") else "<test>",
                code=status,
                msg=str(body) if isinstance(body, str) else json.dumps(body),
                hdrs=headers or {},
                fp=io.BytesIO(
                    json.dumps(body).encode("utf-8")
                    if isinstance(body, dict)
                    else body.encode("utf-8")
                ),
            )
        return _fake_response(status, body, headers)

    return _mock_urlopen


class TestHealth:
    def test_health_returns_parsed_response(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = {
            "version": "1.0.0",
            "protheus_build": "7.00.240223P",
            "protheus_environment": "P2510",
            "exposed_tables": ["SX1", "SX2", "SX3"],
            "extras": [],
        }
        monkeypatch.setattr(
            "plugadvpl.coletadb_client.urlopen",
            _urlopen_returning(200, payload),
        )
        client = ColetaDBClient(
            endpoint="http://protheus:8181/rest/coletadb", token="abc",
        )
        result = client.health()

        assert isinstance(result, HealthResponse)
        assert result.version == "1.0.0"
        assert result.protheus_build == "7.00.240223P"
        assert "SX3" in result.exposed_tables

    def test_health_404_raises_with_install_hint(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "plugadvpl.coletadb_client.urlopen",
            _urlopen_returning(404, {"error": "not found", "code": "NOT_FOUND"}),
        )
        client = ColetaDBClient(endpoint="http://x/rest/coletadb", token="abc")
        with pytest.raises(ColetaDBError) as exc_info:
            client.health()
        # Mensagem deve mencionar "instalado" ou "install"
        assert "instal" in str(exc_info.value).lower()

    def test_health_401_raises_auth_error(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "plugadvpl.coletadb_client.urlopen",
            _urlopen_returning(401, {"error": "unauthorized", "code": "UNAUTHORIZED"}),
        )
        client = ColetaDBClient(endpoint="http://x/rest/coletadb", token="bad")
        with pytest.raises(ColetaDBError) as exc_info:
            client.health()
        assert "401" in str(exc_info.value) or "auth" in str(exc_info.value).lower()


class TestAuth:
    def test_bearer_auth_sends_authorization_header(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: dict[str, Any] = {}

        def capturing_urlopen(req, **kwargs):  # noqa: ARG001
            captured["url"] = req.full_url
            captured["headers"] = dict(req.headers)
            return _fake_response(200, {
                "version": "1.0.0",
                "protheus_build": "X",
                "protheus_environment": "Y",
                "exposed_tables": [],
                "extras": [],
            })

        monkeypatch.setattr("plugadvpl.coletadb_client.urlopen", capturing_urlopen)
        client = ColetaDBClient(
            endpoint="http://x/rest/coletadb",
            token="my-bearer-token",
            auth_method="bearer",
        )
        client.health()

        # urllib normaliza headers como Title-Case
        auth = captured["headers"].get("Authorization", "")
        assert auth == "Bearer my-bearer-token"

    def test_basic_auth_sends_base64_credentials(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import base64
        captured: dict[str, Any] = {}

        def capturing_urlopen(req, **kwargs):  # noqa: ARG001
            captured["headers"] = dict(req.headers)
            return _fake_response(200, {
                "version": "1.0.0",
                "protheus_build": "X",
                "protheus_environment": "Y",
                "exposed_tables": [],
                "extras": [],
            })

        monkeypatch.setattr("plugadvpl.coletadb_client.urlopen", capturing_urlopen)
        client = ColetaDBClient(
            endpoint="http://x/rest/coletadb",
            user="admin",
            password="secret",
            auth_method="basic",
        )
        client.health()

        expected = "Basic " + base64.b64encode(b"admin:secret").decode("ascii")
        assert captured["headers"]["Authorization"] == expected


class TestDump:
    def test_dump_single_table_no_pagination(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        payload = {
            "tables": {
                "SX2": {
                    "row_count": 2,
                    "rows": [
                        {"X2_CHAVE": "SA1", "X2_NOME": "Clientes", "X2_MODO": "C"},
                        {"X2_CHAVE": "SC5", "X2_NOME": "Pedidos", "X2_MODO": "E"},
                    ],
                }
            }
        }
        monkeypatch.setattr(
            "plugadvpl.coletadb_client.urlopen",
            _urlopen_returning(200, payload),
        )
        client = ColetaDBClient(endpoint="http://x/rest/coletadb", token="abc")
        result = client.get_dump(["SX2"])

        assert "SX2" in result
        assert result["SX2"]["row_count"] == 2
        assert len(result["SX2"]["rows"]) == 2
        assert result["SX2"]["rows"][0]["X2_CHAVE"] == "SA1"

    def test_dump_paginated_follows_has_more(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Simula 2 paginas: 2 rows na 1a, 1 row na 2a, has_more=False na 2a.
        responses = [
            {
                "tables": {
                    "SX3": {
                        "row_count": 3,
                        "offset": 0,
                        "limit": 2,
                        "has_more": True,
                        "next_offset": 2,
                        "rows": [
                            {"X3_ARQUIVO": "SA1", "X3_CAMPO": "A1_COD"},
                            {"X3_ARQUIVO": "SA1", "X3_CAMPO": "A1_NOME"},
                        ],
                    }
                }
            },
            {
                "tables": {
                    "SX3": {
                        "row_count": 3,
                        "offset": 2,
                        "limit": 2,
                        "has_more": False,
                        "rows": [
                            {"X3_ARQUIVO": "SA1", "X3_CAMPO": "A1_EMAIL"},
                        ],
                    }
                }
            },
        ]
        call_count = [0]

        def paginated_urlopen(req, **kwargs):  # noqa: ARG001
            payload = responses[call_count[0]]
            call_count[0] += 1
            return _fake_response(200, payload)

        monkeypatch.setattr("plugadvpl.coletadb_client.urlopen", paginated_urlopen)
        client = ColetaDBClient(
            endpoint="http://x/rest/coletadb",
            token="abc",
            paginate_limit=2,
        )
        result = client.get_dump(["SX3"])

        # Cliente deve concatenar as 2 paginas em 1 lista de 3 rows.
        assert call_count[0] == 2  # 2 requests
        assert len(result["SX3"]["rows"]) == 3
        assert result["SX3"]["rows"][2]["X3_CAMPO"] == "A1_EMAIL"


class TestRetry:
    def test_retries_on_5xx_then_succeeds(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from urllib.error import HTTPError
        call_count = [0]

        def flaky_urlopen(req, **kwargs):  # noqa: ARG001
            call_count[0] += 1
            if call_count[0] < 3:
                raise HTTPError(
                    url="<test>", code=503, msg="srv err",
                    hdrs={}, fp=io.BytesIO(b'{"error":"x"}'),
                )
            return _fake_response(200, {
                "version": "1.0.0", "protheus_build": "X",
                "protheus_environment": "Y", "exposed_tables": [], "extras": [],
            })

        monkeypatch.setattr("plugadvpl.coletadb_client.urlopen", flaky_urlopen)
        # Sleep mock to skip backoff delays in test
        monkeypatch.setattr("plugadvpl.coletadb_client.time.sleep", lambda *_: None)

        client = ColetaDBClient(
            endpoint="http://x/rest/coletadb", token="abc",
            retry_count=3, retry_backoff_s=0,
        )
        result = client.health()
        assert call_count[0] == 3  # 2 falhas + 1 success
        assert result.version == "1.0.0"

    def test_gives_up_after_retry_count_exceeded(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from urllib.error import HTTPError
        call_count = [0]

        def always_500(req, **kwargs):  # noqa: ARG001
            call_count[0] += 1
            raise HTTPError(
                url="<test>", code=500, msg="srv err",
                hdrs={}, fp=io.BytesIO(b'{"error":"x"}'),
            )

        monkeypatch.setattr("plugadvpl.coletadb_client.urlopen", always_500)
        monkeypatch.setattr("plugadvpl.coletadb_client.time.sleep", lambda *_: None)

        client = ColetaDBClient(
            endpoint="http://x/rest/coletadb", token="abc",
            retry_count=2, retry_backoff_s=0,
        )
        with pytest.raises(ColetaDBError):
            client.health()
        assert call_count[0] == 2  # initial + 1 retry = 2 attempts


class TestEndpointPath:
    def test_health_url_is_endpoint_plus_health(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured = {}

        def capturing(req, **kwargs):  # noqa: ARG001
            captured["url"] = req.full_url
            return _fake_response(200, {
                "version": "1.0.0", "protheus_build": "X",
                "protheus_environment": "Y", "exposed_tables": [], "extras": [],
            })

        monkeypatch.setattr("plugadvpl.coletadb_client.urlopen", capturing)
        client = ColetaDBClient(
            endpoint="http://protheus.cliente.com:8181/rest/coletadb",
            token="abc",
        )
        client.health()
        assert captured["url"] == "http://protheus.cliente.com:8181/rest/coletadb/health"

    def test_endpoint_strips_trailing_slash(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured = {}

        def capturing(req, **kwargs):  # noqa: ARG001
            captured["url"] = req.full_url
            return _fake_response(200, {
                "version": "1.0.0", "protheus_build": "X",
                "protheus_environment": "Y", "exposed_tables": [], "extras": [],
            })

        monkeypatch.setattr("plugadvpl.coletadb_client.urlopen", capturing)
        client = ColetaDBClient(
            endpoint="http://x/rest/coletadb/", token="abc",
        )
        client.health()
        # Nao deve ter // duplicado
        assert captured["url"] == "http://x/rest/coletadb/health"
