"""Registry global de AppServers Protheus (~/.plugadvpl/servers.json).

Cadastrado **uma vez** por usuário, usado em qualquer projeto plugadvpl
da mesma máquina via ``plugadvpl compile --use-server <nome>``.

Inspirado em ``~/.totvsls/servers.json`` do TDS-VSCode — incluindo
auto-import dessa fonte se existir.

Convenções de segurança:
- NUNCA grava senha (apenas ``user_env`` / ``password_env`` — nomes).
- Arquivo com permissão 0o600 em POSIX (info de host/port/build/env pode
  ser sensível em ambientes corporativos).
- ``~/.plugadvpl/`` é per-user, fora de qualquer projeto/repo.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Server:
    """Cadastro de um AppServer Protheus."""

    name: str
    host: str
    port: int
    build: str
    environments: list[str]
    default_environment: str
    user_env: str = "PROTHEUS_USER"
    password_env: str = "PROTHEUS_PASS"
    secure: bool = False
    notes: str = ""
    restart_cmd: str = ""  # v0.14: shell command pra restart do AppServer (Troca Quente)
    is_prod: bool = False  # v0.15: tq exige --confirm-prod quando True
    includes: list[str] = field(default_factory=list)  # v0.8.11: vem do TDS-VSCode


@dataclass(frozen=True)
class ServersRegistry:
    """Conteúdo de ``~/.plugadvpl/servers.json``."""

    default: str = ""
    servers: list[Server] = field(default_factory=list)


def registry_path() -> Path:
    """``~/.plugadvpl/servers.json`` — path do registry."""
    return Path.home() / ".plugadvpl" / "servers.json"


def tds_vscode_servers_path() -> Path:
    """``~/.totvsls/servers.json`` — registry da extensão TDS-VSCode (auto-import)."""
    return Path.home() / ".totvsls" / "servers.json"


def load_registry() -> ServersRegistry:
    """Carrega registry. Retorna vazio se arquivo não existe."""
    path = registry_path()
    if not path.is_file():
        return ServersRegistry()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ServersRegistry()
    servers = [Server(**s) for s in raw.get("servers", [])]
    return ServersRegistry(
        default=str(raw.get("default", "")),
        servers=servers,
    )


def save_registry(registry: ServersRegistry) -> Path:
    """Grava registry em ~/.plugadvpl/servers.json (cria pasta se necessário, 0o600)."""
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "default": registry.default,
        "servers": [asdict(s) for s in registry.servers],
    }
    # Escreve em CP1252-safe (JSON é UTF-8 sempre)
    payload = json.dumps(data, indent=2, ensure_ascii=False)
    # Cria com 0o600 em POSIX
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, payload.encode("utf-8"))
    finally:
        os.close(fd)
    return path


def get_server(name: str) -> Server | None:
    """Busca server por nome no registry. Retorna None se não existe."""
    registry = load_registry()
    for s in registry.servers:
        if s.name == name:
            return s
    return None


def default_server() -> Server | None:
    """Retorna server marcado como ``default`` no registry, ou o primeiro,
    ou None se vazio."""
    registry = load_registry()
    if not registry.servers:
        return None
    if registry.default:
        for s in registry.servers:
            if s.name == registry.default:
                return s
    return registry.servers[0]


def add_server(server: Server, make_default: bool = False) -> ServersRegistry:
    """Adiciona server ao registry. Substitui se já existe com mesmo nome.

    Returns:
        Registry atualizado (já gravado em disco).
    """
    registry = load_registry()
    others = [s for s in registry.servers if s.name != server.name]
    new_servers = [*others, server]
    new_default = registry.default
    if make_default or not new_default:
        new_default = server.name
    updated = ServersRegistry(default=new_default, servers=new_servers)
    save_registry(updated)
    return updated


def remove_server(name: str) -> bool:
    """Remove server do registry. Retorna True se removeu, False se não existia."""
    registry = load_registry()
    others = [s for s in registry.servers if s.name != name]
    if len(others) == len(registry.servers):
        return False
    new_default = (
        registry.default if registry.default != name else (others[0].name if others else "")
    )
    save_registry(ServersRegistry(default=new_default, servers=others))
    return True


def list_servers() -> list[Server]:
    """Retorna lista de todos os servers cadastrados."""
    return load_registry().servers


def import_from_tds_vscode() -> list[Server]:
    """Lê ``~/.totvsls/servers.json`` (TDS-VSCode) e devolve lista de Server.

    NÃO grava no registry — caller decide quais importar. Retorna lista vazia
    se arquivo não existe ou está malformado.

    Formato esperado do TDS-VSCode (~/.totvsls/servers.json):
        {
          "version": "0.2.0",
          "configurations": [
            {
              "id": "<uuid>",
              "type": "totvs_server_protheus",
              "name": "myserver",
              "address": "127.0.0.1",
              "port": 1234,
              "build": "7.00.240223P",
              "secure": 0,
              "environments": [{"name": "P2510", "id": "..."}],
              ...
            }
          ],
          "lastConnectedServer": "<id>",
          "savedTokens": [...]
        }
    """
    path = tds_vscode_servers_path()
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    out: list[Server] = []
    for cfg in raw.get("configurations", []):
        if not isinstance(cfg, dict):
            continue
        name = str(cfg.get("name") or "").strip()
        if not name:
            continue
        envs_raw = cfg.get("environments") or []
        envs: list[str] = []
        for e in envs_raw:
            if isinstance(e, dict) and e.get("name"):
                envs.append(str(e["name"]))
            elif isinstance(e, str):
                envs.append(e)
        default_env = envs[0] if envs else ""
        try:
            port = int(cfg.get("port", 1234))
        except (ValueError, TypeError):
            port = 1234
        secure_raw = cfg.get("secure", 0)
        secure = bool(secure_raw) if isinstance(secure_raw, bool) else (secure_raw == 1)
        # v0.8.11 fix bug 1: TDS-VSCode usa "buildVersion" (não "build").
        # Aceita ambos pra compat com formatos antigos.
        build_str = str(cfg.get("buildVersion") or cfg.get("build") or "")
        # v0.8.11: também importa includes do TDS — antes eram perdidos
        includes_raw = cfg.get("includes") or []
        includes_list: list[str] = []
        if isinstance(includes_raw, list):
            includes_list = [str(p) for p in includes_raw if p]
        out.append(
            Server(
                name=name,
                host=str(cfg.get("address") or "127.0.0.1"),
                port=port,
                build=build_str,
                environments=envs,
                default_environment=default_env,
                secure=secure,
                notes="imported from TDS-VSCode",
                includes=includes_list,
            )
        )
    return out
