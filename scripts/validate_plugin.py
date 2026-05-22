#!/usr/bin/env python3
"""Validador de plugadvpl plugin structure.

Atualizado em v0.9.5 (QA PERF 2026-05-18 #7): em vez de comparar
``skills/`` contra uma lista hardcoded, descobre os subcomandos via
introspeccao do Typer ``cli.app`` — assim qualquer comando novo entra
no escopo do CI automaticamente.

Tambem valida:

- Frontmatter YAML em todas as skills/agents.
- Pin de versao ``uvx plugadvpl@X.Y.Z`` bate com ``plugin.json:version``
  (skills modernas usam ``plugadvpl`` direto do PATH e nao precisam pin).
- ``marketplace.json:plugins[0].version`` bate com ``plugin.json:version``.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "cli"))

# Skills que NAO sao wrappers de subcomando Typer.
NON_COMMAND_SKILLS = {
    # Wrappers especiais (UX/onboarding).
    "help",
    "setup",
    # Skill de instrucao (como usar o indice).
    "plugadvpl-index-usage",
}

# Knowledge skills (conteudo ADVPL/TLPP, sem subcomando Typer correspondente).
# Validado pelo padrao do nome (prefixo ``advpl-``).
KNOWLEDGE_SKILL_PREFIX = "advpl-"

EXPECTED_AGENTS = {
    "advpl-analyzer",
    "advpl-impact-analyzer",
    "advpl-code-generator",
    "advpl-reviewer-bot",
}


def _read_plugin_version() -> str | None:
    p = ROOT / ".claude-plugin" / "plugin.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("version")
    except json.JSONDecodeError:
        return None


def _typer_command_names() -> tuple[set[str], list[str]]:
    """Retorna ``(command_names, errors)``. Lista comandos e grupos do Typer app.

    Em caso de falha de import (CLI incompleta), retorna set vazio + erro
    para que o CI nao fique cego silenciosamente.
    """
    try:
        from plugadvpl.cli import app  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - defensivo
        return set(), [f"falha ao importar plugadvpl.cli.app: {exc}"]

    names: set[str] = set()
    for ci in app.registered_commands:
        if ci.name:
            names.add(ci.name)
        elif ci.callback is not None:
            # Typer deriva o nome do command da funcao quando ``name`` e None.
            names.add(ci.callback.__name__.replace("_", "-"))
    for gi in app.registered_groups:
        if gi.name:
            names.add(gi.name)
        elif gi.typer_instance is not None:
            nm = getattr(gi.typer_instance.info, "name", None)
            if nm:
                names.add(nm)
    return names, []


def check_plugin_json() -> list[str]:
    errors = []
    p = ROOT / ".claude-plugin" / "plugin.json"
    if not p.exists():
        return [f"missing: {p}"]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"invalid JSON: {p}: {e}"]
    for field in ["name", "version", "description"]:
        if field not in data:
            errors.append(f"plugin.json missing field: {field}")
    if data.get("name") != "plugadvpl":
        errors.append(
            f"plugin.json: name must be 'plugadvpl', got '{data.get('name')}'"
        )
    return errors


def check_marketplace_json() -> list[str]:
    errors = []
    p = ROOT / ".claude-plugin" / "marketplace.json"
    if not p.exists():
        return [f"missing: {p}"]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"invalid JSON: {p}: {e}"]
    if "name" not in data or "owner" not in data or "plugins" not in data:
        errors.append(
            "marketplace.json missing required fields (name, owner, plugins)"
        )

    # v0.9.5 (QA PERF 2026-05-18 #7): marketplace version bate com plugin.json.
    plugin_version = _read_plugin_version()
    plugins = data.get("plugins") or []
    if plugin_version and plugins:
        mp_version = plugins[0].get("version")
        if mp_version and mp_version != plugin_version:
            errors.append(
                f"marketplace.json plugins[0].version={mp_version!r} != "
                f"plugin.json version={plugin_version!r}"
            )
    return errors


def check_skills() -> list[str]:
    """Valida cobertura skills × subcomandos Typer + pin de versao."""
    errors = []
    skills_dir = ROOT / "skills"
    found = {
        p.name
        for p in skills_dir.iterdir()
        if p.is_dir() and (p / "SKILL.md").exists()
    }

    typer_cmds, typer_errs = _typer_command_names()
    errors.extend(typer_errs)

    if typer_cmds:
        # Heuristica: alguns subcomandos do Typer nao precisam de skill wrapper
        # (ex: ``version`` e meta, nao expoe valor agentic).
        cmds_skipped_intentionally = {"version"}
        expected_cmd_skills = typer_cmds - cmds_skipped_intentionally
        missing_cmd = expected_cmd_skills - found
        if missing_cmd:
            errors.append(
                f"missing command skills (sem wrapper em skills/): {sorted(missing_cmd)}"
            )

    # Knowledge skills: tudo que comeca com ``advpl-`` + plugadvpl-index-usage.
    knowledge_found = {
        n for n in found
        if n.startswith(KNOWLEDGE_SKILL_PREFIX) or n in NON_COMMAND_SKILLS
    }
    if not any(n.startswith(KNOWLEDGE_SKILL_PREFIX) for n in knowledge_found):
        errors.append("skills/: nenhum skill ADVPL knowledge (advpl-*) encontrado")

    # Frontmatter check + version pin check
    plugin_version = _read_plugin_version()
    pin_re = re.compile(r"uvx\s+plugadvpl@(\S+)")

    for skill_dir in skills_dir.iterdir():
        if not skill_dir.is_dir():
            continue
        sf = skill_dir / "SKILL.md"
        if not sf.exists():
            continue
        content = sf.read_text(encoding="utf-8", errors="replace")
        if not content.startswith("---"):
            errors.append(f"{sf}: missing YAML frontmatter")
            continue
        if not re.search(r"^description:\s*(.+)$", content[:1000], re.MULTILINE):
            errors.append(f"{sf}: missing 'description' in frontmatter")

        # Version pin check — qualquer ``uvx plugadvpl@X.Y.Z`` deve bater com
        # plugin.json. Skills que usam ``plugadvpl`` direto (sem uvx) passam.
        if plugin_version:
            for m in pin_re.finditer(content):
                pinned = m.group(1)
                if pinned != plugin_version:
                    errors.append(
                        f"{sf}: uvx pin 'plugadvpl@{pinned}' != "
                        f"plugin.json version '{plugin_version}'"
                    )
                    break  # 1 erro por arquivo basta
    return errors


def check_agents() -> list[str]:
    errors = []
    agents_dir = ROOT / "agents"
    found = set()
    for p in agents_dir.iterdir():
        if p.suffix == ".md":
            found.add(p.stem)
    missing = EXPECTED_AGENTS - found
    if missing:
        errors.append(f"missing agents: {sorted(missing)}")
    # Frontmatter check
    for p in agents_dir.glob("*.md"):
        content = p.read_text(encoding="utf-8", errors="replace")
        if not content.startswith("---"):
            errors.append(f"{p}: missing YAML frontmatter")
            continue
        for field in ["name", "description"]:
            if not re.search(rf"^{field}:", content[:500], re.MULTILINE):
                errors.append(f"{p}: missing '{field}' in frontmatter")
    return errors


def check_hook() -> list[str]:
    errors = []
    p = ROOT / "hooks" / "hooks.json"
    if not p.exists():
        return [f"missing: {p}"]
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return [f"invalid JSON: {p}: {e}"]
    if "hooks" not in data:
        errors.append("hooks.json missing 'hooks' key")
    if "SessionStart" not in data.get("hooks", {}):
        errors.append("hooks.json missing SessionStart")
    # Check session-start.mjs exists
    mjs = ROOT / "hooks" / "session-start.mjs"
    if not mjs.exists():
        errors.append(f"missing: {mjs}")
    else:
        # v0.9.5 (QA PERF 2026-05-18 #7): hook nao deve ter pin de versao
        # antigo em CHAMADAS REAIS (string literal). v0.9.2 corrigiu pra
        # preferir PATH; rejeitar regressao do tipo argv ['plugadvpl@0.3.1'].
        # Filtra comentarios JS (linhas iniciando com //) pra evitar FP em
        # historico documentando o fix antigo.
        hook_content = mjs.read_text(encoding="utf-8", errors="replace")
        non_comment_lines = [
            ln for ln in hook_content.splitlines()
            if not ln.lstrip().startswith("//")
        ]
        non_comment = "\n".join(non_comment_lines)
        if re.search(r"['\"]plugadvpl@\d", non_comment):
            errors.append(
                f"{mjs}: hook tem pin de versao hardcoded em chamada real "
                "(regressao do fix v0.9.2 — deve preferir PATH binary)"
            )
    return errors


def main() -> int:
    print("plugadvpl plugin validation\n")
    all_errors = []
    for name, check in [
        ("plugin.json", check_plugin_json),
        ("marketplace.json", check_marketplace_json),
        ("skills/", check_skills),
        ("agents/", check_agents),
        ("hooks/", check_hook),
    ]:
        errs = check()
        if errs:
            print(f"[FAIL] {name}")
            for e in errs:
                print(f"   - {e}")
            all_errors.extend(errs)
        else:
            print(f"[OK] {name}")

    if all_errors:
        print(f"\n{len(all_errors)} errors found")
        return 1
    print("\nAll checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
