"""Resolução de credenciais Protheus em camadas (v0.9.0).

Ordem de precedência (primeira encontrada vence):

1. **Env vars** (server.user_env / server.password_env) — máximo controle,
   CI-friendly, gerenciadores de senha externos (1Password CLI, vault, etc).
2. **Keyring do sistema** (Win Credential Manager / macOS Keychain /
   Linux Secret Service) — UX igual ao TDS-VSCode, mas senha cifrada pelo
   OS (não base64 em JSON).
3. **None** — caller decide se prompta interativo ou aborta com erro claro.

Princípios de segurança:

- Plugin NUNCA grava senha em arquivo. Só o cofre nativo do OS toca o byte
  da senha — descriptografado on-demand pelo usuário logado.
- Service name no keyring: ``"plugadvpl"``. Username: ``"{server_name}:user"``
  e ``"{server_name}:password"`` (formato estável pra introspect/migration).
- Keyring backend instável (ex: Linux server sem D-Bus) NÃO derruba o plugin —
  ``CredentialResolution.keyring_available = False`` deixa o fluxo escolher
  fallback.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

KeyringKind = Literal["user", "password"]

# Service name fixo no cofre — único namespace pro plugadvpl.
KEYRING_SERVICE = "plugadvpl"

CredentialSource = Literal["env", "keyring", "none"]


@dataclass(frozen=True)
class CredentialResolution:
    """Resultado da resolução. Imutável, sem expor a senha por to_dict."""

    user: str
    password: str
    user_source: CredentialSource
    password_source: CredentialSource
    keyring_available: bool

    @property
    def is_complete(self) -> bool:
        return bool(self.user) and bool(self.password)

    def to_safe_dict(self) -> dict[str, object]:
        """Dump seguro pra log/--explain-config: SEM senha, só fonte.

        Importante: extrai ``bool(self.password)`` numa variável intermediária
        antes de montar o dict pra deixar a sanitização explícita pra ferramentas
        de análise de fluxo (CodeQL). Sem o intermediário, o data-flow tracker
        marca o dict como tainted mesmo com o ternário substituindo o valor.
        """
        has_password = bool(self.password)
        return {
            "user": self.user if self.user else "",
            "password": "<set>" if has_password else "<unset>",
            "user_source": self.user_source,
            "password_source": self.password_source,
            "keyring_available": self.keyring_available,
        }


def _try_import_keyring() -> Any:
    """Importa keyring com fallback gracioso. Retorna None se backend não disponível.

    Lazy import: o pacote ``keyring`` tem backends que tocam D-Bus / Credential
    Manager no import — se isso falhar (Linux server sem D-Bus, container
    minimalista), o módulo todo trava se for top-level. Por isso PLC0415 fica.

    Tipo de retorno é ``Any`` em vez de ``ModuleType | None`` porque keyring é
    consumido via duck-typing (``.get_password()``, ``.set_password()``) e
    tipar como ``ModuleType`` exige forward-refs que confundem mypy.
    """
    try:
        import keyring  # noqa: PLC0415
        from keyring.errors import KeyringError  # noqa: F401, PLC0415
    except ImportError:
        return None
    # Tentar pegar o backend — se for o NullBackend (Linux server sem D-Bus),
    # operações reais falham silenciosamente. Detectamos cedo.
    try:
        backend = keyring.get_keyring()
        # NullBackend ou FailKeyring: nome contém "null" ou "fail"
        backend_name = type(backend).__name__.lower()
        if "null" in backend_name or "fail" in backend_name:
            return None
    except Exception:  # pragma: no cover — defensive
        return None
    return keyring


def keyring_available() -> bool:
    """True se algum backend de cofre nativo está disponível."""
    return _try_import_keyring() is not None


def _username_key(server_name: str, kind: KeyringKind) -> str:
    return f"{server_name}:{kind}"


def get_credentials_from_keyring(server_name: str) -> tuple[str, str]:
    """Lê (user, password) do cofre. Retorna ('', '') se não setado / backend down."""
    kr = _try_import_keyring()
    if kr is None:
        return "", ""
    try:
        user = kr.get_password(KEYRING_SERVICE, _username_key(server_name, "user")) or ""
        pwd = kr.get_password(KEYRING_SERVICE, _username_key(server_name, "password")) or ""
        return user, pwd
    except Exception:  # pragma: no cover — backend instável
        return "", ""


def set_credentials_in_keyring(server_name: str, user: str, password: str) -> None:
    """Grava user+pass no cofre. Lança RuntimeError se backend indisponível."""
    kr = _try_import_keyring()
    if kr is None:
        raise RuntimeError(
            "keyring backend não disponível neste sistema. "
            "Em Linux server sem D-Bus, use env vars: "
            "export PROTHEUS_USER=... PROTHEUS_PASS=..."
        )
    kr.set_password(KEYRING_SERVICE, _username_key(server_name, "user"), user)
    kr.set_password(KEYRING_SERVICE, _username_key(server_name, "password"), password)


def clear_credentials_from_keyring(server_name: str) -> tuple[bool, bool]:
    """Remove credenciais do cofre. Retorna (removed_user, removed_password)."""
    kr = _try_import_keyring()
    if kr is None:
        return False, False
    removed_user = False
    removed_pwd = False
    for kind in ("user", "password"):
        try:
            kr.delete_password(KEYRING_SERVICE, _username_key(server_name, kind))
        except Exception:
            # Backend pode falhar (D-Bus, perms) ou senha não existir — op é idempotente
            continue
        if kind == "user":
            removed_user = True
        else:
            removed_pwd = True
    return removed_user, removed_pwd


def resolve_credentials(
    server_name: str,
    user_env: str,
    password_env: str,
) -> CredentialResolution:
    """Resolve user+pass na ordem: env vars → keyring → vazio.

    Args:
        server_name: identificador do server no registry (chave no keyring).
        user_env: nome da env var de usuário (ex: "PROTHEUS_USER").
        password_env: nome da env var de senha.

    Returns:
        CredentialResolution. ``is_complete`` False se nenhuma fonte achou
        ambos. Caller decide: prompt interativo, falhar com mensagem, etc.
    """
    env_user = os.environ.get(user_env, "")
    env_pwd = os.environ.get(password_env, "")

    user = env_user
    pwd = env_pwd
    user_source: CredentialSource = "env" if env_user else "none"
    pwd_source: CredentialSource = "env" if env_pwd else "none"

    # Se faltar algum, tenta cofre
    kr_avail = keyring_available()
    if (not user or not pwd) and kr_avail:
        kr_user, kr_pwd = get_credentials_from_keyring(server_name)
        if not user and kr_user:
            user = kr_user
            user_source = "keyring"
        if not pwd and kr_pwd:
            pwd = kr_pwd
            pwd_source = "keyring"

    return CredentialResolution(
        user=user,
        password=pwd,
        user_source=user_source,
        password_source=pwd_source,
        keyring_available=kr_avail,
    )
