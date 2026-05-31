"""Snapshot tests para o pipeline migrate-tlpp roundtrip (v0.18.0+).

Cobre 5 cenários sintéticos via ``dry_run`` (sem tocar FS):

1. ``simple_user_function.prw`` — User Function + ConOut (SAFE + IDIOMS).
2. ``with_begin_sequence.prw`` — Begin Sequence / Recover (IDIOMS).
3. ``with_json_object.prw`` — JsonObject():New() chain (IDIOMS).
4. ``with_public_var.prw`` — PUBLIC default var (SAFE).
5. ``SIGAFAT/with_namespace_hint.prw`` — path indutivo pra namespace-infer.

Snapshots em ``__snapshots__/test_migrate_tlpp_snapshots.ambr`` (syrupy).
Atualizar com ``pytest --snapshot-update``.
"""

from __future__ import annotations

from pathlib import Path

from plugadvpl.migrate_tlpp import MigrationPlan, dry_run

FIXTURES = Path(__file__).parent.parent / "fixtures" / "migrate_tlpp"
PROJECT_ROOT = Path(__file__).parent.parent.parent


def _final(plan: MigrationPlan) -> str:
    report = dry_run(plan)
    # final_content é None quando nada mudou — devolve sentinela
    return report.final_content if report.final_content is not None else "<NOCHANGE>"


def test_simple_user_function_snapshot(snapshot) -> None:  # type: ignore[no-untyped-def]
    plan = MigrationPlan(
        file_path=FIXTURES / "simple_user_function.prw",
        project_root=PROJECT_ROOT,
        enable_idioms=True,
        tlpp_version=(20, 3, 2),
        no_impact_check=True,
        allow_dirty=True,
    )
    assert _final(plan) == snapshot


def test_with_begin_sequence_snapshot(snapshot) -> None:  # type: ignore[no-untyped-def]
    plan = MigrationPlan(
        file_path=FIXTURES / "with_begin_sequence.prw",
        project_root=PROJECT_ROOT,
        enable_idioms=True,
        tlpp_version=(20, 3, 2),
        no_impact_check=True,
        allow_dirty=True,
    )
    assert _final(plan) == snapshot


def test_with_json_object_snapshot(snapshot) -> None:  # type: ignore[no-untyped-def]
    plan = MigrationPlan(
        file_path=FIXTURES / "with_json_object.prw",
        project_root=PROJECT_ROOT,
        enable_idioms=True,
        tlpp_version=(20, 3, 2),
        no_impact_check=True,
        allow_dirty=True,
    )
    assert _final(plan) == snapshot


def test_with_public_var_snapshot(snapshot) -> None:  # type: ignore[no-untyped-def]
    plan = MigrationPlan(
        file_path=FIXTURES / "with_public_var.prw",
        project_root=PROJECT_ROOT,
        enable_idioms=False,  # PUBLIC removal é SAFE
        tlpp_version=(20, 3, 2),
        no_impact_check=True,
        allow_dirty=True,
    )
    assert _final(plan) == snapshot


def test_with_namespace_hint_snapshot(snapshot) -> None:  # type: ignore[no-untyped-def]
    plan = MigrationPlan(
        file_path=FIXTURES / "SIGAFAT" / "with_namespace_hint.prw",
        project_root=PROJECT_ROOT,
        enable_idioms=True,  # namespace-infer é IDIOMS
        tlpp_version=(20, 3, 2),
        no_impact_check=True,
        allow_dirty=True,
    )
    assert _final(plan) == snapshot
