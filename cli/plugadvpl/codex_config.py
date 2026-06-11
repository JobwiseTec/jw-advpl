"""OpenAI Codex CLI per-project config generator (v0.16.5+).

Detecta Codex (.codex/ no projeto OU 'codex' no PATH) e gera
.codex/config.toml mínimo com defaults comentados. Codex já lê AGENTS.md
automaticamente (gerado pelo plugadvpl init via _write_agent_fragment).
Este config é opt-in pra customizações futuras.

Spec: docs/superpowers/specs/2026-05-30-multi-agent-v0165-improvements.md secao 3.7
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import TYPE_CHECKING

from plugadvpl._skill_catalog import WriteOutcome, _write_managed_file

if TYPE_CHECKING:
    from pathlib import Path

CODEX_MARKER_PREFIX = "# plugadvpl-codex-version:"


@dataclass(frozen=True)
class CodexTarget:
    """Decisão do detect_codex: instalar config.toml ou no-op."""

    install_config: bool


def detect_codex(project_root: Path) -> CodexTarget:
    """Detection conservadora: ``.codex/`` no projeto OU ``codex`` no PATH."""
    if (project_root / ".codex").exists():
        return CodexTarget(install_config=True)
    if shutil.which("codex") is not None:
        return CodexTarget(install_config=True)
    return CodexTarget(install_config=False)


_CODEX_CONFIG_TEMPLATE = """# .codex/config.toml — Codex CLI per-project config
#
# Gerado por plugadvpl init. Edite livremente — marker abaixo controla
# regeneração; remova-o pra preservar customizações manuais.
# Docs: https://developers.openai.com/codex/cli/configuration
#
# plugadvpl-codex-version: __VERSION__

[project]
# Codex carrega AGENTS.md automaticamente (gerado também pelo plugadvpl init).
# Para ler arquivos adicionais como contexto:
# project_doc_fallback_filenames = ["CLAUDE.md"]

# Skills do plugadvpl ficam em .agents/skills/plugadvpl-*/SKILL.md (padrão
# aberto — Codex faz auto-discovery). Também replicadas em .codex/skills/
# para versões experimentais do Codex. Para registrar ou desabilitar caminhos
# específicos (opcional — não é necessário pro auto-discovery):
# [[skills.config]]
# path = ".agents/skills/plugadvpl-arch"
# enabled = true
"""


def render_codex_config(version: str) -> str:
    """Gera conteúdo de ``.codex/config.toml`` com marker."""
    return _CODEX_CONFIG_TEMPLATE.replace("__VERSION__", version)


@dataclass(frozen=True)
class InstallResult:
    """Resumo do install_codex_config."""

    installed: bool
    skipped_due_to_user_file: bool = False
    error: str | None = None

    def summary(self) -> str:
        if self.installed:
            return ".codex/config.toml instalado"
        if self.skipped_due_to_user_file:
            return ".codex/config.toml já existe sem marker (preservado)"
        return "nada instalado"


def install_codex_config(project_root: Path, version: str) -> InstallResult:
    """Orquestra detect + render + write. NUNCA propaga exception."""
    try:
        target = detect_codex(project_root)
    except Exception as e:
        return InstallResult(installed=False, error=f"detect_codex falhou: {e!r}")

    if not target.install_config:
        return InstallResult(installed=False)

    try:
        config_path = project_root / ".codex" / "config.toml"
        content = render_codex_config(version)
        outcome = _write_managed_file(config_path, content, CODEX_MARKER_PREFIX)
        if outcome in (WriteOutcome.WRITTEN, WriteOutcome.OVERWRITTEN):
            return InstallResult(installed=True)
        if outcome == WriteOutcome.SKIPPED_USER_FILE:
            return InstallResult(installed=False, skipped_due_to_user_file=True)
        return InstallResult(installed=False, error=f"falha ao escrever {config_path}")
    except Exception as e:
        return InstallResult(installed=False, error=f"install_codex_config erro: {e!r}")
