"""GitHub Copilot Instructions generator + installer pra plugadvpl init (v0.16.3+).

Detecta `.github/` no projeto e gera:
- `.github/copilot-instructions.md` (global, markdown plano, repo-wide)
- `.github/instructions/plugadvpl-<X>.instructions.md` (52 specifics com applyTo glob)

Fonte: skills/<X>/SKILL.md embarcadas (via _skill_catalog._SKILL_GLOBS).
Compartilha helpers com cursor_rules via plugadvpl._skill_catalog (DRY).

Spec: docs/superpowers/specs/2026-05-29-copilot-instructions-design.md
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CopilotTarget:
    """Decisão do detect_copilot: o que instalar."""

    install_global: bool   # .github/copilot-instructions.md
    install_local: bool    # .github/instructions/plugadvpl-*.instructions.md


def detect_copilot(project_root: Path) -> CopilotTarget:
    """Política simples: `.github/` no projeto → instala ambos.

    Menos conservador que detect_cursor — copilot-instructions.md é
    markdown inerte pra quem não usa Copilot (sem efeito colateral),
    e `.github/` é convenção amplamente adotada em projetos GitHub.
    """
    if (project_root / ".github").exists():
        return CopilotTarget(install_global=True, install_local=True)
    return CopilotTarget(install_global=False, install_local=False)
