"""Orquestrador do plugadvpl migrate-tlpp (v0.18.0+).

Aplica recipes em ordem canônica topológica (spec §3.6), com
safety gates pre-flight (git clean, DB ingest check, backup),
auto-validação via compile, e rollback cascata em 3 níveis
(.bak → git checkout → abort exit 2).

Spec: docs/superpowers/specs/2026-05-31-migrate-tlpp-design.md
"""

from __future__ import annotations

import subprocess
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import typer

from plugadvpl.migrate_tlpp_recipes import (
    REGISTRY,
    MigrationContext,
    RecipeResult,
    _register_all,
    filter_by_category,
)

if TYPE_CHECKING:
    import sqlite3


@dataclass(frozen=True)
class MigrationPlan:
    """Spec do que migrar: arquivo + flags."""

    file_path: Path
    project_root: Path
    enable_idioms: bool = False
    tlpp_version: tuple[int, int, int] = (0, 0, 0)
    allow_dirty: bool = False
    no_impact_check: bool = False
    selected_recipes: tuple[str, ...] = ()  # vazio = todos os filtrados por category


@dataclass(frozen=True)
class MigrationReport:
    """Resultado agregado de aplicar todas recipes a 1 arquivo."""

    file_path: Path
    recipe_results: list[RecipeResult] = field(default_factory=list)
    final_content: str | None = None  # conteúdo após todas recipes
    rollback_used: Literal["none", "bak", "git", "failed"] = "none"
    compile_validated: bool = False

    def counts(self) -> dict[str, int]:
        return dict(Counter(r.status for r in self.recipe_results))

    def has_errors(self) -> bool:
        return any(r.status == "error" for r in self.recipe_results)

    def all_todos(self) -> list[str]:
        return [t for r in self.recipe_results for t in r.todo_markers]


def _check_pre_flight(plan: MigrationPlan) -> list[str]:
    """Pre-flight gates (spec §4.1). Retorna lista de erros bloqueantes."""
    errors: list[str] = []

    # §4.1.1 — git working tree limpo
    if not plan.allow_dirty:
        try:
            r = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=plan.project_root,
                capture_output=True,
                timeout=10,
            )
            if r.stdout.strip():
                errors.append(
                    "git working tree não está limpo. "
                    "Use --allow-dirty pra prosseguir."
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # Sem git ou hangs — ignora (warning seria nice, sem bloqueio)
            pass

    # §4.1.3 — DB populated (CRITICAL pra caller detection)
    if not plan.no_impact_check:
        db_path = plan.project_root / ".plugadvpl" / "index.db"
        if not db_path.exists():
            errors.append(
                "DB .plugadvpl/index.db ausente. "
                "Execute 'plugadvpl ingest' antes "
                "OU use --no-impact-check "
                "(preserva nomes truncados; modo conservador)."
            )

    return errors


def _open_db(project_root: Path) -> sqlite3.Connection | None:
    """Abre DB read-only se existe."""
    import sqlite3

    db_path = project_root / ".plugadvpl" / "index.db"
    if not db_path.exists():
        return None
    try:
        return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except sqlite3.OperationalError:
        return None


def _select_recipes(plan: MigrationPlan) -> list[str]:
    """Filtra + ordena topologicamente as recipes a executar."""
    _register_all()
    available = filter_by_category(plan.enable_idioms)
    if plan.selected_recipes:
        # Intersect mantendo ordem canônica de available
        selected = set(plan.selected_recipes)
        return [r for r in available if r in selected]
    return available


def dry_run(plan: MigrationPlan) -> MigrationReport:
    """Aplica recipes IN MEMORY (sem tocar FS). Retorna report com diffs."""
    db_conn = _open_db(plan.project_root)
    ctx = MigrationContext(
        file_path=plan.file_path,
        project_root=plan.project_root,
        enable_idioms=plan.enable_idioms,
        tlpp_version=plan.tlpp_version,
        db_connection=db_conn,
    )
    # Read raw bytes + decode cp1252 (caso especial pra convert-encoding;
    # recipe é só marker — orquestrador faz I/O)
    try:
        raw = plan.file_path.read_bytes()
        # detect: utf-8 BOM → utf-8; senão utf-8 strict; senão cp1252
        if raw.startswith(b"\xef\xbb\xbf"):
            content = raw.decode("utf-8-sig")
        else:
            try:
                content = raw.decode("utf-8")
            except UnicodeDecodeError:
                content = raw.decode("cp1252", errors="replace")
    except OSError as e:
        return MigrationReport(
            file_path=plan.file_path,
            recipe_results=[
                RecipeResult(
                    recipe_id="io",
                    status="error",
                    message=f"read failed: {e!r}",
                )
            ],
        )

    selected_ids = _select_recipes(plan)
    results: list[RecipeResult] = []
    current_content = content
    for rid in selected_ids:
        recipe = REGISTRY[rid]
        try:
            r = recipe.apply(current_content, ctx)
            results.append(r)
            if r.new_content is not None and r.status in ("ok", "needs-review"):
                current_content = r.new_content
        except Exception as e:  # noqa: BLE001 — recipe não deve quebrar pipeline
            results.append(
                RecipeResult(
                    recipe_id=rid,
                    status="error",
                    message=f"{e!r}",
                )
            )

    # final_content é setado se conteúdo mudou OU se algum recipe 'ok'
    # produziu side-effect (ex: rename-extension não muda content mas
    # exige write em path novo).
    has_ok_sideeffect = any(r.status == "ok" for r in results)
    if current_content != content or has_ok_sideeffect:
        final = current_content
    else:
        final = None
    return MigrationReport(
        file_path=plan.file_path,
        recipe_results=results,
        final_content=final,
    )


def _create_backup(file_path: Path) -> Path | None:
    """Cria backup .bak.<YYYYMMDDHHMMSS>.

    Preserva .bak legado sem timestamp (não sobrescreve).
    """
    if not file_path.exists():
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    bak_path = file_path.with_suffix(file_path.suffix + f".bak.{ts}")
    if bak_path.exists():
        # já existe (run anterior no mesmo segundo) — não sobrescreve
        return bak_path
    bak_path.write_bytes(file_path.read_bytes())
    return bak_path


def _find_oldest_bak(file_path: Path) -> Path | None:
    """Acha .bak.<timestamp> mais antigo OU .bak legado."""
    parent = file_path.parent
    base = file_path.name
    candidates = sorted(parent.glob(f"{base}.bak.*"))
    if candidates:
        # mais antigo (sort lexicográfico de timestamp = cronológico)
        return candidates[0]
    legacy = file_path.with_suffix(file_path.suffix + ".bak")
    return legacy if legacy.exists() else None


def _restore_via_git(file_path: Path, project_root: Path) -> bool:
    """Tenta ``git checkout HEAD -- <file>``. Returns True se OK."""
    try:
        r = subprocess.run(
            ["git", "checkout", "HEAD", "--", str(file_path)],
            cwd=project_root,
            capture_output=True,
            timeout=10,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _validate_via_compile(tlpp_path: Path) -> bool:
    """Roda plugadvpl compile <tlpp> em modo appre. True se exit=0."""
    try:
        from plugadvpl.compile import CompileRequest
        from plugadvpl.compile import run as compile_run
        from plugadvpl.runtime_config import RuntimeConfig

        req = CompileRequest(
            files=[tlpp_path],
            mode="appre",
            no_warnings=False,
        )
        cfg = RuntimeConfig.load_or_default()
        result = compile_run(req, cfg, tlpp_path.parent)
        return result.exit_code == 0
    except Exception:  # noqa: BLE001 — validate é best-effort
        return False


def _rollback_cascade(
    file_path: Path,
    tlpp_path: Path,
    bak_path: Path | None,
    project_root: Path,
) -> Literal["bak", "git", "failed"]:
    """Cascata §4.2.4: bak → git → abort."""
    # Tentativa primária: restore via bak
    if bak_path is None:
        bak_path = _find_oldest_bak(file_path)
    if bak_path and bak_path.exists():
        try:
            file_path.write_bytes(bak_path.read_bytes())
            if tlpp_path.exists() and tlpp_path != file_path:
                tlpp_path.unlink()
            return "bak"
        except OSError:
            pass

    # Fallback 1: git checkout
    if _restore_via_git(file_path, project_root):
        if tlpp_path.exists() and tlpp_path != file_path:
            try:
                tlpp_path.unlink()
            except OSError:
                pass
        return "git"

    # Fallback 2: abort
    return "failed"


def _write_and_rename(report: MigrationReport, plan: MigrationPlan) -> Path:
    """Aplica final_content + rename .prw → .tlpp se rename-extension rodou.

    Retorna path final (.tlpp se rename ok, .prw se não).
    """
    if report.final_content is None:
        return plan.file_path  # nada mudou
    # Detecta se rename-extension rodou OK
    rename_ok = any(
        r.recipe_id == "rename-extension" and r.status == "ok"
        for r in report.recipe_results
    )
    target = (
        plan.file_path.with_suffix(".tlpp") if rename_ok else plan.file_path
    )
    target.write_text(report.final_content, encoding="utf-8")
    if rename_ok and plan.file_path != target and plan.file_path.exists():
        plan.file_path.unlink()
    return target


def apply(plan: MigrationPlan, *, validate: bool = False) -> MigrationReport:
    """Aplica recipes ao FS (com pre-flight, backup, validate, rollback)."""
    errors = _check_pre_flight(plan)
    if errors:
        return MigrationReport(
            file_path=plan.file_path,
            recipe_results=[
                RecipeResult(
                    recipe_id="pre-flight",
                    status="error",
                    message="; ".join(errors),
                )
            ],
        )

    # Backup ANTES de qualquer write
    bak_path = _create_backup(plan.file_path)

    # Dry run pra obter final_content
    report = dry_run(plan)
    if report.final_content is None:
        return report  # nada a aplicar

    # Write + rename
    target = _write_and_rename(report, plan)

    # Validate
    if validate:
        ok = _validate_via_compile(target)
        if not ok:
            # Rollback cascade
            outcome = _rollback_cascade(
                plan.file_path, target, bak_path, plan.project_root
            )
            new_report = MigrationReport(
                file_path=plan.file_path,
                recipe_results=report.recipe_results,
                final_content=None,
                rollback_used=outcome,
                compile_validated=False,
            )
            if outcome == "failed":
                typer.echo(
                    "CRITICAL: rollback falhou. "
                    "Arquivo em estado intermediário. "
                    f"Restaure manualmente de {bak_path} ou via git.",
                    err=True,
                )
                raise typer.Exit(code=2)
            return new_report
        return MigrationReport(
            file_path=target,
            recipe_results=report.recipe_results,
            final_content=report.final_content,
            rollback_used="none",
            compile_validated=True,
        )

    return MigrationReport(
        file_path=target,
        recipe_results=report.recipe_results,
        final_content=report.final_content,
        rollback_used="none",
        compile_validated=False,
    )
