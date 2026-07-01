"""Fase 4 do roadmap-ia — gate de qualidade das descriptions de skill (CI, $0).

A `description` É o roteador (Anthropic Agent Skills). Este gate roda o
lint_description sobre TODAS as skills embarcadas e trava se alguma tiver
description vaga / em 1ª pessoa / curta demais — pegando o risco de
*skill shadowing* à medida que o catálogo cresce.
"""

from __future__ import annotations

from pathlib import Path

from plugadvpl._skill_catalog import _SKILL_GLOBS, _parse_skill_md
from plugadvpl.dispatch_eval import lint_description

_SKILLS = Path(__file__).resolve().parents[3] / "skills"


def test_all_skill_descriptions_pass_lint() -> None:
    errors: list[str] = []
    for name in _SKILL_GLOBS:
        md = _SKILLS / name / "SKILL.md"
        if not md.exists():
            continue
        description, _ = _parse_skill_md(md.read_text(encoding="utf-8"))
        errors.extend(lint_description(name, description))
    assert errors == [], f"descriptions com problema (Fase 4): {errors}"
