"""Pre-flight check do ``plugadvpl compile`` (v0.8.4 Fase 1).

Diagnostica o estado do ambiente e retorna JSON estruturado com ``next_actions``
que o agente IA (ou usuário) deve seguir para chegar ao estado "ready".

Princípios:
- Função pura ``run_doctor(root, runtime_cfg) -> DoctorResult`` — sem efeitos
  colaterais além de TCP ping + leitura de filesystem read-only.
- Cada check tem ``ok: bool`` + ``reason`` + ``hint`` (opcional).
- ``next_actions`` é lista ordenada por dependência: cada ação tem ``action``,
  ``question`` e ``candidates`` (quando aplicável).
"""
from __future__ import annotations

import os
import shutil
import socket
from dataclasses import dataclass, field
from pathlib import Path

from plugadvpl.runtime_config import RuntimeConfig

# Paths comuns onde advpls.exe pode estar (Windows).
_ADVPLS_WIN_CANDIDATES: list[str] = [
    r"D:\TOTVS\protheus\bin\Appserver\advpls.exe",
    r"C:\TOTVS\protheus\bin\Appserver\advpls.exe",
    r"D:\IA\Tools\tds-vscode\extracted\extension\node_modules\@totvs\tds-ls\bin\windows\advpls.exe",
]

# Locais de extensão tds-vscode com glob (cobre versões variadas).
_VSCODE_EXT_GLOBS: list[str] = [
    "%USERPROFILE%/.vscode/extensions/totvs.tds-vscode-*/node_modules/@totvs/tds-ls/bin/{os}/advpls{ext}",
    "%HOME%/.vscode/extensions/totvs.tds-vscode-*/node_modules/@totvs/tds-ls/bin/{os}/advpls{ext}",
]

# Paths comuns de Include Protheus.
_INCLUDES_CANDIDATES: list[str] = [
    r"D:\TOTVS\protheus\Include",
    r"C:\TOTVS\protheus\Include",
    r"D:\PrjProtheus\protheus\Include",
    r"C:\Program Files\TOTVS\Microsiga\Protheus\Include",
    r"/opt/totvs/protheus/Include",
    r"/usr/local/protheus/Include",
]

# Arquivos sentinela que confirmam que a pasta é de Includes Protheus reais.
_INCLUDES_SENTINEL_FILES: list[str] = ["PRTOPDEF.CH", "protheus.ch", "totvs.ch"]


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str
    hint: str = ""


@dataclass(frozen=True)
class NextAction:
    action: str  # set_advpls_binary | set_includes | set_env_var | create_runtime_toml | start_appserver
    question: str
    candidates: list[str] = field(default_factory=list)
    var_name: str = ""  # para set_env_var
    secret: bool = False  # se True, agente NÃO deve logar valor


@dataclass(frozen=True)
class DoctorResult:
    status: str  # "ready" | "needs_setup"
    mode_supported: list[str]  # subset de ["appre", "cli"]
    checks: list[Check]
    next_actions: list[NextAction]

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "mode_supported": self.mode_supported,
            "checks": [
                {"name": c.name, "ok": c.ok, "detail": c.detail, "hint": c.hint}
                for c in self.checks
            ],
            "next_actions": [
                {
                    "action": a.action,
                    "question": a.question,
                    "candidates": a.candidates,
                    "var_name": a.var_name,
                    "secret": a.secret,
                }
                for a in self.next_actions
            ],
        }


def _detect_advpls() -> Path | None:
    """Procura advpls em paths comuns. Retorna Path do primeiro encontrado.

    Ordem de prioridade:
    1. Env var ``PLUGADVPL_ADVPLS_BINARY``
    2. Pasta interna ``~/.plugadvpl/advpls/bin/<os>/`` (instalada via
       ``plugadvpl compile --install-advpls``)
    3. PATH do sistema
    4. Paths Windows canônicos (D:\\TOTVS\\..., D:\\IA\\Tools\\...)
    5. Extensão tds-vscode em ~/.vscode/extensions/totvs.tds-vscode-*/
    """
    # 1. Env var tem prioridade absoluta (escape hatch + test hook)
    env_path = os.environ.get("PLUGADVPL_ADVPLS_BINARY")
    if env_path and Path(env_path).is_file():
        return Path(env_path)

    # 2. Pasta interna do plugadvpl (instalação gerenciada)
    from plugadvpl.compile_installer import installed_binary_path
    internal = installed_binary_path()
    if internal.is_file():
        return internal

    # 3. PATH
    found = shutil.which("advpls") or shutil.which("advpls.exe")
    if found:
        return Path(found)

    # Paths Windows canônicos
    if os.name == "nt":
        for cand in _ADVPLS_WIN_CANDIDATES:
            p = Path(cand)
            if p.is_file():
                return p

    # Extensão tds-vscode (glob — versão muda)
    home = Path.home()
    os_subdir = {"nt": "windows", "posix": "linux"}.get(os.name, "linux")
    ext_suffix = ".exe" if os.name == "nt" else ""
    ext_globs = [
        home / ".vscode" / "extensions",
    ]
    for ext_dir in ext_globs:
        if not ext_dir.is_dir():
            continue
        for entry in ext_dir.glob("totvs.tds-vscode-*"):
            cand = entry / "node_modules" / "@totvs" / "tds-ls" / "bin" / os_subdir / f"advpls{ext_suffix}"
            if cand.is_file():
                return cand

    return None


def _detect_includes() -> list[Path]:
    """Procura pastas com includes Protheus reais. Retorna candidatas validadas."""
    found: list[Path] = []
    for cand in _INCLUDES_CANDIDATES:
        p = Path(cand)
        if not p.is_dir():
            continue
        # Valida que tem pelo menos 1 sentinel (case-insensitive em Windows)
        has_sentinel = any(
            any(p.glob(s)) or any(p.glob(s.lower())) or any(p.glob(s.upper()))
            for s in _INCLUDES_SENTINEL_FILES
        )
        if has_sentinel:
            found.append(p)
    return found


def _tcp_ping(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def run_doctor(
    root: Path, runtime_cfg: RuntimeConfig | None
) -> DoctorResult:
    """Diagnostica setup do compile. Função pura (lê fs + TCP ping)."""
    checks: list[Check] = []
    next_actions: list[NextAction] = []
    appre_ok = True
    cli_ok = True

    # --- 1. advpls binary ---
    binary: Path | None = None
    if runtime_cfg is not None:
        binary = runtime_cfg.tds_ls.binary
        checks.append(Check(
            name="advpls_binary",
            ok=binary.is_file(),
            detail=f"runtime.toml [tds_ls].binary = {binary}",
        ))
    else:
        binary = _detect_advpls()
        if binary:
            checks.append(Check(
                name="advpls_binary",
                ok=True,
                detail=f"auto-detected: {binary}",
                hint="Sete PLUGADVPL_ADVPLS_BINARY ou [tds_ls].binary no runtime.toml pra fixar.",
            ))
        else:
            checks.append(Check(
                name="advpls_binary",
                ok=False,
                detail="advpls não encontrado em PATH, env var, ou locais comuns",
                hint="Baixe extensão tds-vscode do Marketplace (ver docs/setup-compile.md §Binário advpls).",
            ))
            appre_ok = False
            cli_ok = False
            next_actions.append(NextAction(
                action="set_advpls_binary",
                question=(
                    "PRECISO: binário advpls (compilador oficial TOTVS, ~38MB).\n"
                    "  RECOMENDADO: rode `plugadvpl compile --install-advpls` — modo\n"
                    "  interativo que pergunta se você quer:\n"
                    "    (a) Copiar de um path local (se já tem advpls instalado)\n"
                    "    (b) Baixar do Marketplace VSCode público (~118MB, sem precisar VSCode)\n"
                    "  O comando explica tudo + pede confirmação antes de qualquer ação.\n"
                    "  Após instalar, advpls fica em ~/.plugadvpl/advpls/bin/<os>/ e o\n"
                    "  --doctor detecta automaticamente nas próximas chamadas.\n"
                    "  Alternativa manual: setar PLUGADVPL_ADVPLS_BINARY=<path>\n"
                    "  Mais info: docs/compile-checklist.md §1"
                ),
                candidates=[],
            ))

    # --- 2. Includes Protheus ---
    configured_includes: list[Path] = []
    if runtime_cfg is not None:
        configured_includes = list(runtime_cfg.compile.includes)

    has_includes_configured = bool(configured_includes) and all(
        p.is_dir() for p in configured_includes
    )

    if has_includes_configured:
        checks.append(Check(
            name="includes_protheus",
            ok=True,
            detail=f"configurado em runtime.toml: {configured_includes[0]}",
        ))
    else:
        detected = _detect_includes()
        if detected:
            checks.append(Check(
                name="includes_protheus",
                ok=False,
                detail=f"não configurado, mas detectei {len(detected)} pasta(s) candidata(s)",
                hint=f"Use --includes <pasta> ou configure [compile].includes no runtime.toml.",
            ))
            next_actions.append(NextAction(
                action="set_includes",
                question=(
                    f"PRECISO: pasta com includes Protheus (PRTOPDEF.CH, protheus.ch, ~1100 .ch).\n"
                    f"  Detectei {len(detected)} pasta(s) candidata(s) — confirme qual usar OU informe outra:\n"
                    "  Mais info: docs/compile-checklist.md §2"
                ),
                candidates=[str(p) for p in detected],
            ))
        else:
            checks.append(Check(
                name="includes_protheus",
                ok=False,
                detail="nenhuma pasta de includes Protheus detectada",
                hint=(
                    "Includes não vêm com tds-vscode — precisam vir de instalação Protheus. "
                    "Ver docs/compile-checklist.md §2."
                ),
            ))
            next_actions.append(NextAction(
                action="set_includes",
                question=(
                    "PRECISO: pasta com includes Protheus (contém PRTOPDEF.CH, protheus.ch + ~1100 .ch).\n"
                    "  Tipicamente em <protheus-root>/Include/ — vem com instalação do AppServer.\n"
                    "  Sem AppServer/SDK local? Use --mode cli (compila no AppServer remoto, que já tem).\n"
                    "  Mais info: docs/compile-checklist.md §2"
                ),
                candidates=[],
            ))
        appre_ok = False  # appre sem includes geralmente falha

    # --- 3. runtime.toml (necessário pra cli) ---
    runtime_toml_path = root / ".plugadvpl" / "runtime.toml"
    if runtime_cfg is not None:
        checks.append(Check(
            name="runtime_toml",
            ok=True,
            detail=f"carregado de {runtime_cfg.source_path}",
        ))
    else:
        checks.append(Check(
            name="runtime_toml",
            ok=False,
            detail=f"{runtime_toml_path} não existe (modo cli requer)",
            hint="Rode `plugadvpl compile --init-config` para gerar template.",
        ))
        cli_ok = False
        next_actions.append(NextAction(
            action="create_runtime_toml",
            question=(
                f"PRECISO: arquivo runtime.toml em {runtime_toml_path}.\n"
                "  Rode: plugadvpl compile --init-config\n"
                "  Depois edite o TOML preenchendo 5 dados:\n"
                "    1. [tds_ls].binary    — path do advpls\n"
                "    2. [appserver].host/port/build/environment — info do AppServer\n"
                "    3. [auth].user_env/password_env — NOMES das env vars (não valores!)\n"
                "    4. [compile].includes — lista de pastas .ch\n"
                "  Como descobrir cada dado: docs/compile-checklist.md §3-§5"
            ),
            candidates=[],
        ))

    # --- 4. env vars (cli) ---
    if runtime_cfg is not None:
        for var_attr in ("user_env", "password_env"):
            var_name = getattr(runtime_cfg.auth, var_attr)
            is_set = bool(os.environ.get(var_name))
            checks.append(Check(
                name=f"env_var_{var_attr}",
                ok=is_set,
                detail=f"${var_name} {'OK' if is_set else 'NÃO setada'}",
                hint=(
                    f"export {var_name}=<valor> (NUNCA commitar)"
                    if not is_set else ""
                ),
            ))
            if not is_set:
                cli_ok = False
                next_actions.append(NextAction(
                    action="set_env_var",
                    question=(
                        f"Setar variável de ambiente ${var_name}. "
                        f"{'Senha (secret — não logarei)' if 'password' in var_attr else 'Usuário Protheus'}."
                    ),
                    var_name=var_name,
                    secret=("password" in var_attr),
                ))

    # --- 5. AppServer reachable (cli) ---
    if runtime_cfg is not None:
        reachable = runtime_cfg.appserver_reachable  # já checado no load
        checks.append(Check(
            name="appserver_reachable",
            ok=reachable,
            detail=(
                f"{runtime_cfg.appserver.host}:{runtime_cfg.appserver.port} "
                f"{'responde' if reachable else 'NÃO responde'}"
            ),
            hint=(
                "Inicie AppServer ou suba SSH tunnel (`ssh -L 1234:localhost:1234 user@host -N`)."
                if not reachable else ""
            ),
        ))
        if not reachable:
            cli_ok = False
            next_actions.append(NextAction(
                action="start_appserver",
                question=(
                    f"AppServer em {runtime_cfg.appserver.host}:{runtime_cfg.appserver.port} "
                    "não responde. Iniciar localmente OU subir SSH tunnel pra remoto. "
                    "Sem isso, --mode cli não funciona (use --mode appre por enquanto)."
                ),
                candidates=[],
            ))

    # --- Status global ---
    modes: list[str] = []
    if appre_ok:
        modes.append("appre")
    if cli_ok:
        modes.append("cli")
    status = "ready" if modes else "needs_setup"

    return DoctorResult(
        status=status,
        mode_supported=modes,
        checks=checks,
        next_actions=next_actions,
    )
