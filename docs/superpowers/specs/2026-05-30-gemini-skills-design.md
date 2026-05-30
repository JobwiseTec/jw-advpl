# Gemini CLI native skills no `plugadvpl init` — Fase 3 multi-agente

**Data:** 2026-05-30
**Versão alvo:** v0.16.4 (patch — adição compatível)
**Predecessor:** v0.16.3 entregou Copilot Instructions (Fase 2 multi-agente). Este spec completa Fase 3 focando em **Google Gemini CLI** via `GEMINI.md` + `.gemini/skills/<X>/SKILL.md`.
**Fora de escopo:** `~/.gemini/skills/` global skills, MCP integration, `@file.md` imports, `.geminiignore`.

---

## 1. Problema

Fases 1 (v0.16.2 Cursor) e 2 (v0.16.3 Copilot) entregaram integração nativa pra esses agentes. Gemini CLI tem mecanismo equivalente mas com layout e formato próprios:

- **Hierarchical context**: `~/.gemini/GEMINI.md` (global home) + `<project>/GEMINI.md` (workspace) + JIT scan por diretório
- **Skills estruturadas**: `.gemini/skills/<name>/SKILL.md` com YAML frontmatter (`name` + `description`)
- **`/memory` command** pra inspecionar contexto agregado

Sem integração nativa, dev usando Gemini CLI num projeto Protheus não tem contexto algum do plugadvpl — não sabe que existe índice consultável, encoding cp1252, ou quais comandos `uvx` rodar. Embora AGENTS.md (v0.16.1) seja lido por Codex, **Gemini CLI lê especificamente `GEMINI.md`** segundo sua documentação oficial — não cobre AGENTS.md.

**Objetivo:** com 1 `plugadvpl init`, dev Gemini tem cobertura equivalente ao dev Cursor/Copilot — convenções globais + 52 skills SKILL.md estruturadas.

---

## 2. Decisões de produto (fixadas no brainstorming)

| # | Decisão | Justificativa |
|---|---|---|
| 1 | **Multi-file** (global + 52 skills) | Paridade arquitetural com Cursor/Copilot. Gemini SKILL.md formato é virtualmente idêntico ao nosso (frontmatter `name` + `description`) — reuso máximo do `_skill_catalog.py`. |
| 2 | **Detection conservadora** (similar a Cursor) | `~/.gemini/` OU `gemini` no PATH (global); `.gemini/` no projeto OU sinal global (project). Evita pegada não-solicitada em projeto onde Gemini nunca foi usado. |
| 3 | **4º arquivo gêmeo `<project>/GEMINI.md`** | Junto com CLAUDE.md/AGENTS.md já existentes. Necessário porque Gemini não lê AGENTS.md por padrão; sem GEMINI.md, contexto plugadvpl não é carregado automaticamente. |
| 4 | **Sem `~/.gemini/skills/` global** | Apenas `~/.gemini/GEMINI.md` machine-wide. Skills locais (52) ficam por-projeto. |
| 5 | **Marker `<!-- plugadvpl-gemini-version: X.Y.Z -->`** | Distinto de `rule-version` (Cursor), `instructions-version` (Copilot), `fragment-version` (CLAUDE.md/AGENTS.md). Sem widening. |
| 6 | **Flag `--no-gemini`** | Mesmo padrão de `--no-cursor`/`--no-copilot`. |
| 7 | **`_SKILL_GLOBS` reusado pra lista canônica** | Mesmas 52 entradas. Valor (globs) é ignorado — Gemini não tem `applyTo`. Apenas chave (skill name) importa. |

---

## 3. Arquitetura

### 3.1 Adição mínima em `_skill_catalog.py`

Adiciona 1 constante nova:

```python
GEMINI_MARKER_PREFIX = "<!-- plugadvpl-gemini-version:"
```

Outros helpers (`_SKILL_GLOBS`, `_parse_skill_md`, `_transform_body`, `_skills_root`, `_write_managed_file`) reusados sem mudança.

### 3.2 Novo módulo `cli/plugadvpl/gemini_skills.py`

```python
"""Google Gemini CLI native skills generator + installer (v0.16.4+).

Detecta Gemini instalado (~/.gemini/ no home OU 'gemini' no PATH OU .gemini/
no projeto) e gera:
- ~/.gemini/GEMINI.md (global home — só se ~/.gemini/ existe)
- <project>/GEMINI.md (4º gêmeo CLAUDE.md + AGENTS.md + GEMINI.md)
- <project>/.gemini/skills/plugadvpl-<X>/SKILL.md (52 specifics)

Reusa _skill_catalog (DRY com cursor_rules + copilot_instructions).

Spec: docs/superpowers/specs/2026-05-30-gemini-skills-design.md
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from plugadvpl._skill_catalog import (
    GEMINI_MARKER_PREFIX,
    WriteOutcome,
    _SKILL_GLOBS,
    _parse_skill_md,
    _skills_root,
    _transform_body,
    _write_managed_file,
)


@dataclass(frozen=True)
class GeminiTarget:
    """Decisão do detect_gemini: o que instalar."""

    install_global: bool   # ~/.gemini/GEMINI.md
    install_project: bool  # <project>/GEMINI.md + .gemini/skills/plugadvpl-*/


def detect_gemini(project_root: Path) -> GeminiTarget:
    """Política conservadora — só age com sinal explícito de Gemini.

    Global se ``~/.gemini/`` existe OU ``shutil.which("gemini")`` retorna path.
    Project se ``<project_root>/.gemini/`` existe.

    Cross-platform via Path + shutil.which. RuntimeError em Path.home()
    (container minimalista) → no-op silencioso.
    """
    install_global = False
    install_project = False

    try:
        home = Path.home()
        if (home / ".gemini").exists():
            install_global = True
    except RuntimeError:
        return GeminiTarget(install_global=False, install_project=False)

    if not install_global and shutil.which("gemini") is not None:
        install_global = True

    if (project_root / ".gemini").exists():
        install_project = True

    return GeminiTarget(install_global=install_global, install_project=install_project)
```

### 3.3 `render_global_gemini_md(version)`

Gera conteúdo MD plano com marker no topo. Body adaptado do `_GLOBAL_BODY_TEMPLATE` de `copilot_instructions.py` (mesma estrutura, sem prefixo `Bash:` no formato Gemini — Gemini interpreta `uvx ...` como comando direto sugerido).

```python
_GLOBAL_BODY_TEMPLATE = """# Convenções TOTVS Protheus (ADVPL/TLPP) + plugadvpl

Este repositório contém código TOTVS Protheus em **AdvPL** (`.prw`, `.prx`,
`.apw`) e **TLPP** (`.tlpp`). Se `.plugadvpl/index.db` existe no root, use
o índice via `uvx plugadvpl@__VERSION__ <subcomando>` ANTES de ler `.prw`/`.tlpp`
cru — economiza ~16x tokens.

## Tabela de decisão — qual comando rodar antes de Read
[~30 linhas idênticas ao Copilot template]

## Encoding — CRÍTICO
[~15 linhas]

## Workflow padrão
[~15 linhas]

## Skills locais

Este projeto tem `.gemini/skills/plugadvpl-*/SKILL.md` com instruções
específicas por subcomando. Use `/memory show` pra ver todas carregadas.
"""


def render_global_gemini_md(version: str) -> str:
    """Gera conteúdo de GEMINI.md (global ou projeto-root).

    Markdown plano com marker plugadvpl-gemini-version no topo. ~80 linhas
    no body — Gemini concatena todos GEMINI.md hierárquicos, então enxutos
    funcionam melhor.
    """
    markers = f"<!-- plugadvpl-gemini-version: {version} -->\n\n"
    body = _GLOBAL_BODY_TEMPLATE.replace("__VERSION__", version)
    return markers + body
```

### 3.4 `render_skill_for_gemini(skill_md_path, version)`

Gera `SKILL.md` no formato Gemini (frontmatter simples: `name` + `description`).

```python
def render_skill_for_gemini(skill_md_path: Path, version: str) -> str:
    """Gera `.gemini/skills/plugadvpl-<X>/SKILL.md`.

    Frontmatter Gemini é mais simples que Cursor MDC: só `name` (único pra
    o catálogo de skills) + `description`. Sem `applyTo`/`globs`/`alwaysApply`
    (Gemini não tem esses conceitos — usa JIT scan + skill activation por
    descrição).

    Pipeline:
    1. Parse SKILL.md original (extrai description)
    2. _transform_body (slash→uvx + normalize)
    3. Frontmatter Gemini: name=plugadvpl-<X>, description=<da SKILL.md>
    4. Markers gemini-version + skill

    Edge case: SKILL.md sem frontmatter → description fallback.
    """
    skill_name = skill_md_path.parent.name
    raw = skill_md_path.read_text(encoding="utf-8")
    description, body = _parse_skill_md(raw)
    if not description:
        description = f"plugadvpl skill: {skill_name}"

    frontmatter = (
        "---\n"
        f"name: plugadvpl-{skill_name}\n"
        f"description: {description}\n"
        "---\n"
    )
    markers = (
        f"<!-- plugadvpl-gemini-version: {version} -->\n"
        f"<!-- plugadvpl-skill: {skill_name} -->\n\n"
    )
    return frontmatter + markers + _transform_body(body, version)
```

### 3.5 `InstallResult` + `install_gemini_skills`

```python
@dataclass(frozen=True)
class InstallResult:
    installed_global_home: bool   # ~/.gemini/GEMINI.md
    installed_project_md: bool     # <project>/GEMINI.md
    installed_skills_count: int    # 0..52
    skipped_due_to_user_files: list[str]
    errors: list[str]

    def summary(self) -> str:
        parts = []
        if self.installed_global_home:
            parts.append("1 home")
        if self.installed_project_md:
            parts.append("1 projeto")
        if self.installed_skills_count:
            parts.append(f"{self.installed_skills_count} skills")
        return (" + ".join(parts) + " instaladas") if parts else "nada instalado"


def install_gemini_skills(project_root: Path, version: str) -> InstallResult:
    """Orquestra detect + render + write pras GEMINI.md + skills.

    Spec §3.5 da Fase 3. NUNCA propaga exception — try/except em cada bloco,
    init nunca quebra por causa do Gemini.

    Helpers internos extraídos pra manter complexidade abaixo de PLR0912:
    - _install_gemini_global_home
    - _install_gemini_project_md
    - _install_one_gemini_skill
    """
    # delegação igual padrão Copilot (v0.16.3 reviewer fix)
    ...
```

Estrutura igual `install_copilot_instructions` — orquestrador + 3 helpers (`_install_gemini_global_home`, `_install_gemini_project_md`, `_install_one_gemini_skill`) pra manter PLR0912 ≤12 branches.

### 3.6 Integração com `init` em `cli.py`

Após bloco `if not no_copilot:`:

```python
if not no_gemini:
    from plugadvpl.gemini_skills import install_gemini_skills
    gemini_result = install_gemini_skills(root, __version__)
    if not ctx.obj["quiet"]:
        if (
            gemini_result.installed_global_home
            or gemini_result.installed_project_md
            or gemini_result.installed_skills_count
        ):
            typer.echo(f"OK  Gemini skills: {gemini_result.summary()}")
        for warn in gemini_result.errors:
            typer.secho(
                f"⚠  Gemini skills: {warn}", fg=typer.colors.YELLOW, err=True
            )
        for skipped in gemini_result.skipped_due_to_user_files:
            typer.secho(
                f"⚠  Gemini skills: {skipped} já existe sem marker plugadvpl — não sobrescrevi",
                fg=typer.colors.YELLOW,
                err=True,
            )
```

Nova flag `--no-gemini: bool = False` no signature.

### 3.7 Staleness em `_check_fragment_staleness`

Helper novo `_check_gemini_staleness(root) -> str | None` paralelo a `_check_cursor_rules_staleness` e `_check_copilot_instructions_staleness`. Chamado depois do Copilot.

```python
def _check_gemini_staleness(root: Path) -> str | None:
    """Detecta Gemini files desatualizados.

    Cobre ~/.gemini/GEMINI.md (global), <project>/GEMINI.md (projeto),
    e <project>/.gemini/skills/plugadvpl-*/SKILL.md (specifics).
    """
    gemini_files: list[Path] = []
    try:
        home_global = Path.home() / ".gemini" / "GEMINI.md"
        if home_global.exists():
            gemini_files.append(home_global)
    except RuntimeError:
        pass
    project_global = root / "GEMINI.md"
    if project_global.exists():
        gemini_files.append(project_global)
    skills_dir = root / ".gemini" / "skills"
    if skills_dir.exists():
        # Glob recursivo: .gemini/skills/plugadvpl-<X>/SKILL.md
        gemini_files.extend(sorted(skills_dir.glob("plugadvpl-*/SKILL.md")))

    marker_re = re.compile(
        r"<!--\s*plugadvpl-gemini-version:\s*(\d+\.\d+\.\d+[\w.+-]*)\s*-->"
    )
    for gf in gemini_files:
        try:
            content = gf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = marker_re.search(content)
        if m is None:
            continue
        v = m.group(1)
        if v != __version__:
            return f"{gf.name} foi gerado por plugadvpl {v}"
    return None
```

---

## 4. Formato dos arquivos gerados

### 4.1 `~/.gemini/GEMINI.md` (global home)

Markdown plano com marker. Conteúdo: convenções gerais ADVPL/TLPP.

```markdown
<!-- plugadvpl-gemini-version: 0.16.4 -->

# Convenções TOTVS Protheus (ADVPL/TLPP) + plugadvpl

[~80 linhas — convenções, tabela de decisão, encoding, workflow]
```

### 4.2 `<project>/GEMINI.md` (4º gêmeo)

Mesmo conteúdo do `~/.gemini/GEMINI.md`. Geração via mesma função `render_global_gemini_md(version)`. A duplicação é OK — Gemini concatena hierarquicamente e o template é curto.

### 4.3 `<project>/.gemini/skills/plugadvpl-arch/SKILL.md`

```markdown
---
name: plugadvpl-arch
description: Visao arquitetural de um arquivo ADVPL/TLPP (use ANTES de Read)
---
<!-- plugadvpl-gemini-version: 0.16.4 -->
<!-- plugadvpl-skill: arch -->

[body transformado: slash→uvx + version normalize]
```

**Diretório por skill:** `.gemini/skills/plugadvpl-<X>/SKILL.md` — Gemini espera um diretório por skill (não um arquivo flat). Loop cria a pasta antes de escrever o arquivo.

---

## 5. Erro handling

Mesma garantia spec §7 da Fase 1 e §5 da Fase 2:

- **Detection** RuntimeError em `Path.home()` → no-op silencioso
- **Escrita** PermissionError/OSError → warning em stderr, skip, continua
- **Parse SKILL.md** malformed → fallback description
- **Catch-all top-level** em `install_gemini_skills` → init nunca quebra

Exit code do `init` permanece 0 mesmo com falha total de Gemini.

---

## 6. Testes

**Unit tests** — `cli/tests/unit/test_gemini_skills.py` (novo):

| Teste | Cobre |
|---|---|
| `test_detect_no_signals_returns_false_false` | Sem `~/.gemini/`, sem `gemini` PATH, sem `.gemini/` projeto |
| `test_detect_home_gemini_dir_triggers_global` | `~/.gemini/` existe → global=True |
| `test_detect_project_gemini_dir_triggers_project` | `.gemini/` no projeto |
| `test_detect_both_signals_returns_both_true` | Ambos sinais |
| `test_detect_cursor_in_path_triggers_global` | `shutil.which("gemini")` |
| `test_detect_handles_runtime_error_in_home` | Path.home lança |
| `test_render_global_includes_version_marker` | Marker presente |
| `test_render_global_no_frontmatter` | Markdown plano |
| `test_render_global_substitutes_version` | `__VERSION__` substituído |
| `test_render_skill_includes_name` | `name: plugadvpl-arch` |
| `test_render_skill_includes_description` | Description do frontmatter SKILL.md |
| `test_render_skill_falls_back_when_no_frontmatter` | Description fallback |
| `test_render_skill_no_apply_to_field` | Gemini não tem applyTo — confirmar ausência |
| `test_render_skill_includes_skill_marker` | `<!-- plugadvpl-skill: arch -->` |
| `test_render_skill_transforms_body` | slash→uvx + normalize |
| `test_install_creates_all_three_layers` | Global home + project MD + 52 skills |
| `test_install_no_op_without_signals` | Zero efeito sem sinais |

**Integration tests** — em `cli/tests/integration/test_cli.py`:

`TestInitGeminiSkills`:
| Teste | Cobre |
|---|---|
| `test_skips_gemini_when_no_signals` | No-op silencioso |
| `test_installs_when_project_has_gemini_dir` | `.gemini/` → 52 specifics + project MD |
| `test_installs_global_home_when_home_has_gemini` | `~/.gemini/` mockado → home MD |
| `test_no_gemini_flag_skips_everything` | `--no-gemini` |
| `test_quiet_suppresses_message` | `--quiet` |
| `test_idempotent_does_not_duplicate` | 2 inits → marker count == 1 |
| `test_overwrites_with_old_marker` | 0.15.0 → versão atual |
| `test_preserves_user_file_without_marker` | User file preservado + warning |

`TestStatus` (estende com 3 testes):
| Teste | Cobre |
|---|---|
| `test_detects_stale_gemini_home` | `~/.gemini/GEMINI.md` stale |
| `test_detects_stale_gemini_project` | `<project>/GEMINI.md` stale |
| `test_detects_stale_gemini_skill` | `<project>/.gemini/skills/plugadvpl-arch/SKILL.md` stale |

**Total: ~28 testes novos.**

---

## 7. Tamanho e impacto

| Item | Estimativa |
|---|---|
| Adição em `_skill_catalog.py` | +3 linhas (GEMINI_MARKER_PREFIX) |
| Novo módulo `gemini_skills.py` | ~220 linhas |
| Modificações em `cli.py` (init + staleness helper) | +35 linhas |
| Testes novos | ~28 testes (~450 linhas) |

**Release alvo:** v0.16.4 (patch — adição compatível, zero breaking).

**Risco:** baixo. Pattern paralelo às Fases 1/2 já validado. Feature opt-out via `--no-gemini`. Silent fail garante zero regressão.

---

## 8. Critérios de sucesso

1. ✅ `plugadvpl init` em projeto com `~/.gemini/` e `.gemini/` cria home + project + 52 skills.
2. ✅ Init em projeto sem sinais de Gemini não toca em `.gemini/` nem cria `GEMINI.md` no root.
3. ✅ `plugadvpl status` reporta GEMINI.md ou skill desatualizada com nome + versão.
4. ✅ User file sem marker preservado com warning.
5. ✅ `init --no-gemini` é zero-op pra Gemini.
6. ✅ Erro de permissão não quebra init — exit code 0.
7. ✅ Suite full: 1123 → ~1151 (~+28).
8. ✅ Smoke manual: rodar `gemini` num projeto pós-init, verificar `/memory show` lista o GEMINI.md + skills do plugadvpl.

---

## 9. Out of scope

| Item | Por quê |
|---|---|
| `~/.gemini/skills/` global skills (machine-wide skills) | Adoção esperada baixa; user pode copiar manualmente se quiser |
| MCP server integration via `.gemini/extensions/` | Fora do escopo de "skills"; futura fase |
| `@file.md` imports em GEMINI.md (alternativa a multi-file) | Multi-file direto é mais robusto |
| `.geminiignore` configuração | Não nosso domínio (user decide o que esconder) |
| Migração de versões do Gemini CLI | Não nosso problema |
| `/memory reload` automation | User executa quando precisa |

---

## 10. Histórico

- 2026-05-30: design inicial. Brainstorm aprovou: multi-file scope, detection conservadora, 4º gêmeo no root, sem `~/.gemini/skills/` global, marker `gemini-version` distinto. Sucessor da Fase 2 (v0.16.3 Copilot).
