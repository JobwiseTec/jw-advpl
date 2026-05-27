"""Orquestrador do plugadvpl compile (v0.8.0 Fase 1).

Único módulo que toca subprocess + filesystem. Demais (runtime_config,
compile_parser) são funções puras. Spec: docs/fase1/compile-design.md §5, §7.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from plugadvpl.compile_doctor import _detect_advpls
from plugadvpl.compile_parser import Diagnostic, parse_diagnostics
from plugadvpl.edit_prw import encode_cp1252_bytes

if TYPE_CHECKING:
    from plugadvpl.runtime_config import RuntimeConfig

# Exit codes acima de 255 ou negativos sao convencao Unix (signal) ou Windows
# unsigned overflow — normaliza pra 1.
_MAX_POSIX_EXIT_CODE = 255


@dataclass(frozen=True)
class CompileRequest:
    files: list[Path]
    mode: Literal["auto", "appre", "cli"]
    no_warnings: bool
    timeout_seconds: int | None
    no_security_warning: bool
    includes_override: list[Path] | None
    changed_since: str | None


@dataclass(frozen=True)
class CompileResult:
    rows: list[dict[str, object]]
    summary: dict[str, object]
    next_steps: list[str]
    exit_code: int


@dataclass(frozen=True)
class ResolvedFiles:
    valid_files: list[Path]
    missing: list[Path]
    rejected_ext: list[Path]


_VALID_EXTS = (".prw", ".prx", ".tlpp", ".tlpp.ch")


def resolve_files(files: list[Path], changed_since: str | None, root: Path) -> ResolvedFiles:
    if changed_since:
        files = _resolve_changed_since(changed_since, root)
    valid: list[Path] = []
    missing: list[Path] = []
    rejected: list[Path] = []
    for f in files:
        name = f.name.lower()
        ok_ext = any(name.endswith(ext) for ext in _VALID_EXTS)
        if not ok_ext:
            rejected.append(f)
            continue
        if not f.exists():
            missing.append(f)
            continue
        valid.append(f)
    return ResolvedFiles(valid_files=valid, missing=missing, rejected_ext=rejected)


def _resolve_changed_since(ref: str, root: Path) -> list[Path]:
    """git diff --name-only <ref> filtrado por extensões."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", ref, "--", "*.prw", "*.prx", "*.tlpp"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"--changed-since requires a git repository at {root}: {exc.stderr.strip()}"
        ) from exc
    except FileNotFoundError as exc:
        raise RuntimeError("git not found in PATH") from exc
    return [root / line for line in proc.stdout.splitlines() if line.strip()]


def pick_mode(requested: str, runtime_cfg: RuntimeConfig | None) -> str:
    if requested in ("cli", "appre"):
        return requested
    if runtime_cfg is not None and runtime_cfg.appserver_reachable:
        return "cli"
    return "appre"


_UTF8_BOM = b"\xef\xbb\xbf"
_UTF16_LE_BOM = b"\xff\xfe"
_UTF16_BE_BOM = b"\xfe\xff"


def _decode_advpls_output(raw: bytes) -> str:
    """Decodifica saída do advpls tratando BOM UTF-16 (PowerShell/WinSrv) e fallback CP1252."""
    if raw.startswith(_UTF16_LE_BOM):
        return raw[len(_UTF16_LE_BOM) :].decode("utf-16-le", errors="replace")
    if raw.startswith(_UTF16_BE_BOM):
        return raw[len(_UTF16_BE_BOM) :].decode("utf-16-be", errors="replace")
    if raw.startswith(_UTF8_BOM):
        raw = raw[len(_UTF8_BOM) :]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _resolve_advpls(runtime_cfg: RuntimeConfig | None) -> Path:
    """Resolve path do advpls. MESMA ordem que ``compile_doctor._detect_advpls``.

    v0.8.8 fix: bug em que ``--install-advpls`` instalava em
    ``~/.plugadvpl/advpls/`` e ``--doctor`` detectava sozinho, mas o
    ``compile`` real não — porque essa função só olhava PATH/env/runtime_cfg.
    Agora delega pra ``_detect_advpls`` do doctor (fonte única de verdade).
    """
    # 1. Env var tem prioridade absoluta
    env_override = os.environ.get("PLUGADVPL_ADVPLS_BINARY")
    if env_override:
        return Path(env_override)
    # 2. runtime.toml [tds_ls].binary explícito
    if runtime_cfg is not None:
        return runtime_cfg.tds_ls.binary
    # 3. Auto-detect (pasta interna ~/.plugadvpl/advpls/, PATH, extensão VSCode)
    detected = _detect_advpls()
    if detected is not None:
        return detected
    raise RuntimeError(
        "advpls não encontrado. Opções:\n"
        "  • plugadvpl compile --install-advpls   (instala em ~/.plugadvpl/advpls/)\n"
        "  • export PLUGADVPL_ADVPLS_BINARY=<path>\n"
        "  • configure [tds_ls].binary no runtime.toml\n"
        "  • adicione advpls ao PATH"
    )


def _build_ini_script(runtime_cfg: RuntimeConfig, files: list[Path], includes: list[Path]) -> str:
    """Gera conteúdo do script .ini do advpls cli mode (formato §6 do spec).

    v0.8.11: env vars validadas aqui (não mais no load do TOML), porque
    [auth] virou opcional no runtime.toml — só mode=cli precisa.
    """
    user_env = runtime_cfg.auth.user_env
    pwd_env = runtime_cfg.auth.password_env
    user = os.environ.get(user_env)
    pwd = os.environ.get(pwd_env)
    if not user or not pwd:
        missing = [v for v, val in ((user_env, user), (pwd_env, pwd)) if not val]
        raise RuntimeError(
            f"cli mode needs env vars set: {', '.join(missing)} "
            f"(referenced by [auth] in runtime.toml). "
            f"Either export them or use --mode appre (no AppServer connection)."
        )
    asv = runtime_cfg.appserver
    log = runtime_cfg.logging

    lines: list[str] = []
    lines.append(f"logToFile={log.log_to_file}")
    lines.append(f"showConsoleOutput={'true' if log.show_console_output else 'false'}")
    lines.append("")
    lines.append("[auth]")
    lines.append("action=authentication")
    lines.append(f"server={asv.host}")
    lines.append(f"port={asv.port}")
    lines.append(f"secure={1 if asv.secure else 0}")
    lines.append(f"build={asv.build}")
    lines.append(f"environment={asv.environment}")
    lines.append(f"user={user}")
    lines.append(f"psw={pwd}")
    lines.append("")
    lines.append("[compile]")
    lines.append("action=compile")
    # Normaliza pra forward-slash — formato .ini aceito pelo advpls em Win/Linux
    # e evita ambiguidade de escape de backslash em arquivo .ini.
    lines.append(f"program={';'.join(str(f).replace(chr(92), '/') for f in files)}")
    lines.append(f"recompile={'T' if runtime_cfg.compile.recompile else 'F'}")
    lines.append(f"includes={';'.join(str(i).replace(chr(92), '/') for i in includes)}")
    return "\n".join(lines) + "\n"


def _write_secure_ini(content: str) -> tuple[Path, Path]:
    """Cria tempdir (0o700) + escreve ini (0o600) em CP1252.

    Retorna (ini_path, tempdir_path) — caller é responsável por shutil.rmtree.
    Em Windows, mode é ignorado mas o uuid no path do mkdtemp mitiga reading-by-name.
    """
    tempdir = Path(tempfile.mkdtemp(prefix="plugadvpl-"))
    if os.name == "posix":
        tempdir.chmod(0o700)
    ini_path = tempdir / "compile.ini"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):  # Windows
        flags |= os.O_BINARY
    fd = os.open(ini_path, flags, 0o600)
    try:
        os.write(fd, encode_cp1252_bytes(content))
    finally:
        os.close(fd)
    return ini_path, tempdir


def _build_appre_args(
    binary: Path, includes: list[Path], files: list[Path], output_dir: Path
) -> list[str]:
    """Args do ``advpls appre``. Usa ``-O`` para controlar onde ``.errprw`` é gravado.

    Sem ``-O``, o advpls escreve no CWD do processo — torna leitura posterior
    dos diagnostics frágil (depende do cwd). Forçar tempdir garante isolamento.
    """
    args: list[str] = [str(binary), "appre", "-O", str(output_dir)]
    for inc in includes:
        args.append(f"-I{inc}")
    args.extend(str(f) for f in files)
    return args


def _collect_errprw_diagnostics(output_dir: Path, files: list[Path]) -> dict[str, list[Diagnostic]]:
    """Lê ``<basename>.errprw`` para cada fonte em ``files``.

    Diagnostics do advpls ``appre`` NÃO vão para stdout/stderr — vão para
    arquivo ``<basename>.errprw`` em ``-O <dir>``. Esta função faz a leitura
    + parse usando ``force_arquivo`` (porque advpls reporta sempre
    ``APPRE41.PRW`` no arquivo do erro, não o fonte real).

    Retorna dict ``{str(fonte): list[Diagnostic]}``. Fontes sem ``.errprw``
    (compilação bem-sucedida) ficam ausentes.
    """
    by_file: dict[str, list[Diagnostic]] = {}
    for fonte in files:
        # advpls usa nome lowercase para .errprw (foo_real.errprw, não FOO_REAL.errprw)
        errprw = output_dir / (fonte.stem.lower() + ".errprw")
        if not errprw.is_file():
            continue
        try:
            content = errprw.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not content.strip():
            continue
        diags, _unmatched = parse_diagnostics(
            stdout=content,
            stderr="",
            mode="appre",
            requested_files=[fonte],
            force_arquivo=fonte,
        )
        if diags:
            by_file[str(fonte)] = diags
    return by_file


def _normalize_exit_code(returncode: int) -> int:
    """Normaliza ``proc.returncode`` para faixa CI-friendly.

    Windows: ``-1`` vira ``4294967295`` (0xFFFFFFFF) quando lido como unsigned.
    POSIX: já vem signed. Esta função converte para faixa ``0-255`` (POSIX
    convention) preservando 0 = sucesso, não-zero = falha.
    """
    if returncode == 0:
        return 0
    # Casos negativos (Unix signal) ou > 255 (Windows unsigned). Mapeia para 1.
    if returncode < 0 or returncode > _MAX_POSIX_EXIT_CODE:
        return 1
    return returncode


def _build_setup_error_result(files: list[Path], mode: str, exit_code: int) -> CompileResult:
    """Schema completo conforme §8 — CI consumer espera todos os campos."""
    return CompileResult(
        rows=[],
        summary={
            "total_files": len(files),
            "ok": 0,
            "failed": len(files),
            "total_errors": 0,
            "total_warnings": 0,
            "mode_used": mode,
            "appserver_reachable": False,
            "runtime_config_loaded": False,
            "output_truncated": False,
        },
        next_steps=[],
        exit_code=exit_code,
    )


def _build_timeout_result(files: list[Path], timeout: int | None, mode: str) -> CompileResult:
    rows: list[dict[str, object]] = []
    for f in files:
        rows.append(
            {
                "arquivo": str(f),
                "ok": False,
                "mode": mode,
                "duration_ms": (timeout or 0) * 1000,
                "exit_code": 124,
                "counts": {"error": 1, "warning": 0, "info": 0, "unknown": 0},
                "diagnostics": [
                    {
                        "severidade": "error",
                        "arquivo": str(f),
                        "linha": 0,
                        "coluna": 0,
                        "mensagem": f"compile timeout after {timeout}s",
                        "codigo": "",
                        "raw": "",
                    }
                ],
            }
        )
    summary: dict[str, object] = {
        "total_files": len(files),
        "ok": 0,
        "failed": len(files),
        "total_errors": len(files),
        "total_warnings": 0,
        "mode_used": mode,
        "appserver_reachable": False,
        "runtime_config_loaded": False,
        "output_truncated": False,
    }
    return CompileResult(rows=rows, summary=summary, next_steps=[], exit_code=1)


def _build_next_steps(rows: list[dict[str, object]], mode: str) -> list[str]:
    if all(r["ok"] for r in rows):
        return []
    failed_files = [
        str(r["arquivo"]) for r in rows if not r["ok"] and r["arquivo"] != "__unmatched__"
    ]
    steps: list[str] = []

    # Hint específico pro erro mais comum: include Protheus faltando (C2090).
    # Detecta varrendo diagnostics de todas as rows.
    has_c2090 = False
    for r in rows:
        diags = r.get("diagnostics")
        if not isinstance(diags, list):
            continue
        if any(isinstance(d, dict) and d.get("codigo") == "C2090" for d in diags):
            has_c2090 = True
            break
    if has_c2090:
        steps.append(
            "# Erro C2090 = include Protheus faltando. Setup completo em "
            "docs/setup-compile.md. Tipicamente: "
            "--includes <pasta-com-PRTOPDEF.CH-e-protheus.ch>"
        )

    if failed_files:
        steps.append(f"plugadvpl arch {failed_files[0]}   # contexto arquitetural")
    if mode == "appre":
        steps.append(
            "# appre é só pré-processador. Pra erros semânticos use "
            "--mode cli com AppServer rodando (ver docs/setup-compile.md §cli)."
        )
    steps.append("plugadvpl compile --no-warnings <file>   # filtra warnings")
    return steps


def run(request: CompileRequest, runtime_cfg: RuntimeConfig | None, root: Path) -> CompileResult:  # noqa: PLR0912, PLR0915 -- orquestrador end-to-end (resolve files, monta ini, dispara advpls, parseia output); split em fases viraria boilerplate sem ganho de clareza
    resolved = resolve_files(request.files, request.changed_since, root)
    files = resolved.valid_files
    mode = pick_mode(request.mode, runtime_cfg)
    binary = _resolve_advpls(runtime_cfg)

    tempdir: Path | None = None
    if mode == "cli":
        if runtime_cfg is None:
            print(
                "ERROR: runtime.toml required for cli mode. Run: plugadvpl compile --init-config",
                file=sys.stderr,
            )
            return _build_setup_error_result(files, mode, exit_code=2)

        if runtime_cfg.warn_remote_host and not request.no_security_warning:
            print(
                f"WARNING: appserver.host = {runtime_cfg.appserver.host} (não-local).\n"
                f"TDS-LS envia user/password sem TLS sobre TCP. Recomendado:\n"
                f"  ssh -L {runtime_cfg.appserver.port}:localhost:{runtime_cfg.appserver.port} "
                f"user@{runtime_cfg.appserver.host} -N\n"
                f'  # depois altere host = "127.0.0.1" em runtime.toml\n'
                f"(suprima com --no-security-warning)",
                file=sys.stderr,
            )
            # SEM sleep — princípio fail visivelmente (§7.5)

        includes = (
            request.includes_override
            if request.includes_override is not None
            else list(runtime_cfg.compile.includes)
        )
        ini_content = _build_ini_script(runtime_cfg, files, includes)
        ini_path, tempdir = _write_secure_ini(ini_content)
        args = [str(binary), "cli", str(ini_path)]
    else:
        includes = (
            request.includes_override
            if request.includes_override is not None
            else (list(runtime_cfg.compile.includes) if runtime_cfg else [])
        )
        # appre escreve erros em <output_dir>/<basename>.errprw — usa tempdir
        # dedicado (limpo no finally) pra isolar do CWD do processo.
        tempdir = Path(tempfile.mkdtemp(prefix="plugadvpl-appre-"))
        if os.name == "posix":
            tempdir.chmod(0o700)
        args = _build_appre_args(binary, includes, files, tempdir)

    start = time.monotonic()
    proc = subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    errprw_by_file: dict[str, list[Diagnostic]] = {}
    try:
        try:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=request.timeout_seconds)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            return _build_timeout_result(files, request.timeout_seconds, mode)
        except KeyboardInterrupt:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            raise
        # Captura .errprw em memória ANTES do finally (que apaga tempdir).
        # Diagnostics reais do advpls appre vão pra <tempdir>/<basename>.errprw,
        # NÃO stdout/stderr (que tem só log do connection_manager).
        if mode == "appre" and tempdir is not None:
            errprw_by_file = _collect_errprw_diagnostics(tempdir, files)
    finally:
        if tempdir is not None:
            try:
                shutil.rmtree(tempdir, ignore_errors=False)
            except OSError as exc:
                print(f"WARN: failed to delete tempdir {tempdir}: {exc}", file=sys.stderr)

    stdout = _decode_advpls_output(stdout_bytes)
    stderr = _decode_advpls_output(stderr_bytes)
    duration_ms = int((time.monotonic() - start) * 1000)
    normalized_returncode = _normalize_exit_code(proc.returncode)

    matched, unmatched = parse_diagnostics(
        stdout=stdout,
        stderr=stderr,
        mode=mode,
        requested_files=files,
    )

    # group diagnostics by file (requested only — defensivos vão pra __unmatched__)
    by_file: dict[str, list[Diagnostic]] = {str(f): [] for f in files}
    defensive_unmatched: list[Diagnostic] = []
    for d in matched:
        if d.arquivo in by_file:
            by_file[d.arquivo].append(d)
        else:
            # parse_diagnostics normalmente põe em unmatched, mas defensivamente:
            # contrato §7.8 / §11.3 — agrupa em __unmatched__ (nome estável).
            defensive_unmatched.append(d)

    # Mescla diagnostics do .errprw com os do stdout/stderr.
    for fpath, errprw_diags in errprw_by_file.items():
        by_file.setdefault(fpath, []).extend(errprw_diags)

    files_set = {str(f) for f in files}
    rows: list[dict[str, object]] = []
    for fpath, diags in by_file.items():
        counts = {
            "error": sum(1 for d in diags if d.severidade == "error"),
            "warning": sum(1 for d in diags if d.severidade == "warning"),
            "info": sum(1 for d in diags if d.severidade == "info"),
            "unknown": sum(1 for d in diags if d.severidade == "unknown"),
        }
        # ok requer: zero errors E (subprocess sucesso OU temos diagnostics estruturados)
        # Sem essa segunda condição, advpls que crasha sem produzir output marcaria ok=true.
        has_structured = counts["error"] > 0 or counts["warning"] > 0 or counts["info"] > 0
        ok_flag = counts["error"] == 0 and (normalized_returncode == 0 or has_structured)
        rows.append(
            {
                "arquivo": fpath,
                "ok": ok_flag,
                "mode": mode,
                "duration_ms": duration_ms,
                "exit_code": normalized_returncode,
                "counts": counts,
                "diagnostics": [d.to_dict() for d in diags],
            }
        )

    # Bucket __unmatched__: unmatched do parser + defensivos do agrupamento
    all_unmatched = defensive_unmatched + list(unmatched)
    if all_unmatched:
        unmatched_counts = {
            "error": sum(1 for d in all_unmatched if d.severidade == "error"),
            "warning": sum(1 for d in all_unmatched if d.severidade == "warning"),
            "info": sum(1 for d in all_unmatched if d.severidade == "info"),
            "unknown": sum(1 for d in all_unmatched if d.severidade == "unknown"),
        }
        rows.append(
            {
                "arquivo": "__unmatched__",
                "ok": False,
                "mode": mode,
                "duration_ms": duration_ms,
                "exit_code": normalized_returncode,
                "counts": unmatched_counts,
                "diagnostics": [d.to_dict() for d in all_unmatched],
            }
        )

    total_errors = 0
    total_warnings = 0
    for r in rows:
        counts_obj = r["counts"]
        if isinstance(counts_obj, dict):
            total_errors += int(counts_obj.get("error", 0) or 0)
            total_warnings += int(counts_obj.get("warning", 0) or 0)
    failed_requested = sum(1 for r in rows if r["arquivo"] in files_set and not r["ok"])
    # Exit do plugin: 1 se há error parseado OU subprocess falhou sem produzir
    # diagnostic (caso comum: advpls crash, includes faltando que travam pré).
    has_any_failure = total_errors > 0 or failed_requested > 0
    exit_code = 1 if has_any_failure else 0

    summary: dict[str, object] = {
        "total_files": len(files),
        "ok": len(files) - failed_requested,
        "failed": failed_requested,
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "mode_used": mode,
        "appserver_reachable": runtime_cfg.appserver_reachable if runtime_cfg else False,
        "runtime_config_loaded": runtime_cfg is not None,
        "output_truncated": False,
    }
    next_steps = _build_next_steps(rows, mode)
    return CompileResult(rows=rows, summary=summary, next_steps=next_steps, exit_code=exit_code)
