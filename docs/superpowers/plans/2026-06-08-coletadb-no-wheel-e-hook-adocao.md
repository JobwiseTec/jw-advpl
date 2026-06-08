# coletadb no wheel + hook de adoção — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Empacotar o `coletadb.tlpp` no wheel (comando `plugadvpl coletadb` + `init --coletadb`), fazer o SessionStart hook reforçar o uso do plugin toda sessão, e corrigir o version stamp do `coletadb.tlpp`.

**Architecture:** Três unidades independentes. (B) Um módulo novo `server_components.py` resolve o `.tlpp` empacotado (wheel) ou em dev tree (espelhando `_skills_root()`) e copia byte-a-byte; um comando Typer e uma flag em `init` o expõem; uma skill wrapper + entrada no catálogo o registram. (A) Uma mudança cirúrgica no `hooks/session-start.mjs` troca o `emit(null)` do ramo saudável por um lembrete imperativo, com opt-out via env var. (C) Um fix de 1 linha no header do `.tlpp`.

**Tech Stack:** Python 3.11+ / Typer / pytest / `importlib.resources`; hatchling (`force-include`); Node.js (hook `.mjs`).

**Spec:** [docs/superpowers/specs/2026-06-08-coletadb-no-wheel-e-hook-adocao-design.md](../specs/2026-06-08-coletadb-no-wheel-e-hook-adocao-design.md)

**Skills:** @superpowers:test-driven-development para cada unidade com lógica; @superpowers:verification-before-completion antes de fechar.

**Invariantes a respeitar (do projeto):**
- `coletadb.tlpp` é **LF + ASCII puro** (`.gitattributes: *.tlpp text eol=lf`) — extração **byte-a-byte** (`read_bytes`/`write_bytes`); nunca `read_text`/`write_text`.
- opt-in com default desligado = byte-idêntico (`init` puro inalterado).
- skill-por-comando (`scripts/validate_plugin.py` introspecta o Typer) — comando novo ⇒ skill nova + entrada em `_SKILL_GLOBS` + contagem 66→67.
- Sem nome de cliente em fixtures/output/commits/docs.
- Rodar a suíte sem mascarar exit code e sem `-p no:cov`; rodar ruff via `uv run` (CI tem ruff mais novo).

---

## Chunk 1: Parte B — empacotamento + módulo + comando + init + skill

### Task 1: Empacotar `coletadb.tlpp` no wheel (force-include)

**Files:**
- Modify: `cli/pyproject.toml` (bloco `[tool.hatch.build.targets.wheel]`, linha do `force-include`)

- [ ] **Step 1: Editar o `force-include`**

Em `cli/pyproject.toml`, localize a linha (≈76):

```toml
force-include = { "../skills" = "plugadvpl/skills" }
```

Troque por:

```toml
force-include = { "../skills" = "plugadvpl/skills", "../docs/reference-impl/coletadb.tlpp" = "plugadvpl/server_components/coletadb.tlpp" }
```

- [ ] **Step 2: Buildar o wheel e confirmar que o `.tlpp` entrou**

Run:
```bash
cd cli && uv build --wheel 2>&1 | tail -3
python -c "import zipfile,glob; z=zipfile.ZipFile(sorted(glob.glob('dist/plugadvpl-*.whl'))[-1]); print([n for n in z.namelist() if 'coletadb' in n])"
```
Expected: imprime `['plugadvpl/server_components/coletadb.tlpp']` (não vazio).

- [ ] **Step 3: Validar o build encadeado do RC (risco R1 do spec)**

Run:
```bash
cd cli && uv build 2>&1 | tail -5; echo "BUILD_EXIT=$?"
```
Expected: `BUILD_EXIT=0` (o `release-rc.yml` usa `uv build` encadeado; confirmar que o force-include do `../docs/...` não quebra wheel-from-sdist como o comentário do pyproject alerta).

**Remédio pré-decidido:** se quebrar, é o **mesmo modo de falha já aceito** do `../skills` (wheel-from-sdist não acha `../` dentro do sdist extraído). O wheel oficial é buildado por `uv build --wheel` direto do checkout (`release.yml`), não do sdist — então: se o `release-rc.yml` **já tolera** isso hoje com `../skills`, é não-issue (segue); se não, documentar a limitação exatamente como já está documentada pro `../skills` (comentário no `pyproject.toml`). **Não** inventar um caminho de build novo.

- [ ] **Step 4: Commit**

```bash
git add cli/pyproject.toml
git commit -m "build: force-include coletadb.tlpp no wheel (plugadvpl/server_components/)"
```

---

### Task 2: Módulo `server_components.py` (resolver + extrair)

**Files:**
- Create: `cli/plugadvpl/server_components.py`
- Test: `cli/tests/unit/test_server_components.py`

- [ ] **Step 1: Escrever os testes que falham**

Create `cli/tests/unit/test_server_components.py`:

```python
"""Unit tests p/ plugadvpl/server_components.py (extração do coletadb.tlpp)."""
from __future__ import annotations

from pathlib import Path

from plugadvpl import server_components as sc


def _source_bytes() -> bytes:
    return sc._coletadb_bytes()


def test_version_parses_from_define() -> None:
    data = b'... #DEFINE CDB_VERSION      "1.2.0"\n...'
    assert sc.coletadb_version(data) == "1.2.0"


def test_version_none_when_absent() -> None:
    assert sc.coletadb_version(b"sem define aqui") is None


def test_bundled_source_is_lf_ascii() -> None:
    data = _source_bytes()
    assert data.count(b"\r") == 0, "coletadb.tlpp deve ser LF (sem CR)"
    assert all(b <= 0x7F for b in data), "coletadb.tlpp deve ser ASCII puro"
    assert sc.coletadb_version(data) is not None


def test_extract_writes_byte_identical(tmp_path: Path) -> None:
    result = sc.extract_coletadb(tmp_path)
    assert result.status == "written"
    written = (tmp_path / "coletadb.tlpp").read_bytes()
    assert written == _source_bytes()  # byte-idêntico (NÃO comparar EOL specifico)


def test_extract_unchanged_second_run(tmp_path: Path) -> None:
    sc.extract_coletadb(tmp_path)
    result = sc.extract_coletadb(tmp_path)
    assert result.status == "unchanged"


def test_extract_version_mismatch_keeps_existing(tmp_path: Path) -> None:
    target = tmp_path / "coletadb.tlpp"
    target.write_bytes(b'#DEFINE CDB_VERSION "0.9.9"\n// versao velha do cliente')
    result = sc.extract_coletadb(tmp_path, force=False)
    assert result.status == "version_mismatch"
    assert result.version_existing == "0.9.9"
    assert target.read_bytes().startswith(b'#DEFINE CDB_VERSION "0.9.9"')  # intacto


def test_extract_force_overwrites(tmp_path: Path) -> None:
    target = tmp_path / "coletadb.tlpp"
    target.write_bytes(b'#DEFINE CDB_VERSION "0.9.9"\n')
    result = sc.extract_coletadb(tmp_path, force=True)
    assert result.status == "written"
    assert target.read_bytes() == _source_bytes()


def test_extract_creates_dest_dir(tmp_path: Path) -> None:
    dest = tmp_path / "novo" / "sub"
    result = sc.extract_coletadb(dest)
    assert result.status == "written"
    assert (dest / "coletadb.tlpp").exists()
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd cli && uv run pytest tests/unit/test_server_components.py -q`
Expected: FAIL com `ModuleNotFoundError: No module named 'plugadvpl.server_components'`.

- [ ] **Step 3: Implementar o módulo**

Create `cli/plugadvpl/server_components.py`:

```python
"""Extração de componentes-servidor empacotados (coletadb.tlpp).

O ``coletadb.tlpp`` é a fonte de verdade em ``docs/reference-impl/``; o wheel o
embarca via ``force-include`` em ``plugadvpl/server_components/``. Este módulo
resolve a fonte (wheel OU dev tree, espelhando ``_skills_root``) e copia
**byte-a-byte** pra um destino, detectando a versão pelo ``#DEFINE CDB_VERSION``.

A fonte é **LF + ASCII puro** (``.gitattributes``: ``*.tlpp text eol=lf``). A
cópia byte-a-byte preserva isso; **nunca** usar ``read_text``/``write_text`` no
``.tlpp`` (transcodificaria ou normalizaria EOL).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources as ir
from pathlib import Path

_COLETADB_NAME = "coletadb.tlpp"
_CDB_VERSION_RE = re.compile(rb'#DEFINE\s+CDB_VERSION\s+"([\d.]+)"', re.IGNORECASE)


@dataclass(frozen=True)
class ExtractResult:
    """Resultado de :func:`extract_coletadb`.

    status: ``"written"`` | ``"unchanged"`` | ``"version_mismatch"``.
    """

    status: str
    path: Path
    version_bundled: str | None
    version_existing: str | None


def _coletadb_bytes() -> bytes:
    """Bytes do ``coletadb.tlpp`` empacotado (wheel) ou em dev tree.

    Espelha ``_skills_root``: tenta ``importlib.resources`` (wheel:
    ``plugadvpl/server_components/coletadb.tlpp``); cai pro repo-root
    ``docs/reference-impl/coletadb.tlpp`` quando não empacotado (dev tree).
    """
    try:
        res = ir.files("plugadvpl") / "server_components" / _COLETADB_NAME
        return res.read_bytes()
    except (FileNotFoundError, OSError, ModuleNotFoundError):
        pass
    import plugadvpl  # noqa: PLC0415 -- lazy p/ evitar import circular

    pkg_init = Path(plugadvpl.__file__).resolve()
    dev = pkg_init.parents[2] / "docs" / "reference-impl" / _COLETADB_NAME
    return dev.read_bytes()


def coletadb_version(data: bytes) -> str | None:
    """Versão do bundle via ``#DEFINE CDB_VERSION`` (autoritativo, não o header)."""
    m = _CDB_VERSION_RE.search(data)
    return m.group(1).decode("ascii") if m else None


def extract_coletadb(dest_dir: Path, *, force: bool = False) -> ExtractResult:
    """Copia o ``coletadb.tlpp`` empacotado pra ``dest_dir`` (byte-a-byte).

    - não existe → escreve (``written``);
    - existe e bytes idênticos → no-op (``unchanged``);
    - existe e difere, sem ``force`` → não sobrescreve (``version_mismatch``);
    - ``force`` → sobrescreve (``written``).
    """
    data = _coletadb_bytes()
    ver_bundled = coletadb_version(data)
    target = dest_dir / _COLETADB_NAME

    if target.exists():
        existing = target.read_bytes()
        ver_existing = coletadb_version(existing)
        if existing == data:
            return ExtractResult("unchanged", target, ver_bundled, ver_existing)
        if not force:
            return ExtractResult("version_mismatch", target, ver_bundled, ver_existing)

    dest_dir.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return ExtractResult("written", target, ver_bundled, ver_bundled)
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `cd cli && uv run pytest tests/unit/test_server_components.py -q`
Expected: PASS (8 passed).

- [ ] **Step 5: Lint + types**

Run:
```bash
cd cli && uv run ruff check plugadvpl/server_components.py tests/unit/test_server_components.py && uv run ruff format plugadvpl/server_components.py tests/unit/test_server_components.py && uv run mypy plugadvpl/server_components.py
```
Expected: sem erros. (Se `ruff format` mudar algo, rerode os testes.)

- [ ] **Step 6: Commit**

```bash
git add cli/plugadvpl/server_components.py cli/tests/unit/test_server_components.py
git commit -m "feat(coletadb): modulo server_components — extrai coletadb.tlpp byte-a-byte"
```

---

### Task 3: Comando `plugadvpl coletadb` + skill + catálogo + contagens

> ⚠️ Adicionar o comando faz `validate_plugin.py` exigir a skill `skills/coletadb/`,
> e adicionar a skill quebra as 24 asserts `== 66` + o catálogo. Por isso **comando
> + skill + entrada no catálogo + bump das contagens** vão no MESMO task, e a
> verificação só roda no fim.

**Files:**
- Modify: `cli/plugadvpl/cli.py` (novo `@app.command()` `coletadb`)
- Create: `skills/coletadb/SKILL.md`
- Modify: `cli/plugadvpl/_skill_catalog.py` (entrada `"coletadb": []` + docstring)
- Modify: `cli/tests/unit/test_skill_catalog.py` (`== 66` → `67`)
- Modify: `cli/tests/integration/test_cli.py` (12× `== 66` → `67` + novos testes)
- Modify: `cli/tests/unit/test_gemini_skills.py` (7× `== 66` → `67`)
- Modify: `cli/tests/unit/test_copilot_instructions.py` (2× `== 66` → `67`)
- Modify: `cli/tests/unit/test_cursor_rules.py` (2× `== 66` → `67`)
- Modify: `README.md` (linhas ~624, ~911, ~950)

- [ ] **Step 1: Escrever os testes de integração que falham**

Em `cli/tests/integration/test_cli.py`, adicione (no fim do arquivo):

```python
def test_coletadb_command_writes_file(tmp_path: Path, runner: CliRunner) -> None:
    r = runner.invoke(app, ["--root", str(tmp_path), "coletadb"])
    assert r.exit_code == 0, r.stderr or r.stdout
    out = tmp_path / "coletadb.tlpp"
    assert out.exists()
    # byte-idêntico ao bundle + ASCII/LF
    data = out.read_bytes()
    assert data.count(b"\r") == 0
    assert "1.2.0" in (r.stdout + r.stderr)  # versão impressa


def test_coletadb_dest_option(tmp_path: Path, runner: CliRunner) -> None:
    dest = tmp_path / "fontes"
    dest.mkdir()
    r = runner.invoke(app, ["--root", str(tmp_path), "coletadb", "--dest", str(dest)])
    assert r.exit_code == 0, r.stderr or r.stdout
    assert (dest / "coletadb.tlpp").exists()


def test_coletadb_version_mismatch_needs_force(tmp_path: Path, runner: CliRunner) -> None:
    (tmp_path / "coletadb.tlpp").write_bytes(b'#DEFINE CDB_VERSION "0.9.9"\n')
    r = runner.invoke(app, ["--root", str(tmp_path), "coletadb"])
    assert r.exit_code == 1
    assert "--force" in (r.stderr + r.stdout)
    r2 = runner.invoke(app, ["--root", str(tmp_path), "coletadb", "--force"])
    assert r2.exit_code == 0, r2.stderr or r2.stdout
    assert b'CDB_VERSION      "1.2.0"' in (tmp_path / "coletadb.tlpp").read_bytes() \
        or b'1.2.0' in (tmp_path / "coletadb.tlpp").read_bytes()
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd cli && uv run pytest tests/integration/test_cli.py::test_coletadb_command_writes_file -q`
Expected: FAIL (comando `coletadb` não existe → exit≠0 / "No such command").

- [ ] **Step 3: Adicionar o comando `coletadb` em `cli.py`**

Em `cli/plugadvpl/cli.py`, após o comando `ingest_protheus_cmd` (≈linha 3110), adicione:

```python
@app.command()
def coletadb(
    ctx: typer.Context,
    dest: Annotated[
        Path | None,
        typer.Option("--dest", help="Pasta destino (default: raiz do projeto)."),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Sobrescreve se já existir versão diferente."),
    ] = False,
) -> None:
    """Extrai o ``COLETADB.tlpp`` (componente servidor) pra raiz do projeto.

    O ``coletadb.tlpp`` dumpa o dicionário SX no Protheus pro ``ingest-protheus``.
    A versão extraída casa com a versão do plugadvpl instalado.
    """
    from plugadvpl.server_components import extract_coletadb  # noqa: PLC0415

    root: Path = ctx.obj["root"]
    dest_dir = dest or root
    result = extract_coletadb(dest_dir, force=force)

    if result.status == "version_mismatch":
        typer.secho(
            f"⚠  Já existe {result.path} (v{result.version_existing}); "
            f"o bundle é v{result.version_bundled}. Use --force pra substituir.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(code=1)

    if ctx.obj["quiet"]:
        return
    if result.status == "unchanged":
        typer.echo(f"OK  {result.path} já está atualizado (v{result.version_bundled})")
    else:
        typer.echo(f"OK  coletadb.tlpp v{result.version_bundled} escrito em {result.path}")
    typer.echo("")
    typer.echo("Próximos passos (pra usar via REST com ingest-protheus):")
    typer.echo("  1. Copie o coletadb.tlpp pro RPO custom do AppServer")
    typer.echo("  2. Compile (TDS-VSCode ou `plugadvpl compile coletadb.tlpp`)")
    typer.echo("  3. Habilite [HTTPV11] + [HTTPURI] no appserver.ini")
    typer.echo("  Depois: `plugadvpl ingest-protheus --endpoint <url> --user U --password P`")
```

> `Path` e `Annotated` já estão importados no topo de `cli.py`.

- [ ] **Step 4: Criar a skill `skills/coletadb/SKILL.md`**

> O pin `uvx plugadvpl@0.30.1` deve bater com `.claude-plugin/plugin.json:version`
> ATUAL (0.30.1) pra `validate_plugin` passar; o `bump_marketplace_version.py`
> atualiza no release.

```markdown
---
description: Extrai o COLETADB.tlpp (componente servidor que dumpa o dicionario SX do Protheus) pra raiz do projeto, na versao casada com o plugin — pra compilar e usar com ingest-protheus
disable-model-invocation: true
arguments: [opcoes]
allowed-tools: [Bash]
---

# `/plugadvpl:coletadb`

Extrai o `coletadb.tlpp` **empacotado no plugin** (componente servidor) pra raiz
do projeto. A versao extraida **casa com a versao do plugadvpl instalado** — fim
do "peguei uma copia antiga em algum lugar".

O `coletadb.tlpp` roda no AppServer Protheus e dumpa o dicionario SX (SX1..SXG +
MPMENU/Schedules/Jobs) em CSVs, consumidos pelo `/plugadvpl:ingest-protheus` via
REST. Tambem tem UI (`U_COLETADB`) com opcao de salvar o bundle na estacao do
cliente (v1.1.0+).

## Uso

```
/plugadvpl:coletadb [--dest <pasta>] [--force]
```

- Sem argumento → extrai pra raiz do projeto.
- `--dest <pasta>` → extrai pra outra pasta da maquina.
- `--force` → sobrescreve se ja existir uma versao diferente.

## Execucao

```bash
uvx plugadvpl@0.30.1 coletadb $ARGUMENTS
```

## Depois de extrair

1. Copie o `coletadb.tlpp` pro RPO custom do AppServer.
2. Compile (TDS-VSCode ou `plugadvpl compile coletadb.tlpp`).
3. Habilite `[HTTPV11]` + `[HTTPURI]` no `appserver.ini`.
4. `plugadvpl ingest-protheus --endpoint <url> --user U --password P`.

## Relacionado

- Skill `ingest-protheus` — consome o dump SX via REST do COLETADB.
- Skill `ingest-sx` — caminho alternativo via CSV exportado do Configurador.
```

- [ ] **Step 5: Registrar no catálogo `_SKILL_GLOBS`**

Em `cli/plugadvpl/_skill_catalog.py`, no grupo "Meta-skills — sem escopo" (após `"ingest-protheus": [],` ≈linha 105), adicione:

```python
    "coletadb": [],
```

E corrija o docstring do módulo (linha ≈5): `65 skills` → `67 skills`.

- [ ] **Step 6: Bumpar todas as contagens 66 → 67**

Run (atualiza as 24 asserts + o catálogo de uma vez):
```bash
cd cli && for f in tests/integration/test_cli.py tests/unit/test_gemini_skills.py tests/unit/test_copilot_instructions.py tests/unit/test_cursor_rules.py tests/unit/test_skill_catalog.py; do
  python - "$f" <<'PY'
import sys, pathlib
p = pathlib.Path(sys.argv[1])
t = p.read_text(encoding="utf-8")
p.write_text(t.replace("== 66", "== 67"), encoding="utf-8")
print("patched", p, t.count("== 66"))
PY
done
```
Expected: cada arquivo imprime `patched ... 0` (zero `== 66` restantes).

- [ ] **Step 7: Atualizar as 3 contagens no `README.md`**

- Linha ~911: `66 skills (27 knowledge + 39 slash command wrappers)` → `67 skills (27 knowledge + 40 slash command wrappers)`. **(obrigatório)**
- Linha ~950: `Total: 66 skills.` → `Total: 67 skills.` **(obrigatório)**
- **Rot pré-existente (fora de escopo — NÃO mexer a menos que faça limpeza completa):** linha ~282 (`21 knowledge skills`) e linha ~624 (`33 command wrappers ... 1 por subcomando do CLI`) já estão defasadas/inconsistentes com o 27/39 usado acima, independente desta mudança. Se for tocar, alinhar com cuidado; senão, deixar. **Não** introduzir nova inconsistência.

Run (localizar): `grep -n "66 skills\|39 slash\|33 command wrappers\|21 knowledge\|Total: 66" README.md`

- [ ] **Step 8: Rodar suíte + validação + lint**

Run (sem mascarar exit, sem `-p no:cov`):
```bash
cd cli && uv run pytest > /tmp/pytest_coletadb.log 2>&1; echo "PYTEST_EXIT=$?"; tail -5 /tmp/pytest_coletadb.log
cd /d/IA/Projetos/plugadvpl && python scripts/validate_plugin.py; echo "VALIDATE_EXIT=$?"
cd cli && uv run ruff check plugadvpl/cli.py plugadvpl/_skill_catalog.py
```
Expected: `PYTEST_EXIT=0`; `VALIDATE_EXIT=0` ("All checks passed"); ruff sem erros.

- [ ] **Step 9: Commit**

```bash
git add cli/plugadvpl/cli.py skills/coletadb/SKILL.md cli/plugadvpl/_skill_catalog.py cli/tests README.md
git commit -m "feat(coletadb): comando 'plugadvpl coletadb' + skill /plugadvpl:coletadb"
```

---

### Task 4: Flag `init --coletadb`

**Files:**
- Modify: `cli/plugadvpl/cli.py` (assinatura de `init` + helper `_extract_coletadb_for_init`)
- Test: `cli/tests/integration/test_cli.py`

- [ ] **Step 1: Escrever os testes que falham**

Em `cli/tests/integration/test_cli.py`, adicione:

```python
def test_init_coletadb_flag_extracts(tmp_path: Path, runner: CliRunner) -> None:
    r = runner.invoke(app, ["--root", str(tmp_path), "init", "--coletadb"])
    assert r.exit_code == 0, r.stderr or r.stdout
    assert (tmp_path / "coletadb.tlpp").exists()


def test_init_without_flag_does_not_extract(tmp_path: Path, runner: CliRunner) -> None:
    r = runner.invoke(app, ["--root", str(tmp_path), "init"])
    assert r.exit_code == 0, r.stderr or r.stdout
    assert not (tmp_path / "coletadb.tlpp").exists()
```

- [ ] **Step 2: Rodar e confirmar que falha**

Run: `cd cli && uv run pytest tests/integration/test_cli.py::test_init_coletadb_flag_extracts -q`
Expected: FAIL ("No such option: --coletadb").

- [ ] **Step 3: Adicionar a flag + helper**

Em `cli/plugadvpl/cli.py`, na assinatura de `init` (após o param `no_codex`, ≈linha 629), adicione:

```python
    coletadb: Annotated[
        bool,
        typer.Option("--coletadb", help="Também extrai o coletadb.tlpp pra raiz do projeto."),
    ] = False,
```

No corpo de `init`, após `_install_codex_for_init(root, quiet)` (≈linha 673), adicione:

```python
    if coletadb:
        _extract_coletadb_for_init(root, quiet)
```

E crie o helper (próximo aos outros `_install_*_for_init`, ≈linha 766):

```python
def _extract_coletadb_for_init(root: Path, quiet: bool) -> None:
    """Helper de init() — extrai o coletadb.tlpp quando --coletadb é passado."""
    from plugadvpl.server_components import extract_coletadb  # noqa: PLC0415

    result = extract_coletadb(root, force=False)
    if quiet:
        return
    if result.status == "version_mismatch":
        typer.secho(
            f"⚠  coletadb.tlpp já existe (v{result.version_existing}) e difere do "
            f"bundle (v{result.version_bundled}); rode `plugadvpl coletadb --force`.",
            fg=typer.colors.YELLOW,
            err=True,
        )
    else:
        typer.echo(f"OK  coletadb.tlpp v{result.version_bundled} em {result.path}")
```

- [ ] **Step 4: Rodar e confirmar que passa**

Run: `cd cli && uv run pytest tests/integration/test_cli.py -k "init_coletadb or init_without_flag" -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Lint + commit**

```bash
cd cli && uv run ruff check plugadvpl/cli.py
git add cli/plugadvpl/cli.py cli/tests/integration/test_cli.py
git commit -m "feat(coletadb): flag 'plugadvpl init --coletadb'"
```

---

## Chunk 2: Parte A (hook) + Parte C (version stamp) + verificação final

### Task 5: SessionStart hook reforça toda sessão (Parte A)

**Files:**
- Modify: `hooks/session-start.mjs`
- Test: `hooks/session-start.test.mjs` (smoke, Node puro)

- [ ] **Step 1: Adicionar a constante + helper no hook**

Em `hooks/session-start.mjs`, no topo (após os outros `const` ≈linha 21), adicione:

```js
const HEALTHY_REMINDER =
  'Projeto Protheus com índice plugadvpl ativo neste diretório. Antes de Read/Grep em ' +
  '.prw/.tlpp/.prx, consulte o índice PRIMEIRO: `plugadvpl arch <arq>` (visão geral), ' +
  '`find <nome>`, `callers`/`callees`, `tables <T>`, `param <MV_>`, `lint`. Leia o fonte ' +
  'cru só depois de localizar a faixa de linhas exata (10-50× menos contexto). Use o ' +
  'plugadvpl para todo trabalho ADVPL/TLPP.';

function isHookQuiet() {
  const v = (process.env.PLUGADVPL_HOOK_QUIET || '').trim().toLowerCase();
  return v === '1' || v === 'true' || v === 'on' || v === 'sim' || v === 'yes';
}
```

- [ ] **Step 2: Trocar o `emit(null)` do ramo saudável**

No `main()`, no `else` final (DB existe, sem stale, sem drift, ≈linha 183):

```js
    } else {
      emit(null); // tudo OK — silent
    }
```

Troque por:

```js
    } else {
      // v0.31: índice saudável passa a reforçar o uso do plugin toda sessão
      // (antes ficava mudo). Opt-out via PLUGADVPL_HOOK_QUIET.
      emit(isHookQuiet() ? null : HEALTHY_REMINDER);
    }
```

- [ ] **Step 3: Exportar o que o teste precisa (sem mudar o runtime)**

No fim de `hooks/session-start.mjs`, mude:

```js
main();
```

para:

```js
// Permite import em teste sem executar o hook (que lê argv/stdin reais).
if (process.env.PLUGADVPL_HOOK_TEST !== '1') {
  main();
}
export { HEALTHY_REMINDER, isHookQuiet };
```

> Como `hooks.json` invoca o `.mjs` como script (não import), o `export` é inofensivo em runtime; o guard só evita rodar `main()` durante o teste.

- [ ] **Step 4: Escrever o smoke-test**

Create `hooks/session-start.test.mjs`:

```js
// Smoke-test Node puro (sem framework). Roda: node hooks/session-start.test.mjs
import assert from 'node:assert';

process.env.PLUGADVPL_HOOK_TEST = '1';
const { HEALTHY_REMINDER, isHookQuiet } = await import('./session-start.mjs');

// 1. O lembrete existe e cita a regra-chave.
assert.ok(HEALTHY_REMINDER.includes('plugadvpl arch'), 'lembrete deve citar arch');
assert.ok(HEALTHY_REMINDER.includes('Antes de Read'), 'lembrete deve ser imperativo');
assert.ok(HEALTHY_REMINDER.length < 700, 'lembrete deve ser curto');

// 2. Opt-out reconhece valores truthy.
for (const v of ['1', 'true', 'on', 'sim', 'YES']) {
  process.env.PLUGADVPL_HOOK_QUIET = v;
  assert.strictEqual(isHookQuiet(), true, `quiet deve reconhecer '${v}'`);
}
process.env.PLUGADVPL_HOOK_QUIET = '';
assert.strictEqual(isHookQuiet(), false, 'sem env → não-quiet');

console.log('session-start.test.mjs: OK');
```

- [ ] **Step 5: Rodar o smoke-test**

Run: `node hooks/session-start.test.mjs`
Expected: `session-start.test.mjs: OK` (exit 0).

- [ ] **Step 6: Confirmar que `validate_plugin` ainda passa (hook sem pin hardcoded)**

Run: `python scripts/validate_plugin.py; echo "EXIT=$?"`
Expected: `EXIT=0` (o `HEALTHY_REMINDER` não introduz `plugadvpl@\d` em chamada real).

- [ ] **Step 7: Commit**

```bash
git add hooks/session-start.mjs hooks/session-start.test.mjs
git commit -m "feat(hook): SessionStart reforca uso do plugin toda sessao (opt-out PLUGADVPL_HOOK_QUIET)"
```

---

### Task 6: Corrigir o version stamp do `coletadb.tlpp` (Parte C)

**Files:**
- Modify: `docs/reference-impl/coletadb.tlpp` (linha 17; opcional linha 21)

> O arquivo é **ASCII puro** — `Edit` normal é seguro (sem risco cp1252). NÃO
> deixar o editor converter LF→CRLF (o `.gitattributes` reforça `eol=lf`).

- [ ] **Step 1: Corrigir o `Versao:`**

Linha 17: `| Versao: 1.0.0` → `| Versao: 1.2.0` (manter o alinhamento da borda `|`).

- [ ] **Step 2 (opcional): Corrigir o encoding/EOL inexato do header**

Linha 21: `Encoding ANSI (Windows-1252), CRLF.` → `Encoding ASCII puro, LF.`
(ajustar o padding pra manter a borda `|`).

- [ ] **Step 3: Confirmar ASCII/LF + `CDB_VERSION` casa**

Run:
```bash
cd /d/IA/Projetos/plugadvpl && python -c "
b=open('docs/reference-impl/coletadb.tlpp','rb').read()
print('CR:', b.count(b'\r'), 'nonascii:', sum(1 for x in b if x>127))
print('alinhado:', b'Versao: 1.2.0' in b and b'CDB_VERSION      \"1.2.0\"' in b)
"
```
Expected: `CR: 0 nonascii: 0` e `alinhado: True`.

- [ ] **Step 4: Re-rodar o teste do extractor (a fonte mudou de bytes)**

Run: `cd cli && uv run pytest tests/unit/test_server_components.py tests/integration/test_cli.py -k coletadb -q`
Expected: PASS (os testes comparam contra a fonte atual).

- [ ] **Step 5: Commit**

```bash
git add docs/reference-impl/coletadb.tlpp
git commit -m "fix(coletadb): version stamp do header 1.0.0 -> 1.2.0 (alinha CDB_VERSION)"
```

---

### Task 7: Verificação final + docs

**Files:**
- Modify: `CHANGELOG.md` (entrada no topo da seção não-lançada)
- Modify: `README.md` (se houver seção que lista comandos/contagens a tocar)

- [ ] **Step 1: Suíte completa + tipos + lint + validação + build**

Run:
```bash
cd cli && uv run pytest > /tmp/pytest_final.log 2>&1; echo "PYTEST_EXIT=$?"; tail -8 /tmp/pytest_final.log
cd cli && uv run mypy plugadvpl/server_components.py plugadvpl/cli.py
cd cli && uv run ruff check plugadvpl/ tests/
cd /d/IA/Projetos/plugadvpl && python scripts/validate_plugin.py; echo "VALIDATE_EXIT=$?"
cd cli && uv build --wheel 2>&1 | tail -2
```
Expected: `PYTEST_EXIT=0`; mypy/ruff limpos; `VALIDATE_EXIT=0`; wheel buildou.

- [ ] **Step 2: CHANGELOG**

Adicione no topo da seção não-lançada do `CHANGELOG.md`:

```markdown
### Added
- `plugadvpl coletadb` (+ `init --coletadb`, skill `/plugadvpl:coletadb`): extrai o
  `coletadb.tlpp` **empacotado no plugin** (versão casada com o plugadvpl instalado)
  pra raiz do projeto — fim do drift de pegar uma cópia antiga em algum lugar.
- SessionStart hook agora **reforça o uso do plugin toda sessão** quando o índice
  está saudável (antes ficava silencioso). Opt-out: `PLUGADVPL_HOOK_QUIET=1`.

### Fixed
- `coletadb.tlpp`: version stamp do header `1.0.0` → `1.2.0` (alinha com `CDB_VERSION`).
```

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md README.md
git commit -m "docs: CHANGELOG + README p/ coletadb + hook de adocao"
```

- [ ] **Step 4: Verificação antes de fechar (@superpowers:verification-before-completion)**

Confirme, com evidência (cole a saída):
- `PYTEST_EXIT=0` (suíte verde, skill count 67).
- `VALIDATE_EXIT=0` (skill-por-comando + pin OK).
- `node hooks/session-start.test.mjs` → OK.
- wheel contém `plugadvpl/server_components/coletadb.tlpp`.
- `git status` limpo na branch `feat/coletadb-no-wheel-e-hook-adocao`.

---

## Notas de release (fora do escopo deste plano, pro maintainer)

A skill `/plugadvpl:coletadb` foi criada com pin `uvx plugadvpl@0.30.1`. No release
(branch `release/0.X.Y`), o `scripts/bump_marketplace_version.py` reescreve esse pin
junto com os demais. Seguir o fluxo de release padrão (bump → CHANGELOG date → README
"Evolução" → PR → tag anotada → release.yml). **Validar os DOIS caminhos de build**
(`release.yml` split + `release-rc.yml` encadeado) por causa do novo force-include.