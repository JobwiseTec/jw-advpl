"""Cursor Rules generator + installer pra plugadvpl init (v0.16.2+).

Detecta Cursor instalado e gera .cursor/rules/*.mdc files que dão ao Cursor
o mesmo contexto que CLAUDE.md/AGENTS.md dão pro Claude Code: convenções
ADVPL/TLPP, comandos do plugadvpl, encoding cp1252, tabela de decisão, etc.

Single source: skills/<X>/SKILL.md embarcadas geram .mdc em runtime via
2 substituições de string. Falha aqui NUNCA quebra o init.
"""
from __future__ import annotations

import enum
import re
import shutil
from dataclasses import dataclass, field
from importlib import resources as ir
from pathlib import Path


@dataclass(frozen=True)
class CursorTarget:
    """Decisão do detect_cursor: o que instalar e onde."""

    install_global: bool   # ~/.cursor/rules/plugadvpl.mdc
    install_local: bool    # <project>/.cursor/rules/plugadvpl-*.mdc


def detect_cursor(project_root: Path) -> CursorTarget:
    """Decide o que instalar baseado em sinais conservadores.

    Global se ``~/.cursor/`` existe OU ``shutil.which("cursor")`` retorna path.
    Local se ``<project_root>/.cursor/`` existe.

    Conservador de propósito: não instalar `.cursor/rules/` num projeto onde
    o usuário nunca abriu Cursor é uma decisão de produto (evita pegada
    não-solicitada).
    """
    install_global = False
    install_local = False

    try:
        home = Path.home()
        if (home / ".cursor").exists():
            install_global = True
    except RuntimeError:
        # Container minimalista sem home — tudo False.
        return CursorTarget(install_global=False, install_local=False)

    if not install_global and shutil.which("cursor") is not None:
        install_global = True

    if (project_root / ".cursor").exists():
        install_local = True

    return CursorTarget(install_global=install_global, install_local=install_local)


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_DESC_RE = re.compile(r"^description:\s*(.+?)\s*$", re.MULTILINE)
_SLASH_RE = re.compile(r"/plugadvpl:([a-z0-9-]+)")
_UVX_VER_RE = re.compile(r"uvx plugadvpl@[\w.+-]+")


def _transform_body(body: str, version: str) -> str:
    """Aplica as 2 substituições da §3.3 do spec, NESTA ORDEM:

    3a) `/plugadvpl:<X>` → `` `Bash: uvx plugadvpl@<ver> <X>` ``
    3b) `uvx plugadvpl@<qualquer>` → `uvx plugadvpl@<ver>`

    Ordem importa: 3a primeiro emite uvx correto; 3b depois normaliza
    qualquer ocorrência pré-existente (ex: `uvx plugadvpl@0.15.0`).
    """
    body = _SLASH_RE.sub(rf"`Bash: uvx plugadvpl@{version} \1`", body)
    body = _UVX_VER_RE.sub(f"uvx plugadvpl@{version}", body)
    return body


def _parse_skill_md(skill_md_text: str) -> tuple[str, str]:
    """Extrai (description, body) de uma SKILL.md.

    Retorna fallback `("", body inteiro)` se não houver frontmatter parseável.
    """
    m = _FRONTMATTER_RE.match(skill_md_text)
    if m is None:
        return ("", skill_md_text)
    frontmatter, body = m.group(1), m.group(2)
    desc_match = _DESC_RE.search(frontmatter)
    description = desc_match.group(1) if desc_match else ""
    return (description, body)


def render_skill_rule(
    skill_md_path: Path, version: str, globs: list[str]
) -> str:
    """Gera conteúdo MDC pra `.cursor/rules/plugadvpl-<nome>.mdc`.

    Pipeline:
    1. Parse YAML frontmatter da SKILL.md (extrai `description`).
    2. Extrai body.
    3. Substitui `/plugadvpl:<X>` → `Bash: uvx plugadvpl@<ver> <X>`.
    4. Normaliza `uvx plugadvpl@<qualquer-ver>` → `uvx plugadvpl@<ver>`.
    5. Monta MDC com frontmatter (description + globs + alwaysApply=false) +
       markers de versão e skill.

    Edge case: SKILL.md sem/malformed frontmatter → description fallback.
    """
    skill_name = skill_md_path.parent.name
    raw = skill_md_path.read_text(encoding="utf-8")
    description, body = _parse_skill_md(raw)
    if not description:
        description = f"plugadvpl skill: {skill_name}"

    # Frontmatter MDC (linha globs omitida se vazia).
    frontmatter_lines = [f"description: {description}"]
    if globs:
        frontmatter_lines.append(f"globs: {', '.join(globs)}")
    frontmatter_lines.append("alwaysApply: false")
    frontmatter = "---\n" + "\n".join(frontmatter_lines) + "\n---\n"

    markers = (
        f"<!-- plugadvpl-rule-version: {version} -->\n"
        f"<!-- plugadvpl-skill: {skill_name} -->\n\n"
    )

    return frontmatter + markers + _transform_body(body, version)


_GLOBAL_DESCRIPTION = (
    "Convenções TOTVS Protheus (ADVPL/TLPP) + plugadvpl — "
    "índice local, encoding cp1252, comandos uvx, tabela de decisão"
)

_GLOBAL_BODY_TEMPLATE = """# plugadvpl — convenções ADVPL/TLPP (rule global)

Este projeto/workspace pode conter código TOTVS Protheus em **AdvPL** (`.prw`, `.prx`,
`.apw`) e **TLPP** (`.tlpp`). Se houver `.plugadvpl/index.db` no root do projeto, use
o índice via comandos `uvx plugadvpl@__VERSION__ <subcomando>` ANTES de ler `.prw`/`.tlpp`
cru — economiza ~16x tokens.

## Tabela de decisão — qual comando rodar antes de Read

| Pergunta | Comando |
|---|---|
| "explique o fonte X" / "o que faz Y" | `Bash: uvx plugadvpl@__VERSION__ arch <arq>` |
| "onde está a função X?" | `Bash: uvx plugadvpl@__VERSION__ find <nome>` |
| "quem chama X?" | `Bash: uvx plugadvpl@__VERSION__ callers <funcao>` |
| "o que X chama?" | `Bash: uvx plugadvpl@__VERSION__ callees <funcao>` |
| "quem mexe na tabela SA1?" | `Bash: uvx plugadvpl@__VERSION__ tables SA1` |
| "onde MV_LOCALIZA é usado?" | `Bash: uvx plugadvpl@__VERSION__ param MV_LOCALIZA` |
| "achar 'RecLock' nos fontes" | `Bash: uvx plugadvpl@__VERSION__ grep RecLock` |
| "tem problemas no fonte X?" | `Bash: uvx plugadvpl@__VERSION__ lint <arq>` |

## Encoding — CRÍTICO

- `.prw`/`.prx` são **cp1252**. Read/Write/Edit comuns são UTF-8 — bytes acentuados viram `�`.
- Antes de editar `.prw`: `Bash: uvx plugadvpl@__VERSION__ edit-prw stage <arq>` (converte pra UTF-8 com backup).
- Depois de editar: `Bash: uvx plugadvpl@__VERSION__ edit-prw commit <arq>` (volta pra cp1252).
- `.tlpp` é UTF-8 nativo — sem stage/commit.

## Workflow padrão pra "explique o programa X"

1. `Bash: uvx plugadvpl@__VERSION__ find X` — descobre arquivo
2. `Bash: uvx plugadvpl@__VERSION__ arch <arq>` — visão arquitetural
3. `Bash: uvx plugadvpl@__VERSION__ callees X` — o que X chama
4. `Bash: uvx plugadvpl@__VERSION__ callers X` — quem chama X
5. Só depois, se necessário, Read do arquivo com offset/limit do `arch`
"""


# Mapping skill → globs (spec §5). Skills sem entrada NÃO geram rule local.
# Adicionar nova skill = 1 entrada nessa constante.
_PRW = ["**/*.prw", "**/*.tlpp", "**/*.prx", "**/*.apw"]
_PRW_CSV = ["**/*.prw", "**/*.tlpp", "**/*.prx", "**/*.csv"]

_SKILL_GLOBS: dict[str, list[str]] = {
    # Skills com escopo ADVPL/TLPP source
    "arch": _PRW,
    "find": _PRW,
    "callers": _PRW,
    "callees": _PRW,
    "lint": _PRW,
    "grep": _PRW,
    "compile": _PRW,
    "tq": _PRW,
    "edit-prw": _PRW,
    "deploy": _PRW,
    "hotspots": _PRW,
    "metrics": _PRW,
    "cobertura-doc": _PRW,
    "plugadvpl-index-usage": _PRW,
    # Skills de conhecimento ADVPL/TLPP (reference/training)
    "advpl-advanced": _PRW,
    "advpl-code-review": _PRW,
    "advpl-debugging": _PRW,
    "advpl-dicionario-sx": _PRW,
    "advpl-dicionario-sx-validacoes": _PRW,
    "advpl-embedded-sql": _PRW,
    "advpl-encoding": _PRW,
    "advpl-fundamentals": _PRW,
    "advpl-jobs-rpc": _PRW,
    "advpl-matxfis": _PRW,
    "advpl-mvc": _PRW,
    "advpl-mvc-avancado": _PRW,
    "advpl-pontos-entrada": _PRW,
    "advpl-refactoring": _PRW,
    "advpl-tlpp": _PRW,
    "advpl-tlpp-named-params": _PRW,
    "advpl-web": _PRW,
    "advpl-webservice": _PRW,
    # Skills com escopo de dicionário SX (inclui CSV exportado)
    "tables": _PRW_CSV,
    "param": _PRW_CSV,
    "impacto": _PRW_CSV,
    "gatilho": _PRW_CSV,
    "ingest-sx": _PRW_CSV,
    "sx-status": _PRW_CSV,
    # Skills com escopo específico
    "ini-audit": ["**/*.ini"],
    "log-diagnose": ["**/*.log"],
    # Meta-skills — sem escopo (alwaysApply: false sem globs)
    "init": [],
    "ingest": [],
    "status": [],
    "doctor": [],
    "reindex": [],
    "help": [],
    "workflow": [],
    "execauto": [],
    "docs": [],
    "trace": [],
    "setup": [],
    "ingest-protheus": [],
}


def render_global_rule(version: str) -> str:
    """Gera conteúdo MDC pra ``~/.cursor/rules/plugadvpl.mdc`` (rule global).

    Sempre injetado em qualquer arquivo aberto (``alwaysApply: true``).
    Sem ``globs`` — vale pra qualquer arquivo do workspace.
    """
    frontmatter = (
        "---\n"
        f"description: {_GLOBAL_DESCRIPTION}\n"
        "alwaysApply: true\n"
        "---\n"
    )
    markers = f"<!-- plugadvpl-rule-version: {version} -->\n\n"
    body = _GLOBAL_BODY_TEMPLATE.replace("__VERSION__", version)
    return frontmatter + markers + body


_MARKER_PREFIX = "<!-- plugadvpl-rule-version:"


class WriteOutcome(enum.Enum):
    """Resultado de tentar escrever uma rule individual."""

    WRITTEN = "written"                     # arquivo novo, escrito OK
    OVERWRITTEN = "overwritten"             # tinha marker, sobrescrevemos
    SKIPPED_USER_FILE = "skipped_user_file" # tinha conteúdo sem marker — preservamos
    ERROR = "error"                         # falha de I/O


def _write_rule(target_path: Path, content: str) -> WriteOutcome:
    """Escreve ou skipa um arquivo .mdc seguindo a política de marker (spec §6.1).

    - Não existe → escreve (WRITTEN).
    - Existe + tem marker plugadvpl-rule-version → sobrescreve (OVERWRITTEN).
    - Existe + sem marker → skipa (SKIPPED_USER_FILE), preserva arquivo.
    - PermissionError/OSError → ERROR (caller decide se acumula warning).
    """
    try:
        if not target_path.exists():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")
            return WriteOutcome.WRITTEN
        existing = target_path.read_text(encoding="utf-8", errors="replace")
        if _MARKER_PREFIX in existing:
            target_path.write_text(content, encoding="utf-8")
            return WriteOutcome.OVERWRITTEN
        return WriteOutcome.SKIPPED_USER_FILE
    except OSError:
        return WriteOutcome.ERROR


def _skills_root() -> Path:
    """Localiza skills/ tanto em dev tree quanto em wheel.

    Tenta importlib.resources primeiro; se a skill embarcada não existir
    (caso: dev tree onde skills/ não é packaged), cai pro repo root
    relativo ao __init__.py do plugadvpl.
    """
    try:
        test = ir.files("plugadvpl") / "skills"
        with ir.as_file(test) as resolved:
            if (resolved / "arch" / "SKILL.md").exists():
                return resolved
    except (FileNotFoundError, OSError, ModuleNotFoundError):
        pass
    # Fallback dev tree: <repo>/cli/plugadvpl/__init__.py → <repo>/skills/
    import plugadvpl
    pkg_init = Path(plugadvpl.__file__).resolve()
    return pkg_init.parents[2] / "skills"


@dataclass(frozen=True)
class InstallResult:
    """Resumo do install_cursor_rules — quanto foi instalado + warnings."""

    installed_global: bool
    installed_local_count: int               # 0..52
    skipped_due_to_user_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """String curta pra `init` printar."""
        parts = []
        if self.installed_global:
            parts.append("1 global")
        if self.installed_local_count:
            parts.append(f"{self.installed_local_count} locais")
        return " + ".join(parts) + " instaladas" if parts else "nada instalado"


def install_cursor_rules(project_root: Path, version: str) -> InstallResult:
    """Orquestra detect + render + write pras rules Cursor.

    Spec §3.4. NUNCA propaga exception — top-level try captura tudo, init
    nunca quebra por causa do Cursor.
    """
    skipped: list[str] = []
    errors: list[str] = []
    installed_global = False
    installed_local_count = 0

    try:
        target = detect_cursor(project_root)
    except Exception as e:  # noqa: BLE001 — defensivo total
        errors.append(f"detect_cursor falhou: {e!r}")
        return InstallResult(
            installed_global=False,
            installed_local_count=0,
            skipped_due_to_user_files=[],
            errors=errors,
        )

    if target.install_global:
        try:
            global_path = Path.home() / ".cursor" / "rules" / "plugadvpl.mdc"
            outcome = _write_rule(global_path, render_global_rule(version))
            if outcome in (WriteOutcome.WRITTEN, WriteOutcome.OVERWRITTEN):
                installed_global = True
            elif outcome == WriteOutcome.SKIPPED_USER_FILE:
                skipped.append("plugadvpl.mdc (global)")
            elif outcome == WriteOutcome.ERROR:
                errors.append(
                    f"falha ao escrever {global_path}: permission/IO denied"
                )
        except Exception as e:  # noqa: BLE001
            errors.append(f"global rule erro: {e!r}")

    if target.install_local:
        local_dir = project_root / ".cursor" / "rules"
        skills_root = _skills_root()
        for skill_name, globs in _SKILL_GLOBS.items():
            try:
                skill_md_path = skills_root / skill_name / "SKILL.md"
                if not skill_md_path.exists():
                    errors.append(
                        f"skill {skill_name}: SKILL.md ausente no wheel"
                    )
                    continue
                content = render_skill_rule(skill_md_path, version, globs)
                target_path = local_dir / f"plugadvpl-{skill_name}.mdc"
                outcome = _write_rule(target_path, content)
                if outcome in (WriteOutcome.WRITTEN, WriteOutcome.OVERWRITTEN):
                    installed_local_count += 1
                elif outcome == WriteOutcome.SKIPPED_USER_FILE:
                    skipped.append(f"plugadvpl-{skill_name}.mdc")
                elif outcome == WriteOutcome.ERROR:
                    errors.append(
                        f"falha ao escrever {target_path}: permission/IO denied"
                    )
            except Exception as e:  # noqa: BLE001
                errors.append(f"skill {skill_name}: {e!r}")

    return InstallResult(
        installed_global=installed_global,
        installed_local_count=installed_local_count,
        skipped_due_to_user_files=skipped,
        errors=errors,
    )
