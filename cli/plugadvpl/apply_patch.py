"""apply-patch — aplicação de `.PTM` via advpls (`action=patchApply`).

Spec: docs/superpowers/specs/2026-06-16-u6-apply-patch-design.md
Contrato: docs/apply-patch-contract.md
Research/smoke: gaps/U6_APPLY_PATCH_RESEARCH.md

Endurece a lógica artesanal dos scripts de referência (Fase 0):
- idempotência por **hash** (tabela patches_applied), não por mover arquivo;
- status real **parseado do log** — o advpls retorna exit 0 mesmo em partial-apply;
- ZIP **descompactado internamente** (híbrido), aplicação 1 `advpls cli` por `.PTM`;
- `secure` numérico (0/1) — `false`/`true` derruba o advpls com `[ERROR] stoi`.

Reúsa de compile.py: resolução do binário, escrita segura do .ini (CP1252/0600),
decode da saída (BOM UTF-16 + fallback CP1252).
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from plugadvpl.compile import (
    _decode_advpls_output,
    _write_secure_ini,
)

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator

    from plugadvpl.compile_servers import Server

PatchStatus = Literal["applied", "partial", "skipped", "failed"]

# Marcadores estáveis do log do advpls (confirmados no smoke 2026-06-16).
_MARK_APPLIED = "successfully applied."
_MARK_PARTIAL = "Only new sources are being applied"
_MARK_STOI = "[ERROR] stoi"
_RE_BUILD = re.compile(r"Appserver detected with build version:\s*(\S+)")
# `[ERROR] Unable to connect` é a tentativa secure→fallback plain — benigno.
_BENIGN_ERROR = "Unable to connect to the server"


@dataclass(frozen=True)
class PatchOutcome:
    """Resultado da aplicação de UM `.PTM`."""

    ptm_name: str
    ptm_hash: str
    status: PatchStatus
    log_path: str = ""
    backup_path: str = ""
    detail: str = ""


@dataclass(frozen=True)
class ApplyPatchResult:
    """Resultado consolidado de uma batch de `apply-patch`."""

    ok: bool
    server: str
    environment: str
    batch_ts: str
    patches: list[PatchOutcome] = field(default_factory=list)
    build: str = ""
    error: str = ""

    @property
    def summary(self) -> dict[str, int]:
        out = {"applied": 0, "partial": 0, "skipped": 0, "failed": 0}
        for p in self.patches:
            out[p.status] += 1
        return out


# --------------------------------------------------------------------------- #
# Helpers puros (sem side effect de rede/advpls) — fáceis de testar
# --------------------------------------------------------------------------- #
def sha256_file(path: Path) -> str:
    """SHA-256 do conteúdo de um arquivo (chave de idempotência)."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_ptms(input_path: Path, workdir: Path) -> list[Path]:
    """Resolve a lista de `.PTM` a aplicar, em ordem alfabética.

    - `.zip`  -> descompacta em ``workdir`` (híbrido D7) e lista `.PTM` internos.
    - diretório -> varre `*.ptm` não-recursivo.
    - `.ptm`  -> ele mesmo.

    Ordenação **alfabética** do nome (alinhado à impl de referência; case-insensitive).
    """
    if input_path.is_dir():
        ptms = [p for p in input_path.iterdir() if p.suffix.lower() == ".ptm"]
    elif input_path.suffix.lower() == ".zip":
        with zipfile.ZipFile(input_path) as zf:
            zf.extractall(workdir)
        ptms = [p for p in workdir.rglob("*") if p.suffix.lower() == ".ptm"]
    elif input_path.suffix.lower() == ".ptm":
        ptms = [input_path]
    else:
        raise ValueError(f"input não suportado: {input_path} (esperado .ptm, .zip ou diretório)")
    return sorted(ptms, key=lambda p: p.name.lower())


def build_patch_ini(
    server: Server,
    environment: str,
    user: str,
    password: str,
    ptm: Path,
    log_path: Path,
    *,
    apply_old: bool = False,
    with_defrag: bool = False,
) -> str:
    """Monta o `.ini` do advpls pra UM patchApply.

    `secure` é emitido **numérico** (0/1) — string `false`/`true` derruba o advpls
    com `[ERROR] stoi` (smoke 2026-06-16). Paths em forward-slash (aceito em Win/Linux).
    """

    def fwd(p: Path) -> str:
        return str(p).replace(chr(92), "/")

    lines = [
        f"logToFile={fwd(log_path)}",
        "showConsoleOutput=true",
        "",
        "[auth]",
        "action=authentication",
        f"server={server.host}",
        f"port={server.port}",
        f"secure={1 if server.secure else 0}",
        f"build={server.build}",
        f"environment={environment}",
        f"user={user}",
        f"psw={password}",
        "",
        "[patchApply]",
        "action=patchApply",
        f"patchFile={fwd(ptm)}",
        "localPatch=True",
        f"applyOldProgram={'True' if apply_old else 'False'}",
    ]
    if with_defrag:
        lines += ["", "[defragRPO]", "action=defragRPO"]
    return "\n".join(lines) + "\n"


def extract_build(log_text: str) -> str:
    """Extrai o build do AppServer do log (`Appserver detected with build version: X`)."""
    m = _RE_BUILD.search(log_text)
    return m.group(1) if m else ""


def parse_patch_log(log_text: str) -> tuple[PatchStatus, str]:
    """Deriva status do log do advpls — NÃO confiar no exit code (smoke: 0 em partial).

    - `applied`: tem `successfully applied.` sem o warning de outdated.
    - `partial`: aplicou, mas só recursos novos (`applyOldProgram` OFF).
    - `failed`:  sem `successfully applied.` (ou `[ERROR] stoi`, ou outro `[ERROR]` fatal).

    O `[ERROR] Unable to connect` (tentativa secure→plain) é ignorado como benigno.
    """
    applied = _MARK_APPLIED in log_text
    partial = _MARK_PARTIAL in log_text
    if applied and partial:
        return "partial", "Only new sources applied (applyOldProgram OFF)"
    if applied:
        return "applied", ""
    if _MARK_STOI in log_text:
        return "failed", "advpls [ERROR] stoi — 'secure' deve ser numérico (0/1)"
    return "failed", _first_fatal_error(log_text)


def _first_fatal_error(log_text: str) -> str:
    """Primeira linha `[ERROR]` que NÃO seja a de conexão benigna."""
    for line in log_text.splitlines():
        if "[ERROR]" in line and _BENIGN_ERROR not in line:
            return line.strip()
    return "patch não aplicado (sem marcador de sucesso no log)"


# --------------------------------------------------------------------------- #
# DB — idempotência
# --------------------------------------------------------------------------- #
def is_applied(conn: sqlite3.Connection, env: str, ptm_hash: str) -> bool:
    """True se o `.PTM` (por hash) já foi aplicado nesse environment."""
    row = conn.execute(
        "SELECT 1 FROM patches_applied WHERE env = ? AND ptm_hash = ? LIMIT 1",
        (env, ptm_hash),
    ).fetchone()
    return row is not None


def _record(
    conn: sqlite3.Connection,
    *,
    env: str,
    build: str,
    batch_ts: str,
    applied_at: str,
    outcome: PatchOutcome,
) -> None:
    """Grava um patch aplicado (OR IGNORE respeita o UNIQUE(env, ptm_hash))."""
    conn.execute(
        "INSERT OR IGNORE INTO patches_applied "
        "(env, build, ptm_name, ptm_hash, status, applied_at, batch_ts, log_path, backup_path, detail) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            env,
            build,
            outcome.ptm_name,
            outcome.ptm_hash,
            outcome.status,
            applied_at,
            batch_ts,
            outcome.log_path,
            outcome.backup_path,
            outcome.detail,
        ),
    )
    conn.commit()


# --------------------------------------------------------------------------- #
# Lock por environment
# --------------------------------------------------------------------------- #
def _lock_path(env: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", env)
    return Path.home() / ".plugadvpl" / "locks" / f"{safe}.lock"


@contextlib.contextmanager
def env_lock(env: str) -> Iterator[None]:
    """Lock exclusivo por environment durante a batch. Raise se já houver lock."""
    lock = _lock_path(env)
    lock.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(lock, flags, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(
            f"lock ocupado: {lock} — outra batch de apply-patch em andamento no env '{env}'. "
            f"Se for órfão, remova o arquivo manualmente."
        ) from exc
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        with contextlib.suppress(OSError):
            lock.unlink()


# --------------------------------------------------------------------------- #
# Orquestrador
# --------------------------------------------------------------------------- #
def _run_advpls(binary: Path, ini_path: Path) -> str:
    """Roda `advpls cli <ini>` e devolve a saída decodificada (stdout+stderr)."""
    proc = subprocess.run(
        [str(binary), "cli", str(ini_path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return _decode_advpls_output(proc.stdout or b"")


def run_apply_patch(
    *,
    input_path: Path,
    server: Server,
    environment: str,
    user: str,
    password: str,
    binary: Path,
    conn: sqlite3.Connection,
    audit_base: Path,
    apply_old: bool = False,
    backup_rpo_path: Path | None = None,
) -> ApplyPatchResult:
    """Aplica um `.PTM`/`.zip`/diretório no `environment`, 1 `advpls cli` por patch.

    - idempotência: skip por hash já em ``patches_applied``;
    - backup: best-effort (só quando ``backup_rpo_path`` aponta pra RPO acessível);
    - defrag: na última invocação que realmente aplica;
    - aborta a sequência no primeiro ``failed`` (rollback fica a cargo de --rollback*).

    Side effects: tempdir, subprocess advpls, escrita em ``audit_dir`` e na ``conn``.
    O lock por env é responsabilidade do caller (use :func:`env_lock`).
    """
    batch_ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    audit_dir = audit_base / batch_ts
    audit_dir.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="plugadvpl-patch-"))
    if os.name == "posix":
        workdir.chmod(0o700)

    outcomes: list[PatchOutcome] = []
    build = ""
    try:
        ptms = discover_ptms(input_path, workdir)
        if not ptms:
            return ApplyPatchResult(
                ok=True,
                server=server.name,
                environment=environment,
                batch_ts=batch_ts,
                patches=[],
                error="nenhum .PTM encontrado no input",
            )

        # Pré-classifica skip (idempotência) pra saber qual é o último que aplica (defrag).
        plan: list[tuple[Path, str, bool]] = []  # (ptm, hash, skip)
        for ptm in ptms:
            h = sha256_file(ptm)
            plan.append((ptm, h, is_applied(conn, environment, h)))
        to_apply_idx = [i for i, (_, _, skip) in enumerate(plan) if not skip]
        last_apply = to_apply_idx[-1] if to_apply_idx else -1

        aborted = False
        for i, (ptm, h, skip) in enumerate(plan):
            if aborted:
                break
            if skip:
                outcomes.append(
                    PatchOutcome(
                        ptm_name=ptm.name,
                        ptm_hash=h,
                        status="skipped",
                        detail=f"hash já em patches_applied (env {environment})",
                    )
                )
                continue

            log_path = audit_dir / f"patch_{i + 1}.log"
            backup_path = _maybe_backup(backup_rpo_path, audit_dir, ptm.name)
            ini_content = build_patch_ini(
                server,
                environment,
                user,
                password,
                ptm,
                log_path,
                apply_old=apply_old,
                with_defrag=(i == last_apply),
            )
            ini_path, ini_tmp = _write_secure_ini(ini_content)
            try:
                console = _run_advpls(binary, ini_path)
            finally:
                shutil.rmtree(ini_tmp, ignore_errors=True)

            # advpls escreve no logToFile; cai pro console se o arquivo não existir.
            log_text = (
                log_path.read_text(encoding="utf-8", errors="replace")
                if log_path.exists()
                else console
            )
            build = build or extract_build(log_text)
            status, detail = parse_patch_log(log_text)
            outcome = PatchOutcome(
                ptm_name=ptm.name,
                ptm_hash=h,
                status=status,
                log_path=str(log_path),
                backup_path=backup_path,
                detail=detail,
            )
            outcomes.append(outcome)
            if status in ("applied", "partial"):
                applied_at = datetime.now(UTC).isoformat()
                _record(
                    conn,
                    env=environment,
                    build=build,
                    batch_ts=batch_ts,
                    applied_at=applied_at,
                    outcome=outcome,
                )
            else:  # failed -> aborta sequência
                aborted = True
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    ok = not any(o.status == "failed" for o in outcomes)
    return ApplyPatchResult(
        ok=ok,
        server=server.name,
        environment=environment,
        batch_ts=batch_ts,
        patches=outcomes,
        build=build,
    )


def _maybe_backup(backup_rpo_path: Path | None, audit_dir: Path, ptm_name: str) -> str:
    """Backup best-effort do RPO antes do patch. Vazio se não houver path acessível.

    O `Server` registry não guarda o caminho do RPO no filesystem, e o advpls aplica
    via AppServer (que pode ser remoto). Então backup só é possível quando o caller
    passa um `backup_rpo_path` local acessível (tipicamente AppServer na mesma máquina).
    """
    if backup_rpo_path is None or not backup_rpo_path.is_file():
        return ""
    backups = audit_dir / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    dest = backups / f"{ptm_name}.rpo"
    shutil.copy2(backup_rpo_path, dest)
    return str(dest)
