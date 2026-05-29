# Copilot Instructions nativos no `plugadvpl init` — Fase 2 multi-agente

**Data:** 2026-05-29
**Versão alvo:** v0.16.3 (patch — adição compatível)
**Predecessor:** v0.16.2 entregou Cursor Rules nativos (Fase 1 multi-agente). Este spec completa Fase 2 focando em **GitHub Copilot** via `.github/copilot-instructions.md` + `.github/instructions/*.instructions.md`.
**Fora de escopo:** Gemini, OpenAI Codex específico, `excludeAgent` para gates code-review/cloud-agent.

---

## 1. Problema

A Fase 1 (v0.16.2) cobriu Cursor com 1 rule global em `~/.cursor/rules/` + 52 locais em `.cursor/rules/`. GitHub Copilot tem mecanismo equivalente mas com formato e localização diferentes:

- **Global**: `.github/copilot-instructions.md` na raiz do repo (markdown plano)
- **Specific**: `.github/instructions/<name>.instructions.md` com frontmatter `applyTo` (glob single-string)

Sem isso, dev usando Copilot num projeto Protheus não tem contexto algum do plugadvpl — não sabe que existe índice consultável, encoding cp1252, ou quais comandos `uvx` rodar.

**Objetivo:** com 1 `plugadvpl init`, dev Copilot tem cobertura equivalente ao dev Cursor — convenções globais + 52 instructions específicas por contexto.

---

## 2. Decisões de produto (fixadas no brainstorming)

| # | Decisão | Justificativa |
|---|---|---|
| 1 | **Multi-file** (global + 52 específicas) | Paridade arquitetural com Cursor; reuso máximo de código; `applyTo` é equivalente direto de `globs` MDC |
| 2 | **Refatorar pra `_skill_catalog.py` compartilhado** | DRY — `_SKILL_GLOBS`, `_parse_skill_md`, `_transform_body`, `_skills_root`, `WriteOutcome`, `_write_rule` viram neutros e reusados |
| 3 | **Detection: `.github/` existe** | Menos conservador que Cursor — `copilot-instructions.md` é markdown inerte pra quem não usa Copilot (sem efeito colateral) |
| 4 | **Flag `--no-copilot`** | Mesmo padrão do `--no-cursor` |
| 5 | **Marker `<!-- plugadvpl-instructions-version: X.Y.Z -->`** | Distinto do Cursor (`-rule-version-`) pra não confundir staleness check |

---

## 3. Arquitetura

### 3.1 Refactor: novo módulo `cli/plugadvpl/_skill_catalog.py`

Extrai do `cursor_rules.py` os componentes neutros (que servem qualquer agente):

```python
# _skill_catalog.py — fonte canônica de skills + helpers neutros multi-agente.

from __future__ import annotations
import enum
import re
from importlib import resources as ir
from pathlib import Path

_PRW = ["**/*.prw", "**/*.tlpp", "**/*.prx", "**/*.apw"]
_PRW_CSV = ["**/*.prw", "**/*.tlpp", "**/*.prx", "**/*.csv"]

_SKILL_GLOBS: dict[str, list[str]] = { ... 52 entradas ... }

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_DESC_RE = re.compile(r"^description:\s*(.+?)\s*$", re.MULTILINE)
_SLASH_RE = re.compile(r"/plugadvpl:([a-z0-9-]+)")
_UVX_VER_RE = re.compile(r"uvx plugadvpl@[\w.+-]+")
_MARKER_PREFIX = "<!-- plugadvpl-"  # mais geral — pega rule-version E instructions-version

def _parse_skill_md(skill_md_text: str) -> tuple[str, str]: ...
def _transform_body(body: str, version: str) -> str: ...
def _skills_root() -> Path: ...

class WriteOutcome(enum.Enum):
    WRITTEN = "written"
    OVERWRITTEN = "overwritten"
    SKIPPED_USER_FILE = "skipped_user_file"
    ERROR = "error"

def _write_managed_file(target_path: Path, content: str, marker_substring: str = _MARKER_PREFIX) -> WriteOutcome:
    """Mesmo policy do _write_rule, mas marker substring é parameter (default cobre ambos)."""
    ...
```

**Atenção:** `_MARKER_PREFIX` agora é mais amplo (`<!-- plugadvpl-`) pra detectar nossos arquivos tanto com `rule-version` (Cursor) quanto `instructions-version` (Copilot). O policy é o mesmo: arquivo com nosso marker → sobrescreve; sem → preserva.

### 3.2 `cli/plugadvpl/cursor_rules.py` — refactor mínimo

- Remove os helpers que foram pro `_skill_catalog`
- Importa: `from plugadvpl._skill_catalog import _SKILL_GLOBS, _parse_skill_md, _transform_body, _skills_root, WriteOutcome, _write_managed_file`
- Mantém: `CursorTarget`, `detect_cursor`, `render_global_rule`, `render_skill_rule` (MDC-specific), `_GLOBAL_DESCRIPTION`, `_GLOBAL_BODY_TEMPLATE`, `InstallResult`, `install_cursor_rules`
- Tests existentes em `test_cursor_rules.py` continuam passando (mesmo comportamento, só caminho do import muda — uns ajustam mock paths se referenciam `plugadvpl.cursor_rules.shutil.which`)

### 3.3 Novo módulo `cli/plugadvpl/copilot_instructions.py`

```python
"""GitHub Copilot Instructions generator/installer (v0.16.3+)."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

from plugadvpl._skill_catalog import (
    _SKILL_GLOBS, _parse_skill_md, _transform_body, _skills_root,
    WriteOutcome, _write_managed_file,
)


@dataclass(frozen=True)
class CopilotTarget:
    install_global: bool   # .github/copilot-instructions.md
    install_local: bool    # .github/instructions/plugadvpl-*.instructions.md


def detect_copilot(project_root: Path) -> CopilotTarget:
    """`.github/` existe → instala ambos."""
    if (project_root / ".github").exists():
        return CopilotTarget(True, True)
    return CopilotTarget(False, False)


_GLOBAL_BODY_TEMPLATE = """# Convenções TOTVS Protheus (ADVPL/TLPP) + plugadvpl

Este repositório contém código TOTVS Protheus em **AdvPL** (`.prw`, `.prx`,
`.apw`) e **TLPP** (`.tlpp`). Se `.plugadvpl/index.db` existe no root, use
o índice via `uvx plugadvpl@__VERSION__ <subcomando>` ANTES de ler `.prw`/`.tlpp`
cru — economiza ~16x tokens.

## Tabela de decisão
[~30 linhas — mesma da rule global Cursor, mas formato Markdown puro]

## Encoding cp1252 — CRÍTICO
[~15 linhas]

## Workflow padrão
[~15 linhas]
"""


def render_global_instructions(version: str) -> str:
    """Gera `.github/copilot-instructions.md` (≤2 páginas, repo-wide)."""
    markers = f"<!-- plugadvpl-instructions-version: {version} -->\n\n"
    body = _GLOBAL_BODY_TEMPLATE.replace("__VERSION__", version)
    return markers + body


def render_skill_instructions(
    skill_md_path: Path, version: str, globs: list[str]
) -> str:
    """Gera `.github/instructions/plugadvpl-<skill>.instructions.md` com `applyTo`.

    Pipeline:
    1. Parse SKILL.md frontmatter (extrai description)
    2. Extrai body
    3. Aplica _transform_body (slash→uvx + normalize)
    4. Monta frontmatter Copilot: applyTo (string join), description
    5. Adiciona markers de versão + skill

    Edge case: SKILL.md sem frontmatter → description fallback.
    """
    skill_name = skill_md_path.parent.name
    raw = skill_md_path.read_text(encoding="utf-8")
    description, body = _parse_skill_md(raw)
    if not description:
        description = f"plugadvpl skill: {skill_name}"

    # applyTo é STRING ÚNICA no Copilot (Cursor usa array)
    apply_to = ",".join(globs) if globs else "**/*"

    frontmatter = (
        "---\n"
        f'applyTo: "{apply_to}"\n'
        f"description: {description}\n"
        "---\n"
    )
    markers = (
        f"<!-- plugadvpl-instructions-version: {version} -->\n"
        f"<!-- plugadvpl-skill: {skill_name} -->\n\n"
    )
    return frontmatter + markers + _transform_body(body, version)


@dataclass(frozen=True)
class InstallResult:
    installed_global: bool
    installed_local_count: int  # 0..52
    skipped_due_to_user_files: list[str]
    errors: list[str]
    def summary(self) -> str: ...


def install_copilot_instructions(project_root: Path, version: str) -> InstallResult:
    """Orquestra detect + render + write. NUNCA propaga exception (spec §5)."""
    ...
```

### 3.4 Integração com `init` em `cli/plugadvpl/cli.py`

Após a chamada de `install_cursor_rules`, adicionar:

```python
if not no_copilot:
    from plugadvpl.copilot_instructions import install_copilot_instructions
    copilot_result = install_copilot_instructions(root, __version__)
    if not ctx.obj["quiet"]:
        if copilot_result.installed_global or copilot_result.installed_local_count:
            typer.echo(f"OK  Copilot instructions: {copilot_result.summary()}")
        for warn in copilot_result.errors:
            typer.secho(f"⚠  Copilot instructions: {warn}", fg=typer.colors.YELLOW, err=True)
        for skipped in copilot_result.skipped_due_to_user_files:
            typer.secho(
                f"⚠  Copilot instructions: {skipped} já existe sem marker plugadvpl — não sobrescrevi",
                fg=typer.colors.YELLOW, err=True,
            )
```

Nova flag `--no-copilot: bool = False` no signature do `init`.

### 3.5 Staleness em `_check_fragment_staleness`

Estende com 3ª passada (após Cursor):

```python
# 3. Copilot instructions (instructions-version)
copilot_files: list[Path] = []
global_copilot = root / ".github" / "copilot-instructions.md"
if global_copilot.exists():
    copilot_files.append(global_copilot)
copilot_dir = root / ".github" / "instructions"
if copilot_dir.exists():
    copilot_files.extend(sorted(copilot_dir.glob("plugadvpl-*.instructions.md")))

inst_marker_re = re.compile(
    r"<!--\s*plugadvpl-instructions-version:\s*(\d+\.\d+\.\d+[\w.+-]*)\s*-->"
)
for cf in copilot_files:
    try:
        content = cf.read_text(encoding="utf-8", errors="replace")
    except OSError:
        continue
    m = inst_marker_re.search(content)
    if m is None:
        continue
    inst_version = m.group(1)
    if inst_version != __version__:
        return f"{cf.name} foi gerado por plugadvpl {inst_version}"
```

---

## 4. Formato dos arquivos gerados

### 4.1 Global — `.github/copilot-instructions.md`

```markdown
<!-- plugadvpl-instructions-version: 0.16.3 -->

# Convenções TOTVS Protheus (ADVPL/TLPP) + plugadvpl

Este repositório contém código TOTVS Protheus em **AdvPL** (`.prw`, `.prx`,
`.apw`) e **TLPP** (`.tlpp`). Se `.plugadvpl/index.db` existe no root, use
o índice via `uvx plugadvpl@0.16.3 <subcomando>` ANTES de ler `.prw`/`.tlpp`
cru — economiza ~16x tokens.

[corpo conciso ~60-80 linhas: tabela de decisão + encoding + workflow]
```

Sem frontmatter — markdown plano (padrão `copilot-instructions.md`).

### 4.2 Specific — `.github/instructions/plugadvpl-arch.instructions.md`

```markdown
---
applyTo: "**/*.prw,**/*.tlpp,**/*.prx,**/*.apw"
description: Visao arquitetural de um arquivo ADVPL/TLPP (use ANTES de Read)
---
<!-- plugadvpl-instructions-version: 0.16.3 -->
<!-- plugadvpl-skill: arch -->

[body transformado: slash→uvx, mesmo pipeline da Fase 1]
```

**Diferenças vs Cursor MDC:**
- `applyTo` é **string única** com vírgulas (Cursor `globs` é array YAML)
- Sem `alwaysApply` (não existe no Copilot)
- Quando `_SKILL_GLOBS[name]` é vazio → `applyTo: "**/*"` (meta-skills aplicam sempre)

---

## 5. Erro handling

Mesma garantia spec §7 da Fase 1:

- **Detection** RuntimeError → no-op silencioso
- **Escrita** PermissionError/OSError → warning em stderr, skip, continua
- **Parse SKILL.md** malformed → fallback description
- **Catch-all top-level** em `install_copilot_instructions` → init nunca quebra

Exit code do `init` permanece 0 mesmo com falha total de Copilot.

---

## 6. Testes

**Unit tests** — `cli/tests/unit/test_copilot_instructions.py` (novo):

| Teste | Cobre |
|---|---|
| `test_detect_no_github_returns_false_false` | Sem `.github/` → no-op |
| `test_detect_with_github_returns_both_true` | `.github/` existe → ambos |
| `test_render_global_includes_version_marker` | Marker presente |
| `test_render_global_has_no_frontmatter` | Markdown plano, sem `---` |
| `test_render_skill_includes_apply_to_string` | `applyTo: "..."` |
| `test_render_skill_applyto_is_string_not_array` | Confirma string (não YAML list) |
| `test_render_skill_empty_globs_uses_wildcard` | `applyTo: "**/*"` quando globs vazios |
| `test_render_skill_includes_skill_marker` | `<!-- plugadvpl-skill: arch -->` |
| `test_render_skill_falls_back_no_frontmatter` | Description fallback |
| `test_install_creates_global_and_locals` | Smoke end-to-end |
| `test_install_no_op_without_github` | Sem `.github/` → zero |

**Unit tests** — `cli/tests/unit/test_skill_catalog.py` (novo após refactor):

| Teste | Cobre |
|---|---|
| `test_skill_globs_has_52_entries` | Constante preservada |
| `test_skill_globs_matches_actual_skills_dir` | Paridade (movido de test_cursor_rules.py) |
| `test_parse_skill_md_extracts_description` | Movido de test_cursor_rules.py |
| `test_parse_skill_md_fallback_when_no_frontmatter` | Movido |
| `test_transform_body_substitutes_slash` | Movido |
| `test_transform_body_normalizes_version` | Movido |
| `test_write_managed_file_writes_new` | Movido (era test_write_rule) |
| `test_write_managed_file_overwrites_with_marker` | Movido |
| `test_write_managed_file_skips_user_file` | Movido |

**Integration tests** — adicionar em `cli/tests/integration/test_cli.py`:

`TestInitCopilotInstructions` (classe nova):
| Teste | Cobre |
|---|---|
| `test_skips_copilot_when_no_github` | Sem `.github/` → zero |
| `test_installs_when_project_has_github` | `.github/` existe → 1+52 criados |
| `test_no_copilot_flag_skips_everything` | `--no-copilot` desabilita |
| `test_idempotent_does_not_duplicate` | 2 inits → mesmo conteúdo |
| `test_overwrites_with_old_marker` | Old marker → regen |
| `test_preserves_user_file_without_marker` | User file preservado |

`TestStatus` (estende com 2 testes):
| Teste | Cobre |
|---|---|
| `test_detects_stale_copilot_global` | Stale `copilot-instructions.md` |
| `test_detects_stale_copilot_local` | Stale `.github/instructions/plugadvpl-arch.instructions.md` |

**Total novo: ~28 testes.** Existentes preservados.

---

## 7. Tamanho e impacto

| Item | Estimativa |
|---|---|
| Novo módulo `_skill_catalog.py` | ~150 linhas (extraído de cursor_rules) |
| Novo módulo `copilot_instructions.py` | ~200 linhas |
| Refactor `cursor_rules.py` | ~150 linhas removidas (helpers movidos) |
| Modificações em `cli.py` | +5 linhas (flag + chamada) + ~25 (staleness) |
| Testes novos | ~28 testes (~500 linhas) |
| Testes movidos (cursor → catalog) | ~9 testes movidos |

**Release alvo:** v0.16.3 (patch — adição compatível, zero breaking).

**Risco:** baixo. Refactor é internal (test re-paths simples). Feature opt-out via `--no-copilot`. Silent fail garante zero regressão.

---

## 8. Critérios de sucesso

1. ✅ `plugadvpl init` em projeto com `.github/` cria global + 52 locais Copilot sem prompt.
2. ✅ Init em projeto sem `.github/` não toca em `.github/`.
3. ✅ `plugadvpl status` reporta Copilot instruction desatualizada.
4. ✅ User file sem marker preservado com warning.
5. ✅ `init --no-copilot` é zero-op pra Copilot (Cursor continua funcionando).
6. ✅ Refactor neutral: testes Cursor da Fase 1 (32 tests) continuam passando.
7. ✅ Suite full: 1097 → ~1125 (~+28 testes líquido após movidos).
8. ✅ Smoke manual no GitHub: abrir PR num repo com `.github/copilot-instructions.md` gerado, verificar que Copilot considera contexto ADVPL.

---

## 9. Out of scope

| Item | Por quê | Quando |
|---|---|---|
| Gemini CLI | Mecanismo próprio (`GEMINI.md` ou similar) | Fase 3 futura |
| OpenAI Codex personalização | Já coberto via AGENTS.md (v0.16.1) | — |
| `excludeAgent` gates (code-review/cloud-agent) | Recursos avançados de path-specific | Versão futura |
| Sincronização bi-direcional `.instructions.md` → SKILL.md | Owner do conteúdo é Claude side | — |
| Auto-detection de Copilot Pro/Business | Não há sinal claro local | — |
| Validação de tamanho ≤2 páginas no global | Soft hint Copilot, não enforced | Mantemos conciso por convenção |

---

## 10. Histórico

- 2026-05-29: design inicial. Brainstorm aprovou: multi-file scope, refactor `_skill_catalog`, detection via `.github/`, marker `-instructions-version`. Sucessor da Fase 1 (v0.16.2 Cursor).
