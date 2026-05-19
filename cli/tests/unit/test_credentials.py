"""Testes de plugadvpl.credentials (v0.9.0 — keyring + env fallback)."""
from __future__ import annotations

import pytest

from plugadvpl.credentials import (
    CredentialResolution,
    _username_key,
    clear_credentials_from_keyring,
    get_credentials_from_keyring,
    keyring_available,
    resolve_credentials,
    set_credentials_in_keyring,
)


class FakeKeyring:
    """Fake keyring backend pra testes (in-memory)."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        key = (service, username)
        if key not in self.store:
            raise RuntimeError("not found")
        del self.store[key]

    def get_keyring(self) -> object:
        """Tipo do backend — usado por _try_import_keyring pra detectar NullBackend."""
        return self


@pytest.fixture
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> FakeKeyring:
    """Substitui o módulo `keyring` por nosso fake em-memória."""
    fake = FakeKeyring()
    # _try_import_keyring faz `import keyring` interno — mockamos isso
    import sys
    monkeypatch.setitem(sys.modules, "keyring", fake)
    monkeypatch.setitem(sys.modules, "keyring.errors", type("M", (), {"KeyringError": Exception}))
    return fake


@pytest.fixture
def no_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    """Simula ambiente sem backend (Linux server sem D-Bus)."""
    monkeypatch.setattr(
        "plugadvpl.credentials._try_import_keyring", lambda: None
    )


class TestUsernameKey:
    def test_user_key(self) -> None:
        assert _username_key("dev-local", "user") == "dev-local:user"

    def test_password_key(self) -> None:
        assert _username_key("dev-local", "password") == "dev-local:password"


class TestKeyringAvailable:
    def test_true_with_fake(self, fake_keyring: FakeKeyring) -> None:
        assert keyring_available() is True

    def test_false_without_backend(self, no_keyring: None) -> None:
        assert keyring_available() is False


class TestSetGetClear:
    def test_set_then_get_roundtrip(self, fake_keyring: FakeKeyring) -> None:
        set_credentials_in_keyring("srv1", "admin", "totvs")
        user, pwd = get_credentials_from_keyring("srv1")
        assert user == "admin"
        assert pwd == "totvs"

    def test_get_missing_returns_empty(self, fake_keyring: FakeKeyring) -> None:
        user, pwd = get_credentials_from_keyring("nonexistent")
        assert user == ""
        assert pwd == ""

    def test_set_raises_when_no_backend(self, no_keyring: None) -> None:
        with pytest.raises(RuntimeError, match="backend"):
            set_credentials_in_keyring("srv1", "x", "y")

    def test_clear_removes_both(self, fake_keyring: FakeKeyring) -> None:
        set_credentials_in_keyring("srv1", "admin", "totvs")
        removed_u, removed_p = clear_credentials_from_keyring("srv1")
        assert removed_u is True
        assert removed_p is True
        # Idempotente: segunda chamada não falha
        u2, p2 = clear_credentials_from_keyring("srv1")
        assert u2 is False
        assert p2 is False

    def test_clear_returns_false_when_missing(self, fake_keyring: FakeKeyring) -> None:
        u, p = clear_credentials_from_keyring("nada")
        assert u is False
        assert p is False

    def test_clear_no_backend_returns_false(self, no_keyring: None) -> None:
        u, p = clear_credentials_from_keyring("srv1")
        assert (u, p) == (False, False)


class TestResolveCredentials:
    def test_env_only_no_keyring(
        self, monkeypatch: pytest.MonkeyPatch, no_keyring: None
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "totvs")
        res = resolve_credentials("srv1", "PROTHEUS_USER", "PROTHEUS_PASS")
        assert res.user == "admin"
        assert res.password == "totvs"
        assert res.user_source == "env"
        assert res.password_source == "env"
        assert res.is_complete is True
        assert res.keyring_available is False

    def test_keyring_only_when_env_missing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_keyring: FakeKeyring,
    ) -> None:
        monkeypatch.delenv("PROTHEUS_USER", raising=False)
        monkeypatch.delenv("PROTHEUS_PASS", raising=False)
        set_credentials_in_keyring("srv1", "kr_admin", "kr_secret")
        res = resolve_credentials("srv1", "PROTHEUS_USER", "PROTHEUS_PASS")
        assert res.user == "kr_admin"
        assert res.password == "kr_secret"
        assert res.user_source == "keyring"
        assert res.password_source == "keyring"
        assert res.is_complete is True

    def test_env_wins_over_keyring(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_keyring: FakeKeyring,
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "env_user")
        monkeypatch.setenv("PROTHEUS_PASS", "env_pwd")
        set_credentials_in_keyring("srv1", "kr_user", "kr_pwd")
        res = resolve_credentials("srv1", "PROTHEUS_USER", "PROTHEUS_PASS")
        # env vence
        assert res.user == "env_user"
        assert res.password == "env_pwd"
        assert res.user_source == "env"
        assert res.password_source == "env"

    def test_mixed_env_user_keyring_pass(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_keyring: FakeKeyring,
    ) -> None:
        """Edge case: user via env, pass via keyring."""
        monkeypatch.setenv("PROTHEUS_USER", "env_user")
        monkeypatch.delenv("PROTHEUS_PASS", raising=False)
        set_credentials_in_keyring("srv1", "kr_user", "kr_pwd")
        res = resolve_credentials("srv1", "PROTHEUS_USER", "PROTHEUS_PASS")
        assert res.user == "env_user"
        assert res.user_source == "env"
        assert res.password == "kr_pwd"
        assert res.password_source == "keyring"

    def test_nothing_set_incomplete(
        self,
        monkeypatch: pytest.MonkeyPatch,
        fake_keyring: FakeKeyring,
    ) -> None:
        monkeypatch.delenv("PROTHEUS_USER", raising=False)
        monkeypatch.delenv("PROTHEUS_PASS", raising=False)
        res = resolve_credentials("srv1", "PROTHEUS_USER", "PROTHEUS_PASS")
        assert res.is_complete is False
        assert res.user_source == "none"
        assert res.password_source == "none"


class TestToSafeDict:
    def test_password_redacted(self) -> None:
        res = CredentialResolution(
            user="admin", password="totvs123",
            user_source="env", password_source="env",
            keyring_available=True,
        )
        d = res.to_safe_dict()
        assert d["password"] == "<set>"
        assert "totvs123" not in str(d)
        assert d["user"] == "admin"

    def test_unset_marker(self) -> None:
        res = CredentialResolution(
            user="", password="",
            user_source="none", password_source="none",
            keyring_available=False,
        )
        d = res.to_safe_dict()
        assert d["password"] == "<unset>"
