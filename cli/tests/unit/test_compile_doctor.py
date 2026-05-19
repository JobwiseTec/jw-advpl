"""Testes do plugadvpl.compile_doctor (v0.8.4)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from plugadvpl.compile_doctor import (
    DoctorResult,
    NextAction,
    _detect_advpls,
    _detect_includes,
    run_doctor,
)


class TestDetectAdvpls:
    def test_env_var_takes_precedence(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake = tmp_path / "advpls.exe"
        fake.write_text("", encoding="utf-8")
        monkeypatch.setenv("PLUGADVPL_ADVPLS_BINARY", str(fake))
        assert _detect_advpls() == fake

    def test_returns_none_when_nowhere(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PLUGADVPL_ADVPLS_BINARY", raising=False)
        monkeypatch.setenv("PATH", str(tmp_path))  # PATH vazio
        with patch("plugadvpl.compile_doctor.shutil.which", return_value=None):
            with patch.object(Path, "home", return_value=tmp_path):
                # patch _ADVPLS_WIN_CANDIDATES como vazio
                with patch("plugadvpl.compile_doctor._ADVPLS_WIN_CANDIDATES", []):
                    result = _detect_advpls()
        assert result is None


class TestDetectIncludes:
    def test_returns_empty_when_no_candidates_exist(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Force lista vazia de candidatos pra isolar do FS real do dev
        monkeypatch.setattr("plugadvpl.compile_doctor._INCLUDES_CANDIDATES", [])
        assert _detect_includes() == []

    def test_validates_sentinel_files(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Cria pasta candidata mas SEM PRTOPDEF.CH (não deve ser detectada)
        bad = tmp_path / "fake_includes"
        bad.mkdir()
        (bad / "random.txt").write_text("", encoding="utf-8")
        monkeypatch.setattr(
            "plugadvpl.compile_doctor._INCLUDES_CANDIDATES", [str(bad)]
        )
        assert _detect_includes() == []

        # Adiciona sentinel — agora deve detectar
        (bad / "PRTOPDEF.CH").write_text("", encoding="utf-8")
        assert _detect_includes() == [bad]


class TestRunDoctor:
    def test_no_runtime_cfg_no_advpls_no_includes_needs_setup(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PLUGADVPL_ADVPLS_BINARY", raising=False)
        monkeypatch.setattr("plugadvpl.compile_doctor._ADVPLS_WIN_CANDIDATES", [])
        monkeypatch.setattr("plugadvpl.compile_doctor._INCLUDES_CANDIDATES", [])
        with patch("plugadvpl.compile_doctor.shutil.which", return_value=None):
            with patch.object(Path, "home", return_value=tmp_path):
                result = run_doctor(tmp_path, runtime_cfg=None)
        assert result.status == "needs_setup"
        assert result.mode_supported == []
        # Deve ter next_action de set_advpls_binary
        actions = [a.action for a in result.next_actions]
        assert "set_advpls_binary" in actions

    def test_with_advpls_and_includes_appre_ok(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Mock advpls detectado
        fake_advpls = tmp_path / "advpls.exe"
        fake_advpls.write_text("", encoding="utf-8")
        monkeypatch.setenv("PLUGADVPL_ADVPLS_BINARY", str(fake_advpls))
        # Mock includes detectados
        inc = tmp_path / "Include"
        inc.mkdir()
        (inc / "PRTOPDEF.CH").write_text("", encoding="utf-8")
        monkeypatch.setattr(
            "plugadvpl.compile_doctor._INCLUDES_CANDIDATES", [str(inc)]
        )
        result = run_doctor(tmp_path, runtime_cfg=None)
        # advpls OK + includes detectadas mas não-configuradas — appre ainda needs_setup
        # (set_includes pendente — usuário precisa confirmar)
        assert "set_includes" in [a.action for a in result.next_actions]

    def test_runtime_cfg_full_ready(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "totvs")
        inc = tmp_path / "Include"
        inc.mkdir()
        (inc / "PRTOPDEF.CH").write_text("", encoding="utf-8")
        fake_advpls = tmp_path / "advpls.exe"
        fake_advpls.write_text("", encoding="utf-8")
        runtime_cfg = MagicMock(
            tds_ls=MagicMock(binary=fake_advpls),
            appserver=MagicMock(host="127.0.0.1", port=1234),
            auth=MagicMock(user_env="PROTHEUS_USER", password_env="PROTHEUS_PASS"),
            compile=MagicMock(includes=[inc]),
            appserver_reachable=True,
            source_path=tmp_path / ".plugadvpl" / "runtime.toml",
        )
        result = run_doctor(tmp_path, runtime_cfg=runtime_cfg)
        assert result.status == "ready"
        assert "appre" in result.mode_supported
        assert "cli" in result.mode_supported
        assert result.next_actions == []


class TestDoctorResultToDict:
    def test_schema_completo(self) -> None:
        result = DoctorResult(
            status="needs_setup",
            mode_supported=["appre"],
            checks=[],
            next_actions=[
                NextAction(
                    action="set_env_var",
                    question="Set PROTHEUS_PASS",
                    var_name="PROTHEUS_PASS",
                    secret=True,
                ),
            ],
        )
        d = result.to_dict()
        assert d["status"] == "needs_setup"
        assert d["mode_supported"] == ["appre"]
        assert d["next_actions"][0]["secret"] is True
        assert d["next_actions"][0]["var_name"] == "PROTHEUS_PASS"
