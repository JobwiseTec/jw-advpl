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
from typing import TYPE_CHECKING

from plugadvpl._skill_catalog import (
    _SKILL_GLOBS,
    INSTRUCTIONS_MARKER_PREFIX,
    WriteOutcome,
    _parse_skill_md,
    _skills_root,
    _transform_body,
    _write_managed_file,
)

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class CopilotTarget:
    """Decisão do detect_copilot: o que instalar."""

    install_global: bool  # .github/copilot-instructions.md
    install_local: bool  # .github/instructions/plugadvpl-*.instructions.md


def detect_copilot(project_root: Path) -> CopilotTarget:
    """Política simples: `.github/` no projeto → instala ambos.

    Menos conservador que detect_cursor — copilot-instructions.md é
    markdown inerte pra quem não usa Copilot (sem efeito colateral),
    e `.github/` é convenção amplamente adotada em projetos GitHub.
    """
    if (project_root / ".github").exists():
        return CopilotTarget(install_global=True, install_local=True)
    return CopilotTarget(install_global=False, install_local=False)


_GLOBAL_BODY_TEMPLATE = """# Convenções TOTVS Protheus (ADVPL/TLPP) + plugadvpl

Este repositório contém código TOTVS Protheus em **AdvPL** (`.prw`, `.prx`,
`.apw`) e **TLPP** (`.tlpp`). Se `.plugadvpl/index.db` existe no root, use
o índice via `uvx plugadvpl@__VERSION__ <subcomando>` ANTES de ler `.prw`/`.tlpp`
cru — economiza ~16x tokens.

## Tabela de decisão — qual comando rodar antes de Read

| Pergunta | Comando |
|---|---|
| "explique o fonte X" / "o que faz Y" | `uvx plugadvpl@__VERSION__ arch <arq>` |
| "onde está a função X?" | `uvx plugadvpl@__VERSION__ find <nome>` |
| "quem chama X?" | `uvx plugadvpl@__VERSION__ callers <funcao>` |
| "o que X chama?" | `uvx plugadvpl@__VERSION__ callees <funcao>` |
| "quem mexe na tabela SA1?" | `uvx plugadvpl@__VERSION__ tables SA1` |
| "onde MV_LOCALIZA é usado?" | `uvx plugadvpl@__VERSION__ param MV_LOCALIZA` |
| "achar 'RecLock' nos fontes" | `uvx plugadvpl@__VERSION__ grep RecLock` |
| "tem problemas no fonte X?" | `uvx plugadvpl@__VERSION__ lint <arq>` |

## Encoding — CRÍTICO

- `.prw`/`.prx` são **cp1252**. Read/Write/Edit comuns são UTF-8 — bytes acentuados viram `�`.
- Antes de editar `.prw`: `uvx plugadvpl@__VERSION__ edit-prw stage <arq>` (converte pra UTF-8 com backup).
- Depois de editar: `uvx plugadvpl@__VERSION__ edit-prw commit <arq>` (volta pra cp1252).
- `.tlpp` é UTF-8 nativo — sem stage/commit.

## Workflow padrão pra "explique o programa X"

1. `uvx plugadvpl@__VERSION__ find X` — descobre arquivo
2. `uvx plugadvpl@__VERSION__ arch <arq>` — visão arquitetural
3. `uvx plugadvpl@__VERSION__ callees X` — o que X chama
4. `uvx plugadvpl@__VERSION__ callers X` — quem chama X
5. Só depois, se necessário, leia o arquivo com offset/limit do `arch`

## Precisão — leia antes de concluir (pegadinhas que enganam o agente)

- **Resultado vazio nem sempre é "limpo".** `lint <arq>` vazio pode ser (a) código OK,
  (b) arquivo **não indexado** — o comando avisa *"não está no índice"* — ou (c) índice
  **desatualizado** após upgrade do plugadvpl. Se atualizou o plugin (ou na dúvida), rode
  `uvx plugadvpl@__VERSION__ ingest --no-incremental` ANTES de confiar em `lint`/`arch`: o
  `--incremental` (default) pula arquivos com mtime inalterado e **não** reaplica regras novas.
- **Listas grandes truncam no `table`/`md` (~20 linhas).** Para a lista COMPLETA (ex.: as
  ~128 props de `PoDynamicFormField`), use **`--format json`** (nunca trunca) ou **`--limit 0`
  ANTES do subcomando** (`uvx plugadvpl@__VERSION__ --limit 0 <cmd>`). `--limit` é flag
  global — **não** vai depois do subcomando.
- **Prefira `--format json`** quando for parsear o resultado: campos estáveis e `truncated`
  sinaliza corte.

## PO UI (Angular) + Protheus REST

| Pergunta | Comando |
|---|---|
| bindings `p-*` válidos de um componente | `uvx plugadvpl@__VERSION__ poui-componentes po-table` |
| propriedades/valores de uma interface de config | `uvx plugadvpl@__VERSION__ poui-componentes PoTableColumn` (+ `<prop>` filtra) |
| qual `ng generate @po-ui/...` usar | `uvx plugadvpl@__VERSION__ poui-componentes schematics` |
| front (HttpClient/`[p-service-api]`) ↔ rota REST do back | `uvx plugadvpl@__VERSION__ poui-bridge` |
| erros de PO UI gerado (binding/chave/valor/import/versão) | `uvx plugadvpl@__VERSION__ poui-lint` |

Antes de gerar Angular/PO UI, **consulte o catálogo** (`poui-componentes`) — não invente
binding/chave/valor; o `poui-lint` confirma. REST no Protheus: ver a skill `advpl-webservice`
(notation `@Get/@Post`, `oRest`) e `protheus-poui` (integração front↔back).
"""


def render_global_instructions(version: str) -> str:
    """Gera conteúdo de `.github/copilot-instructions.md` (global Copilot file).

    Markdown plano sem frontmatter (padrão Copilot). Marker de versão
    no topo. ~60 linhas no body — respeitando soft limit de ~2 páginas
    documentado pelo GitHub Copilot.
    """
    markers = f"<!-- plugadvpl-instructions-version: {version} -->\n\n"
    body = _GLOBAL_BODY_TEMPLATE.replace("__VERSION__", version)
    return markers + body


def render_skill_instructions(skill_md_path: Path, version: str, globs: list[str]) -> str:
    """Gera `.github/instructions/plugadvpl-<skill>.instructions.md`.

    Pipeline (similar a render_skill_rule do Cursor):
    1. Parse SKILL.md frontmatter (description)
    2. Body extraction
    3. _transform_body (slash→uvx + version normalize)
    4. Monta frontmatter Copilot:
       - applyTo (STRING com globs joined por vírgula; '**/*' se vazio)
       - description
    5. Markers de versão + skill

    Edge case: SKILL.md sem frontmatter → description fallback usa skill_name.
    """
    skill_name = skill_md_path.parent.name
    raw = skill_md_path.read_text(encoding="utf-8")
    description, body = _parse_skill_md(raw)
    if not description:
        description = f"plugadvpl skill: {skill_name}"

    # applyTo é STRING única no Copilot (Cursor usa array)
    apply_to = ",".join(globs) if globs else "**/*"

    frontmatter = f'---\napplyTo: "{apply_to}"\ndescription: {description}\n---\n'
    markers = (
        f"<!-- plugadvpl-instructions-version: {version} -->\n"
        f"<!-- plugadvpl-skill: {skill_name} -->\n\n"
    )
    return frontmatter + markers + _transform_body(body, version, style="plain")


@dataclass(frozen=True)
class InstallResult:
    """Resumo do install_copilot_instructions."""

    installed_global: bool
    installed_local_count: int  # 0..52
    skipped_due_to_user_files: list[str]
    errors: list[str]

    def summary(self) -> str:
        parts = []
        if self.installed_global:
            parts.append("1 global")
        if self.installed_local_count:
            parts.append(f"{self.installed_local_count} locais")
        return (" + ".join(parts) + " instaladas") if parts else "nada instalado"


def _install_global_instructions(
    project_root: Path, version: str
) -> tuple[bool, list[str], list[str]]:
    """Helper: install global .github/copilot-instructions.md.

    Returns (installed_bool, skipped_list, errors_list).
    """
    skipped: list[str] = []
    errors: list[str] = []
    try:
        global_path = project_root / ".github" / "copilot-instructions.md"
        outcome = _write_managed_file(
            global_path,
            render_global_instructions(version),
            INSTRUCTIONS_MARKER_PREFIX,
        )
        if outcome in (WriteOutcome.WRITTEN, WriteOutcome.OVERWRITTEN):
            return (True, skipped, errors)
        if outcome == WriteOutcome.SKIPPED_USER_FILE:
            skipped.append("copilot-instructions.md (global)")
        elif outcome == WriteOutcome.ERROR:
            errors.append(f"falha ao escrever {global_path}: permission/IO denied")
        return (False, skipped, errors)
    except Exception as e:
        errors.append(f"global instructions erro: {e!r}")
        return (False, skipped, errors)


def _install_one_skill(
    skill_name: str,
    globs: list[str],
    skills_root: Path,
    instructions_dir: Path,
    version: str,
) -> tuple[bool, list[str], list[str]]:
    """Helper: install one .github/instructions/plugadvpl-<X>.instructions.md.

    Returns (installed_bool, skipped_list, errors_list).
    """
    skipped: list[str] = []
    errors: list[str] = []
    try:
        skill_md_path = skills_root / skill_name / "SKILL.md"
        if not skill_md_path.exists():
            errors.append(f"skill {skill_name}: SKILL.md ausente")
            return (False, skipped, errors)
        content = render_skill_instructions(skill_md_path, version, globs)
        target_path = instructions_dir / f"plugadvpl-{skill_name}.instructions.md"
        outcome = _write_managed_file(target_path, content, INSTRUCTIONS_MARKER_PREFIX)
        if outcome in (WriteOutcome.WRITTEN, WriteOutcome.OVERWRITTEN):
            return (True, skipped, errors)
        if outcome == WriteOutcome.SKIPPED_USER_FILE:
            skipped.append(f"plugadvpl-{skill_name}.instructions.md")
        elif outcome == WriteOutcome.ERROR:
            errors.append(f"falha ao escrever {target_path}: permission/IO denied")
        return (False, skipped, errors)
    except Exception as e:
        errors.append(f"skill {skill_name}: {e!r}")
        return (False, skipped, errors)


def install_copilot_instructions(project_root: Path, version: str) -> InstallResult:
    """Orquestra detect + render + write pras instructions Copilot.

    Spec §3.3 da Fase 2. NUNCA propaga exception — try/except em cada bloco
    + helpers _install_global_instructions / _install_one_skill,
    init nunca quebra por causa do Copilot.
    """
    skipped: list[str] = []
    errors: list[str] = []
    installed_global = False
    installed_local_count = 0

    try:
        target = detect_copilot(project_root)
    except Exception as e:
        errors.append(f"detect_copilot falhou: {e!r}")
        return InstallResult(False, 0, [], errors)

    if target.install_global:
        ok, skp, err = _install_global_instructions(project_root, version)
        installed_global = ok
        skipped.extend(skp)
        errors.extend(err)

    if target.install_local:
        instructions_dir = project_root / ".github" / "instructions"
        try:
            skills_root = _skills_root()
        except Exception as e:
            errors.append(f"_skills_root falhou: {e!r}")
            return InstallResult(installed_global, installed_local_count, skipped, errors)

        for skill_name, globs in _SKILL_GLOBS.items():
            ok, skp, err = _install_one_skill(
                skill_name, globs, skills_root, instructions_dir, version
            )
            if ok:
                installed_local_count += 1
            skipped.extend(skp)
            errors.extend(err)

    return InstallResult(
        installed_global=installed_global,
        installed_local_count=installed_local_count,
        skipped_due_to_user_files=skipped,
        errors=errors,
    )
