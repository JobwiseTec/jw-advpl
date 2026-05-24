"""Testes do cliente HTTP do COLETADB — protocolo real (bundle pattern).

Pivot pos-recebimento do COLETADB.tlpp em 2026-05-21. Endpoints reais:

- POST /coletadb/run   -> manifest com files[]
- POST /coletadb/file  -> chunk bytes (octet-stream) + headers X-Total-Size/X-Chunk-Range

Mock via monkeypatch em ``urllib.request.urlopen`` (sem dep nova).
"""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from plugadvpl.coletadb_client import (
    BundleFile,
    ColetaDBClient,
    ColetaDBError,
    Manifest,
)


def _fake_json_response(status: int, body: dict | str, headers: dict[str, str] | None = None):
    if isinstance(body, dict):
        body_bytes = json.dumps(body).encode("utf-8")
    else:
        body_bytes = body.encode("utf-8")
    fake = mock.MagicMock()
    fake.status = status
    fake.read.return_value = body_bytes
    fake.headers = headers or {}
    # urlopen returns context manager
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    return fake


def _fake_binary_response(
    status: int, body: bytes, headers: dict[str, str] | None = None,
):
    fake = mock.MagicMock()
    fake.status = status
    fake.read.return_value = body
    fake.headers = headers or {}
    fake.__enter__.return_value = fake
    fake.__exit__.return_value = False
    return fake


def _urlopen_returning(status: int, body: bytes | dict | str, headers: dict[str, str] | None = None):
    """Retorna funcao mock pra urlopen."""

    def _mock_urlopen(req, **kwargs):  # noqa: ARG001
        if status >= 400:
            from urllib.error import HTTPError
            body_bytes = (
                body if isinstance(body, bytes)
                else (json.dumps(body).encode("utf-8") if isinstance(body, dict) else body.encode("utf-8"))
            )
            raise HTTPError(
                url=req.full_url if hasattr(req, "full_url") else "<test>",
                code=status,
                msg=str(body) if isinstance(body, str) else "err",
                hdrs=headers or {},
                fp=io.BytesIO(body_bytes),
            )
        if isinstance(body, bytes):
            return _fake_binary_response(status, body, headers)
        return _fake_json_response(status, body, headers)

    return _mock_urlopen


class TestRun:
    def test_run_returns_manifest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = {
            "bundle_id": "abc123",
            "bundle_dir": "\\temp\\20260521_153000_abc\\",
            "modo": "enxuto",
            "threshold": 10,
            "chunk_size": 4194304,
            "files": [
                {
                    "name": "SX3.csv",
                    "path": "\\temp\\20260521_153000_abc\\SX3.csv",
                    "size_bytes": 12345678,
                    "chunks": 3,
                    "sha256": "abc" * 21 + "a",  # 64 chars
                },
            ],
        }
        monkeypatch.setattr(
            "plugadvpl.coletadb_client.urlopen",
            _urlopen_returning(200, payload),
        )
        client = ColetaDBClient(
            endpoint="http://protheus:8181/rest",
            user="admin", password="pwd",
        )
        manifest = client.run(modo="enxuto", threshold=10)

        assert isinstance(manifest, Manifest)
        assert manifest.bundle_id == "abc123"
        assert manifest.modo == "enxuto"
        assert len(manifest.files) == 1
        assert manifest.files[0].name == "SX3.csv"
        assert manifest.files[0].size_bytes == 12345678
        assert manifest.files[0].chunks == 3

    def test_run_sends_correct_body(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        def capturing_urlopen(req, **kwargs):  # noqa: ARG001
            captured["url"] = req.full_url
            captured["body"] = req.data
            captured["headers"] = dict(req.headers)
            return _fake_json_response(200, {
                "bundle_id": "x", "bundle_dir": "y",
                "modo": "completo", "threshold": 5,
                "chunk_size": 4194304, "files": [],
            })

        monkeypatch.setattr("plugadvpl.coletadb_client.urlopen", capturing_urlopen)
        client = ColetaDBClient(
            endpoint="http://protheus:8181/rest", user="admin", password="pwd",
        )
        client.run(modo="completo", threshold=5)

        assert captured["url"] == "http://protheus:8181/rest/coletadb/run"
        body = json.loads(captured["body"].decode("utf-8"))
        assert body["modo"] == "completo"
        assert body["threshold"] == 5

    def test_run_404_raises_with_install_hint(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "plugadvpl.coletadb_client.urlopen",
            _urlopen_returning(404, {"error": "not found"}),
        )
        client = ColetaDBClient(
            endpoint="http://protheus:8181/rest", user="admin", password="pwd",
        )
        with pytest.raises(ColetaDBError) as exc_info:
            client.run()
        # Hint deve mencionar compilar COLETADB.tlpp ou similar
        assert exc_info.value.hint is not None
        assert (
            "compilar" in exc_info.value.hint.lower()
            or "coletadb" in exc_info.value.hint.lower()
        )

    def test_run_401_raises_auth_error(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            "plugadvpl.coletadb_client.urlopen",
            _urlopen_returning(401, {"error": "unauthorized"}),
        )
        client = ColetaDBClient(
            endpoint="http://protheus:8181/rest", user="admin", password="bad",
        )
        with pytest.raises(ColetaDBError) as exc_info:
            client.run()
        assert exc_info.value.status == 401


class TestSmokeRegression:
    """Regressao do smoke test contra Protheus real (2026-05-23)."""

    def test_post_bytes_sends_accept_star(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """Smoke 2026-05-23: REST framework do Protheus rejeita
        'Accept: application/octet-stream' com HTTP 400 antes do WSMETHOD.
        Cliente DEVE enviar 'Accept: */*' no /file."""
        captured: dict[str, Any] = {}

        def capturing(req, **kwargs):  # noqa: ARG001
            captured["headers"] = dict(req.headers)
            return _fake_binary_response(
                200, b"data",
                headers={"X-Total-Size": "4", "Content-Length": "4"},
            )

        monkeypatch.setattr("plugadvpl.coletadb_client.urlopen", capturing)
        client = ColetaDBClient(
            endpoint="http://x/rest", user="u", password="p", chunk_size=4,
        )
        import hashlib
        bf = BundleFile(
            name="t.csv", path="/tmp/t.csv", size_bytes=4, chunks=1,
            sha256=hashlib.sha256(b"data").hexdigest(),
        )
        client.download_file(bf, tmp_path / "t.csv")
        # Accept header DEVE ser */* (HTTP normaliza pra Title-Case '*/*')
        assert captured["headers"]["Accept"] == "*/*"

    def test_400_error_exposes_server_body(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Smoke 2026-05-23: erro 400 do server pode ter JSON estruturado
        tipo {'error': 'msg'} — cliente DEVE expor essa msg pro usuario."""
        monkeypatch.setattr(
            "plugadvpl.coletadb_client.urlopen",
            _urlopen_returning(400, {"error": "campo X obrigatorio"}),
        )
        client = ColetaDBClient(
            endpoint="http://x/rest", user="u", password="p",
        )
        with pytest.raises(ColetaDBError) as exc_info:
            client.run()
        msg = str(exc_info.value)
        assert "campo X obrigatorio" in msg

    def test_500_error_exposes_server_body(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Smoke 2026-05-23: erro 500 tambem deve mostrar body do server
        (ate o ultimo retry). Plugin nao silencia mensagens."""
        monkeypatch.setattr(
            "plugadvpl.coletadb_client.urlopen",
            _urlopen_returning(500, {"error": "Postgres ENCODE syntax error"}),
        )
        monkeypatch.setattr("plugadvpl.coletadb_client.time.sleep", lambda *_: None)
        client = ColetaDBClient(
            endpoint="http://x/rest", user="u", password="p",
            retry_count=1, retry_backoff_s=0,
        )
        with pytest.raises(ColetaDBError) as exc_info:
            client.run()
        msg = str(exc_info.value)
        assert "Postgres ENCODE syntax error" in msg

    def test_401_with_server_msg_includes_it_in_error(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Erro de auth com mensagem do server vira hint completo."""
        monkeypatch.setattr(
            "plugadvpl.coletadb_client.urlopen",
            _urlopen_returning(401, {"error": "user 'X' nao tem permissao REST"}),
        )
        client = ColetaDBClient(
            endpoint="http://x/rest", user="X", password="p",
        )
        with pytest.raises(ColetaDBError) as exc_info:
            client.run()
        msg = str(exc_info.value)
        assert "user 'X' nao tem permissao" in msg


class TestAuth:
    def test_basic_auth_sends_authorization_header(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: dict[str, Any] = {}

        def capturing_urlopen(req, **kwargs):  # noqa: ARG001
            captured["headers"] = dict(req.headers)
            return _fake_json_response(200, {
                "bundle_id": "x", "bundle_dir": "y", "modo": "enxuto",
                "threshold": 10, "chunk_size": 4194304, "files": [],
            })

        monkeypatch.setattr("plugadvpl.coletadb_client.urlopen", capturing_urlopen)
        client = ColetaDBClient(
            endpoint="http://protheus:8181/rest", user="admin", password="secret",
        )
        client.run()

        import base64
        expected = "Basic " + base64.b64encode(b"admin:secret").decode("ascii")
        assert captured["headers"]["Authorization"] == expected


class TestDownloadFile:
    def test_single_chunk_download(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        import hashlib
        content = b"X3_ARQUIVO,X3_CAMPO,X3_TIPO\nSA1,A1_COD,C\n"
        sha = hashlib.sha256(content).hexdigest()

        bf = BundleFile(
            name="SX3.csv",
            path="\\temp\\bundle\\SX3.csv",
            size_bytes=len(content),
            chunks=1,
            sha256=sha,
        )

        def single_chunk_urlopen(req, **kwargs):  # noqa: ARG001
            return _fake_binary_response(
                200, content,
                headers={
                    "X-Total-Size": str(len(content)),
                    "X-Chunk-Range": f"0-{len(content)-1}/{len(content)}",
                    "Content-Length": str(len(content)),
                },
            )

        monkeypatch.setattr("plugadvpl.coletadb_client.urlopen", single_chunk_urlopen)

        client = ColetaDBClient(
            endpoint="http://x/rest", user="u", password="p",
            chunk_size=1024 * 1024,
        )
        dest = tmp_path / "SX3.csv"
        bytes_written = client.download_file(bf, dest)

        assert bytes_written == len(content)
        assert dest.read_bytes() == content

    def test_multi_chunk_download_reassembles(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        import hashlib
        # 3 chunks de 10 bytes
        full_content = b"0123456789ABCDEFGHIJabcdefghij"
        sha = hashlib.sha256(full_content).hexdigest()
        bf = BundleFile(
            name="data.csv",
            path="\\temp\\bundle\\data.csv",
            size_bytes=len(full_content),
            chunks=3,
            sha256=sha,
        )

        call_idx = [0]
        chunks = [full_content[0:10], full_content[10:20], full_content[20:30]]

        def chunked_urlopen(req, **kwargs):  # noqa: ARG001
            i = call_idx[0]
            call_idx[0] += 1
            chunk = chunks[i]
            return _fake_binary_response(
                200, chunk,
                headers={
                    "X-Total-Size": str(len(full_content)),
                    "X-Chunk-Range": f"{i*10}-{(i+1)*10-1}/{len(full_content)}",
                    "Content-Length": str(len(chunk)),
                },
            )

        monkeypatch.setattr("plugadvpl.coletadb_client.urlopen", chunked_urlopen)

        client = ColetaDBClient(
            endpoint="http://x/rest", user="u", password="p",
            chunk_size=10,
        )
        dest = tmp_path / "data.csv"
        bytes_written = client.download_file(bf, dest)

        assert bytes_written == len(full_content)
        assert dest.read_bytes() == full_content
        assert call_idx[0] == 3  # 3 chunks pedidos

    def test_sha256_mismatch_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        content = b"correct content"
        # Hash de OUTRO conteudo — vai dar mismatch
        bf = BundleFile(
            name="x.csv",
            path="\\temp\\x.csv",
            size_bytes=len(content),
            chunks=1,
            sha256="0" * 64,  # claramente errado
        )

        def urlopen_correct_bytes(req, **kwargs):  # noqa: ARG001
            return _fake_binary_response(
                200, content,
                headers={
                    "X-Total-Size": str(len(content)),
                    "Content-Length": str(len(content)),
                },
            )

        monkeypatch.setattr("plugadvpl.coletadb_client.urlopen", urlopen_correct_bytes)

        client = ColetaDBClient(
            endpoint="http://x/rest", user="u", password="p",
            chunk_size=1024,
        )
        with pytest.raises(ColetaDBError) as exc_info:
            client.download_file(bf, tmp_path / "x.csv")
        assert exc_info.value.code == "SHA256_MISMATCH"


class TestHashAlgo:
    """Verificacao de hash com algoritmo dinamico (v1.0.3+ do servidor)."""

    def _setup_download(
        self,
        monkeypatch: pytest.MonkeyPatch,
        content: bytes,
    ) -> None:
        def urlopen_bytes(req, **kwargs):  # noqa: ARG001
            return _fake_binary_response(
                200, content,
                headers={
                    "X-Total-Size": str(len(content)),
                    "Content-Length": str(len(content)),
                },
            )
        monkeypatch.setattr("plugadvpl.coletadb_client.urlopen", urlopen_bytes)

    def test_sha1_hash_verified(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        import hashlib
        content = b"hello sha1 world"
        sha1 = hashlib.sha1(content).hexdigest()
        bf = BundleFile(
            name="x.csv", path="\\temp\\x.csv",
            size_bytes=len(content), chunks=1, sha256="",
            hash=sha1, hash_algo="sha1", hash_partial=False,
        )
        self._setup_download(monkeypatch, content)
        client = ColetaDBClient(endpoint="http://x/rest", user="u", password="p")
        # Nao deve raise — sha1 bate
        client.download_file(bf, tmp_path / "x.csv")

    def test_md5_hash_verified(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        import hashlib
        content = b"hello md5 world"
        md5 = hashlib.md5(content).hexdigest()
        bf = BundleFile(
            name="x.csv", path="\\temp\\x.csv",
            size_bytes=len(content), chunks=1, sha256="",
            hash=md5, hash_algo="md5", hash_partial=False,
        )
        self._setup_download(monkeypatch, content)
        client = ColetaDBClient(endpoint="http://x/rest", user="u", password="p")
        client.download_file(bf, tmp_path / "x.csv")

    def test_sha1_mismatch_raises(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        content = b"correct bytes"
        bf = BundleFile(
            name="x.csv", path="\\temp\\x.csv",
            size_bytes=len(content), chunks=1, sha256="",
            hash="0" * 40, hash_algo="sha1", hash_partial=False,
        )
        self._setup_download(monkeypatch, content)
        client = ColetaDBClient(endpoint="http://x/rest", user="u", password="p")
        with pytest.raises(ColetaDBError) as exc_info:
            client.download_file(bf, tmp_path / "x.csv")
        assert exc_info.value.code == "SHA1_MISMATCH"

    def test_hash_partial_only_hashes_first_65535_bytes(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """Quando hash_partial=True, cliente hasheia so os primeiros 65535
        bytes pra casar com MemoRead truncado do server."""
        import hashlib
        # 100KB de conteudo; server hasheia so primeiros 65535
        content = b"A" * (100 * 1024)
        expected_partial_sha1 = hashlib.sha1(content[:65535]).hexdigest()
        bf = BundleFile(
            name="big.csv", path="\\temp\\big.csv",
            size_bytes=len(content), chunks=1, sha256="",
            hash=expected_partial_sha1, hash_algo="sha1", hash_partial=True,
        )
        self._setup_download(monkeypatch, content)
        client = ColetaDBClient(endpoint="http://x/rest", user="u", password="p")
        # Nao deve raise — hash dos primeiros 65535 bate
        client.download_file(bf, tmp_path / "big.csv")

    def test_no_hash_skips_validation(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """Server sem funcao de hash disponivel -> hash="", hash_algo="".
        Cliente deve pular validacao silenciosamente."""
        content = b"any bytes"
        bf = BundleFile(
            name="x.csv", path="\\temp\\x.csv",
            size_bytes=len(content), chunks=1, sha256="",
            hash="", hash_algo="", hash_partial=False,
        )
        self._setup_download(monkeypatch, content)
        client = ColetaDBClient(endpoint="http://x/rest", user="u", password="p")
        # Sem hash, nao raise mesmo com bytes "errados"
        client.download_file(bf, tmp_path / "x.csv")

    def test_legacy_sha256_field_still_works(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        """Servidor v1.0.x emite so 'sha256' (sem hash_algo). Cliente
        deve continuar validando pelo campo legado."""
        import hashlib
        content = b"legacy server response"
        sha256 = hashlib.sha256(content).hexdigest()
        bf = BundleFile(
            name="x.csv", path="\\temp\\x.csv",
            size_bytes=len(content), chunks=1, sha256=sha256,
            # hash/hash_algo nao setados — server antigo
        )
        self._setup_download(monkeypatch, content)
        client = ColetaDBClient(endpoint="http://x/rest", user="u", password="p")
        client.download_file(bf, tmp_path / "x.csv")


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
            return _fake_json_response(200, {
                "bundle_id": "ok", "bundle_dir": "x", "modo": "enxuto",
                "threshold": 10, "chunk_size": 4194304, "files": [],
            })

        monkeypatch.setattr("plugadvpl.coletadb_client.urlopen", flaky_urlopen)
        monkeypatch.setattr("plugadvpl.coletadb_client.time.sleep", lambda *_: None)

        client = ColetaDBClient(
            endpoint="http://x/rest", user="u", password="p",
            retry_count=3, retry_backoff_s=0,
        )
        m = client.run()
        assert call_count[0] == 3
        assert m.bundle_id == "ok"

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
            endpoint="http://x/rest", user="u", password="p",
            retry_count=2, retry_backoff_s=0,
        )
        with pytest.raises(ColetaDBError):
            client.run()
        assert call_count[0] == 2


class TestEndpointPath:
    def test_endpoint_strips_trailing_slash(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: dict[str, Any] = {}

        def capturing(req, **kwargs):  # noqa: ARG001
            captured["url"] = req.full_url
            return _fake_json_response(200, {
                "bundle_id": "x", "bundle_dir": "y", "modo": "enxuto",
                "threshold": 10, "chunk_size": 4194304, "files": [],
            })

        monkeypatch.setattr("plugadvpl.coletadb_client.urlopen", capturing)
        client = ColetaDBClient(
            endpoint="http://x/rest/", user="u", password="p",
        )
        client.run()
        # Sem // duplicado
        assert captured["url"] == "http://x/rest/coletadb/run"
