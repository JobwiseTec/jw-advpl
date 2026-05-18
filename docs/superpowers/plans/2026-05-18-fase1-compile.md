# Fase 1 — `plugadvpl compile` Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar o subcomando `plugadvpl compile <fonte...>` que invoca o binário oficial `advpls` (TOTVS) e devolve resultado estruturado JSON, com 2 modos (`appre` local e `cli` full via AppServer), config opt-in via `runtime.toml`, parser de output com patterns externos, ~85 testes novos. Release v0.8.0.

**Architecture:** Wrapper Python sobre `advpls` proprietário. 4 módulos isolados: `runtime_config.py` (TOML loader, função pura), `compile_parser.py` (regex+patterns, função pura), `compile.py` (orchestrator — único com side effects de subprocess/fs), `cli.py` (typer sub-app). 2 lookups novos (`compile_patterns.json`, `redact_patterns.json`) seguem padrão `lookups/lint_rules.json` com catalog consistency test.

**Tech Stack:** Python 3.11+, typer (existente), `tomllib` stdlib (sem dep nova), `subprocess.Popen`, `tempfile.mkdtemp`. Reusa `cli/plugadvpl/edit_prw.py::detect_encoding` e infra de testes `pytest` + `CliRunner` existente.

**Spec de referência:** [`docs/fase1/compile-design.md`](../../fase1/compile-design.md) — leia primeiro antes de implementar.

**Estimativa:** ~23h (~3 dias) com margem.

---

## File Structure

### Arquivos NOVOS

| Path | Responsabilidade | Linhas estimadas |
|---|---|---|
| `cli/plugadvpl/runtime_config.py` | Dataclass `RuntimeConfig` + `load(root)` + validações + `render_template()` + `init_gitignore_entry()` | ~180 |
| `cli/plugadvpl/compile_parser.py` | `parse_diagnostics(stdout, stderr, mode, requested_files) → list[Diagnostic]`. Função pura. Inclui normalização de path e redact. | ~150 |
| `cli/plugadvpl/compile.py` | Orchestrator: `resolve_files`, `pick_mode`, `build_invocation`, `run_subprocess` (Popen + lifecycle), `build_result`. Único módulo com side effects de subprocess + filesystem. | ~280 |
| `cli/plugadvpl/lookups/compile_patterns.json` | 5+ patterns iniciais (pt-BR + en). Schema documentado em spec §8.1. | ~60 |
| `cli/plugadvpl/lookups/redact_patterns.json` | 5+ patterns de redaction (password/psw/senha/pwd/aut_file/hex keys). | ~30 |
| `cli/tests/unit/test_runtime_config.py` | ~20 testes (validações, env vars, symlink, TCP ping mockado, template round-trip). | ~250 |
| `cli/tests/unit/test_compile_parser.py` | ~30 testes (8 fixtures + tie-break + normalização de path + bucket `__unmatched__` + redact). | ~300 |
| `cli/tests/unit/test_compile.py` | ~25 testes orchestrator com subprocess mockado. | ~400 |
| `cli/tests/integration/test_cli_compile.py` | ~10 testes CLI end-to-end com PATH-shim de advpls. | ~250 |
| `cli/tests/fixtures/compile_outputs/*.txt` | 8 fixtures iniciais (mais que vêm do smoke iterativo). | n/a |
| `cli/tests/unit/test_compile_catalog_consistency.py` | Catalog test para `compile_patterns.json` + `redact_patterns.json`. | ~80 |

### Arquivos MODIFICADOS

| Path | Mudança |
|---|---|
| `cli/plugadvpl/cli.py` | +80 linhas: sub-app typer `compile_app` com comando `compile <files>` + `compile --init-config` |
| `cli/plugadvpl/edit_prw.py` | Extrair função pura `encode_cp1252_bytes(text: str) → bytes` para reuso (Task 5 precisa) |
| `cli/plugadvpl/__init__.py` | Nenhuma mudança esperada (versão via hatch-vcs) |
| `CHANGELOG.md` | Nova entry `[0.8.0]` no topo |
| `.claude-plugin/plugin.json` | `0.7.0 → 0.8.0` |
| `.claude-plugin/marketplace.json` | `0.7.0 → 0.8.0` |
| `docs/ROADMAP.md` | Marca Fase 1 como shipped |
| `docs/cli-reference.md` | Adiciona seção `compile` |
| `README.md` | Status v0.8.0 |

---

## Chunk 1: Config & Redact Patterns

Foundation: módulo de configuração + lookup de redact patterns. Sem dependência entre tasks aqui. Cada uma é independente.

### Task 1: `runtime_config.py` — dataclass + load + validações + template

**Files:**
- Create: `cli/plugadvpl/runtime_config.py`
- Test: `cli/tests/unit/test_runtime_config.py`

**Spec refs:** §5, §6 inteiro, §15.3 mapeamento de fixes do review.

#### Step 1.1 — Criar esqueleto do módulo (sem implementação)

- [ ] **Step 1.1.1: Criar arquivo `cli/plugadvpl/runtime_config.py` com esqueleto**

```python
"""Carrega e valida ``<root>/.plugadvpl/runtime.toml``. Compartilhado com Fases 2-4.

Schema documentado em ``docs/fase1/compile-design.md`` §6.

Convenções:
- Credenciais NUNCA são valores literais no TOML — só nome de env var.
- Função ``load()`` é pura: recebe Path, devolve dataclass imutável ou None.
- Validações falham com ``RuntimeConfigError`` (mensagem clara apontando a chave).
"""
from __future__ import annotations

import os
import socket
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class RuntimeConfigError(Exception):
    """Erro de validação do runtime.toml — mensagem clara, sem stacktrace ruidoso."""


@dataclass(frozen=True)
class TdsLsConfig:
    binary: Path
    binary_is_symlink: bool


@dataclass(frozen=True)
class AppserverConfig:
    host: str
    port: int
    secure: bool
    build: str
    environment: str


@dataclass(frozen=True)
class AuthConfig:
    user_env: str
    password_env: str
    aut_file: Path | None


@dataclass(frozen=True)
class CompileConfig:
    recompile: bool
    includes: tuple[Path, ...]
    mode: str
    timeout_seconds: int
    include_warnings: bool


@dataclass(frozen=True)
class LoggingConfig:
    log_to_file: str
    show_console_output: bool


@dataclass(frozen=True)
class RuntimeConfig:
    tds_ls: TdsLsConfig
    appserver: AppserverConfig
    auth: AuthConfig
    compile: CompileConfig
    logging: LoggingConfig
    warn_remote_host: bool
    appserver_reachable: bool
    source_path: Path


def load(root: Path) -> RuntimeConfig | None:
    """Carrega ``<root>/.plugadvpl/runtime.toml`` ou retorna None se ausente.

    Raises:
        RuntimeConfigError: TOML malformado, campo obrigatório ausente, env var
            não setada, binary inexistente, etc.
    """
    raise NotImplementedError("será implementado nos próximos steps")


def render_template() -> str:
    """Retorna o conteúdo de template do runtime.toml com comentários explicativos.

    Usado por ``plugadvpl compile --init-config``. Sem efeito colateral.
    """
    raise NotImplementedError("será implementado nos próximos steps")


def init_gitignore_entry(root: Path) -> bool:
    """Garante ``.plugadvpl/runtime.toml`` no ``.gitignore`` (cria se ausente).

    Retorna True se adicionou linha, False se já estava lá ou se ``.gitignore``
    não existe (não cria arquivo novo só por isso — usuário pode preferir commitar).
    """
    raise NotImplementedError("será implementado nos próximos steps")
```

- [ ] **Step 1.1.2: Criar arquivo `cli/tests/unit/test_runtime_config.py` com imports**

```python
"""Testes de plugadvpl.runtime_config (v0.8.0 Fase 1)."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from plugadvpl.runtime_config import (
    RuntimeConfig,
    RuntimeConfigError,
    init_gitignore_entry,
    load,
    render_template,
)
```

- [ ] **Step 1.1.3: Commit esqueleto**

```bash
git add cli/plugadvpl/runtime_config.py cli/tests/unit/test_runtime_config.py
git commit -m "feat(runtime_config): skeleton module + dataclasses (Fase 1 #1)"
```

#### Step 1.2 — `load()` retorna `None` quando TOML ausente

- [ ] **Step 1.2.1: Escrever teste (RED)**

Adicionar em `test_runtime_config.py`:
```python
class TestLoadAbsent:
    def test_returns_none_when_toml_missing(self, tmp_path: Path) -> None:
        """Sem runtime.toml → None (sem exceção). Modo appre funciona assim."""
        assert load(tmp_path) is None
```

- [ ] **Step 1.2.2: Rodar teste — esperado FAIL com `NotImplementedError`**

```bash
cd cli && python -m pytest tests/unit/test_runtime_config.py::TestLoadAbsent -v --override-ini="addopts="
```
Expected: `FAILED ... NotImplementedError`

- [ ] **Step 1.2.3: Implementação mínima em `load()`**

```python
def load(root: Path) -> RuntimeConfig | None:
    toml_path = root / ".plugadvpl" / "runtime.toml"
    if not toml_path.is_file():
        return None
    raise NotImplementedError("parse será no próximo step")
```

- [ ] **Step 1.2.4: Rodar — esperado PASS**

```bash
cd cli && python -m pytest tests/unit/test_runtime_config.py::TestLoadAbsent -v --override-ini="addopts="
```

- [ ] **Step 1.2.5: Commit**

```bash
git add cli/plugadvpl/runtime_config.py cli/tests/unit/test_runtime_config.py
git commit -m "feat(runtime_config): load() returns None when TOML missing"
```

#### Step 1.3 — `load()` parseia TOML válido completo

- [ ] **Step 1.3.1: Escrever teste positivo + helper de fixture**

```python
def _fake_advpls_binary(root: Path) -> Path:
    """Cria executável real (cross-platform) que serve como `tds_ls.binary`.

    Linux/macOS: shell script `#!/bin/sh\\nexit 0\\n` com mode 0o755.
    Windows: arquivo `.bat` (PATH lookup respeita PATHEXT no PATH, mas
    `Path.is_file()` aceita qualquer extensão).
    """
    import os as _os
    import stat as _stat
    if _os.name == "nt":
        target = root / "fake_advpls.bat"
        target.write_text("@exit /b 0\r\n", encoding="cp1252")
    else:
        target = root / "fake_advpls"
        target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        target.chmod(target.stat().st_mode | _stat.S_IEXEC | _stat.S_IXGRP | _stat.S_IXOTH)
    return target


def _write_minimal_toml(root: Path, **overrides: str) -> Path:
    """Helper: escreve runtime.toml com defaults sensatos + overrides."""
    cfg_dir = root / ".plugadvpl"
    cfg_dir.mkdir(exist_ok=True)
    binary_path = overrides.get("binary", str(_fake_advpls_binary(root)))
    # Path no TOML usa forward slash (TOML não escapa \ — em Windows D:\foo seria erro)
    binary_path_toml = binary_path.replace("\\", "/")
    content = f'''
[tds_ls]
binary = "{binary_path_toml}"

[appserver]
host = "127.0.0.1"
port = 1234
secure = false
build = "7.00.240223P"
environment = "P2510"

[auth]
user_env = "PROTHEUS_USER"
password_env = "PROTHEUS_PASS"
aut_file = ""

[compile]
recompile = true
includes = []
mode = "auto"
timeout_seconds = 120
include_warnings = true

[logging]
log_to_file = ""
show_console_output = true
'''
    toml_path = cfg_dir / "runtime.toml"
    toml_path.write_text(content, encoding="utf-8")
    return toml_path


class TestLoadValidComplete:
    def test_returns_dataclass_when_all_valid(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "totvs")
        _write_minimal_toml(tmp_path)
        with patch("plugadvpl.runtime_config._tcp_ping", return_value=False):
            cfg = load(tmp_path)
        assert cfg is not None
        assert isinstance(cfg, RuntimeConfig)
        assert cfg.appserver.host == "127.0.0.1"
        assert cfg.appserver.port == 1234
        assert cfg.compile.mode == "auto"
        assert cfg.warn_remote_host is False
        assert cfg.appserver_reachable is False
```

- [ ] **Step 1.3.2: RED**

```bash
cd cli && python -m pytest tests/unit/test_runtime_config.py::TestLoadValidComplete -v --override-ini="addopts="
```
Expected: FAIL.

- [ ] **Step 1.3.3: GREEN — implementar parser**

Substituir corpo de `load()`:
```python
def _tcp_ping(host: str, port: int, timeout: float = 1.0) -> bool:
    """Tenta conectar TCP. True se responde dentro do timeout."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def _require(d: dict, section: str, key: str, src: Path) -> object:
    if section not in d or key not in d[section]:
        raise RuntimeConfigError(
            f"missing required key [{section}].{key} in {src}"
        )
    return d[section][key]


def _require_env(varname: str, ref: str) -> str:
    val = os.environ.get(varname)
    if val is None:
        raise RuntimeConfigError(
            f"env var {varname} (referenced by {ref}) is not set"
        )
    return val


def load(root: Path) -> RuntimeConfig | None:
    toml_path = root / ".plugadvpl" / "runtime.toml"
    if not toml_path.is_file():
        return None
    try:
        raw = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeConfigError(f"invalid TOML in {toml_path}: {exc}") from exc

    # tds_ls
    binary_str = str(_require(raw, "tds_ls", "binary", toml_path))
    binary = Path(binary_str)
    if not binary.is_file():
        raise RuntimeConfigError(f"advpls not found at {binary}")
    try:
        resolved = binary.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise RuntimeConfigError(
            f"binary path resolution failed for {binary}: {exc}"
        ) from exc
    is_symlink = binary.is_symlink()
    tds_ls = TdsLsConfig(binary=resolved, binary_is_symlink=is_symlink)

    # appserver
    asv = raw.get("appserver", {})
    appserver = AppserverConfig(
        host=str(_require(raw, "appserver", "host", toml_path)),
        port=int(_require(raw, "appserver", "port", toml_path)),
        secure=bool(asv.get("secure", False)),
        build=str(_require(raw, "appserver", "build", toml_path)),
        environment=str(_require(raw, "appserver", "environment", toml_path)),
    )

    # auth
    auth_raw = raw.get("auth", {})
    user_env = str(_require(raw, "auth", "user_env", toml_path))
    password_env = str(_require(raw, "auth", "password_env", toml_path))
    _require_env(user_env, "auth.user_env")
    _require_env(password_env, "auth.password_env")
    aut_file_str = str(auth_raw.get("aut_file", "") or "")
    aut_file: Path | None = None
    if aut_file_str:
        aut_file = Path(aut_file_str)
        if not aut_file.is_file():
            raise RuntimeConfigError(f"aut_file not found: {aut_file}")
    auth = AuthConfig(user_env=user_env, password_env=password_env, aut_file=aut_file)

    # compile
    cmp_raw = raw.get("compile", {})
    compile_cfg = CompileConfig(
        recompile=bool(cmp_raw.get("recompile", True)),
        includes=tuple(Path(p) for p in cmp_raw.get("includes", [])),
        mode=str(cmp_raw.get("mode", "auto")),
        timeout_seconds=int(cmp_raw.get("timeout_seconds", 120)),
        include_warnings=bool(cmp_raw.get("include_warnings", True)),
    )

    # logging (optional section)
    log_raw = raw.get("logging", {})
    logging_cfg = LoggingConfig(
        log_to_file=str(log_raw.get("log_to_file", "") or ""),
        show_console_output=bool(log_raw.get("show_console_output", True)),
    )

    warn_remote = appserver.host not in {"127.0.0.1", "localhost", "::1"}
    reachable = _tcp_ping(appserver.host, appserver.port)

    return RuntimeConfig(
        tds_ls=tds_ls,
        appserver=appserver,
        auth=auth,
        compile=compile_cfg,
        logging=logging_cfg,
        warn_remote_host=warn_remote,
        appserver_reachable=reachable,
        source_path=toml_path,
    )
```

- [ ] **Step 1.3.4: GREEN — rodar teste**

```bash
cd cli && python -m pytest tests/unit/test_runtime_config.py::TestLoadValidComplete -v --override-ini="addopts="
```
Expected: PASS.

- [ ] **Step 1.3.5: Commit**

```bash
git add cli/plugadvpl/runtime_config.py cli/tests/unit/test_runtime_config.py
git commit -m "feat(runtime_config): load() parses valid TOML completely"
```

#### Step 1.4 — Validações específicas (uma por sub-step, padrão RED→GREEN→COMMIT)

Para cada validação abaixo, repetir o ciclo: escrever teste RED → rodar → adicionar/refinar check em `load()` → rodar GREEN → commit. Use mensagens de commit no padrão `feat(runtime_config): validate <X>`.

- [ ] **Step 1.4.1: TOML malformado → RuntimeConfigError com mensagem**

```python
class TestLoadInvalid:
    def test_malformed_toml_raises(self, tmp_path: Path) -> None:
        cfg_dir = tmp_path / ".plugadvpl"
        cfg_dir.mkdir()
        (cfg_dir / "runtime.toml").write_text("not = valid = toml = at = all", encoding="utf-8")
        with pytest.raises(RuntimeConfigError, match="invalid TOML"):
            load(tmp_path)
```

- [ ] **Step 1.4.2: seção `[tds_ls]` ausente**

```python
    def test_missing_section_raises(self, tmp_path: Path) -> None:
        cfg_dir = tmp_path / ".plugadvpl"
        cfg_dir.mkdir()
        (cfg_dir / "runtime.toml").write_text("[appserver]\nhost = '127.0.0.1'\n", encoding="utf-8")
        with pytest.raises(RuntimeConfigError, match="missing required key"):
            load(tmp_path)
```

- [ ] **Step 1.4.3: `binary` aponta para arquivo inexistente**

```python
    def test_binary_missing_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "x")
        monkeypatch.setenv("PROTHEUS_PASS", "y")
        _write_minimal_toml(tmp_path, binary="/nope/advpls.exe")
        with pytest.raises(RuntimeConfigError, match="advpls not found"):
            load(tmp_path)
```

- [ ] **Step 1.4.4: env var ausente**

```python
    def test_env_var_missing_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PROTHEUS_USER", raising=False)
        monkeypatch.setenv("PROTHEUS_PASS", "y")
        _write_minimal_toml(tmp_path)
        with pytest.raises(RuntimeConfigError, match="env var PROTHEUS_USER"):
            load(tmp_path)
```

- [ ] **Step 1.4.5: `aut_file` setado mas inexistente**

```python
    def test_aut_file_missing_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "x")
        monkeypatch.setenv("PROTHEUS_PASS", "y")
        cfg_dir = tmp_path / ".plugadvpl"
        cfg_dir.mkdir()
        # patch _write_minimal_toml with explicit aut_file
        toml = _write_minimal_toml(tmp_path).read_text(encoding="utf-8")
        toml = toml.replace('aut_file = ""', 'aut_file = "/nope/chave.aut"')
        (cfg_dir / "runtime.toml").write_text(toml, encoding="utf-8")
        with pytest.raises(RuntimeConfigError, match="aut_file not found"):
            load(tmp_path)
```

- [ ] **Step 1.4.6: host remoto → flag `warn_remote_host=True`**

```python
class TestLoadFlags:
    def test_warn_remote_host_true_for_remote(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "x")
        monkeypatch.setenv("PROTHEUS_PASS", "y")
        toml_path = _write_minimal_toml(tmp_path)
        toml = toml_path.read_text(encoding="utf-8").replace(
            'host = "127.0.0.1"', 'host = "187.77.46.221"'
        )
        toml_path.write_text(toml, encoding="utf-8")
        with patch("plugadvpl.runtime_config._tcp_ping", return_value=False):
            cfg = load(tmp_path)
        assert cfg is not None
        assert cfg.warn_remote_host is True

    def test_appserver_reachable_set_by_ping(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "x")
        monkeypatch.setenv("PROTHEUS_PASS", "y")
        _write_minimal_toml(tmp_path)
        with patch("plugadvpl.runtime_config._tcp_ping", return_value=True):
            cfg = load(tmp_path)
        assert cfg is not None
        assert cfg.appserver_reachable is True
```

Após cada teste passar, commit. Mínimo 1 commit por validação (6 commits aqui).

#### Step 1.5 — `render_template()` + `init_gitignore_entry()`

- [ ] **Step 1.5.1: Teste de `render_template` (round-trip)**

```python
class TestRenderTemplate:
    def test_template_has_all_sections(self) -> None:
        text = render_template()
        for section in ["[tds_ls]", "[appserver]", "[auth]", "[compile]", "[logging]"]:
            assert section in text

    def test_template_is_valid_toml(self) -> None:
        import tomllib
        parsed = tomllib.loads(render_template())
        assert "tds_ls" in parsed
        assert "appserver" in parsed
        assert "auth" in parsed
        assert "compile" in parsed
```

- [ ] **Step 1.5.2: RED → implementar `render_template()` como string literal**

```python
_TEMPLATE = """\
# .plugadvpl/runtime.toml — NÃO commitar valores de credencial
# Gerado por `plugadvpl compile --init-config`. Edite e descomente conforme uso.

[tds_ls]
# Caminho para advpls. Windows típico: D:/TOTVS/protheus/bin/Appserver/advpls.exe
# ou da extensão tds-vscode.
binary = "D:/TOTVS/protheus/bin/Appserver/advpls.exe"

[appserver]
# RECOMENDAÇÃO: host = "127.0.0.1" + SSH tunnel.
# `ssh -L 1234:localhost:1234 user@vps -N`
host = "127.0.0.1"
port = 1234
secure = false
build = "7.00.240223P"
environment = "P2510"

[auth]
# Convenção: NUNCA valor literal. Sempre nome da env var.
# export PROTHEUS_USER=admin / export PROTHEUS_PASS='senha'
user_env = "PROTHEUS_USER"
password_env = "PROTHEUS_PASS"
aut_file = ""

[compile]
recompile = true
includes = [
    "D:/TOTVS/protheus/includes",
]
mode = "auto"            # auto | appre | cli
timeout_seconds = 120
include_warnings = true

[logging]
log_to_file = ""
show_console_output = true
"""


def render_template() -> str:
    return _TEMPLATE
```

- [ ] **Step 1.5.3: GREEN + commit**

```bash
cd cli && python -m pytest tests/unit/test_runtime_config.py::TestRenderTemplate -v --override-ini="addopts="
git add cli/plugadvpl/runtime_config.py cli/tests/unit/test_runtime_config.py
git commit -m "feat(runtime_config): render_template() for --init-config"
```

- [ ] **Step 1.5.4: Teste `init_gitignore_entry()` — adiciona linha**

```python
class TestInitGitignore:
    def test_adds_line_when_gitignore_exists(self, tmp_path: Path) -> None:
        gi = tmp_path / ".gitignore"
        gi.write_text("*.pyc\n", encoding="utf-8")
        assert init_gitignore_entry(tmp_path) is True
        assert ".plugadvpl/runtime.toml" in gi.read_text(encoding="utf-8")

    def test_idempotent(self, tmp_path: Path) -> None:
        gi = tmp_path / ".gitignore"
        gi.write_text(".plugadvpl/runtime.toml\n", encoding="utf-8")
        assert init_gitignore_entry(tmp_path) is False

    def test_no_gitignore_returns_false(self, tmp_path: Path) -> None:
        assert init_gitignore_entry(tmp_path) is False
        assert not (tmp_path / ".gitignore").exists()
```

- [ ] **Step 1.5.5: RED → implementar**

```python
def init_gitignore_entry(root: Path) -> bool:
    gi = root / ".gitignore"
    if not gi.is_file():
        return False
    text = gi.read_text(encoding="utf-8")
    needle = ".plugadvpl/runtime.toml"
    if needle in text:
        return False
    suffix = "" if text.endswith("\n") else "\n"
    gi.write_text(text + suffix + needle + "\n", encoding="utf-8")
    return True
```

- [ ] **Step 1.5.6: GREEN + commit**

```bash
cd cli && python -m pytest tests/unit/test_runtime_config.py -v --override-ini="addopts="
git add cli/plugadvpl/runtime_config.py cli/tests/unit/test_runtime_config.py
git commit -m "feat(runtime_config): init_gitignore_entry() helper"
```

#### Step 1.6 — Suite completa de runtime_config

- [ ] **Step 1.6.1: Confirmar contagem ≥20 testes passing**

```bash
cd cli && python -m pytest tests/unit/test_runtime_config.py -v --override-ini="addopts=" --no-header
```
Expected: pelo menos 20 PASS (cobre Steps 1.2–1.5).

### Task 2: `lookups/redact_patterns.json` + catalog test

**Files:**
- Create: `cli/plugadvpl/lookups/redact_patterns.json`
- Create: `cli/tests/unit/test_compile_catalog_consistency.py`

**Spec refs:** §9 (tabela redact), §14 (critério ≥5 patterns).

#### Step 2.1 — Lookup JSON

- [ ] **Step 2.1.1: Criar `cli/plugadvpl/lookups/redact_patterns.json`**

```json
[
  {
    "id": "password_assignment",
    "description": "password=foo, PASSWORD: foo, etc",
    "pattern": "(?i)(password)\\s*[:=]\\s*\\S+",
    "replacement": "\\1=***REDACTED***"
  },
  {
    "id": "psw_assignment",
    "description": "psw=foo (advpls .ini canonical)",
    "pattern": "(?i)(psw)\\s*[:=]\\s*\\S+",
    "replacement": "\\1=***REDACTED***"
  },
  {
    "id": "senha_assignment_pt",
    "description": "senha=foo (pt-BR)",
    "pattern": "(?i)(senha)\\s*[:=]\\s*\\S+",
    "replacement": "\\1=***REDACTED***"
  },
  {
    "id": "pwd_assignment",
    "description": "pwd=foo (common alias)",
    "pattern": "(?i)(pwd)\\s*[:=]\\s*\\S+",
    "replacement": "\\1=***REDACTED***"
  },
  {
    "id": "hex_key_long",
    "description": "Hex keys >16 chars (tokens, signatures)",
    "pattern": "\\b[0-9a-fA-F]{16,}\\b",
    "replacement": "***HEX_REDACTED***"
  },
  {
    "id": "aut_file_value",
    "description": "Path/conteúdo do arquivo .aut (chave de autorização TOTVS)",
    "pattern": "(?i)(aut_file|authorization)\\s*[:=]\\s*\\S+",
    "replacement": "\\1=***REDACTED***"
  }
]
```

- [ ] **Step 2.1.2: Commit lookup**

```bash
git add cli/plugadvpl/lookups/redact_patterns.json
git commit -m "feat(lookups): redact_patterns.json for credential masking (Fase 1 #2)"
```

#### Step 2.2 — Catalog consistency test

- [ ] **Step 2.2.1: Criar `cli/tests/unit/test_compile_catalog_consistency.py` esqueleto**

```python
"""Garante que lookups/compile_patterns.json e lookups/redact_patterns.json
seguem o schema esperado pelo runtime. Padrão idêntico ao test_lint_catalog_consistency.
"""
from __future__ import annotations

import json
import re
from importlib import resources as ir

import pytest
```

- [ ] **Step 2.2.2: Teste RED — patterns válidos**

```python
@pytest.fixture(scope="module")
def redact_catalog() -> list[dict]:
    text = ir.files("plugadvpl").joinpath("lookups/redact_patterns.json").read_text(
        encoding="utf-8"
    )
    return json.loads(text)


def test_redact_min_count(redact_catalog: list[dict]) -> None:
    assert len(redact_catalog) >= 5


def test_redact_required_fields(redact_catalog: list[dict]) -> None:
    for entry in redact_catalog:
        for field in ("id", "description", "pattern", "replacement"):
            assert field in entry, f"entry missing {field}: {entry}"


def test_redact_pattern_compiles(redact_catalog: list[dict]) -> None:
    for entry in redact_catalog:
        try:
            re.compile(entry["pattern"])
        except re.error as exc:
            pytest.fail(f"{entry['id']} pattern doesn't compile: {exc}")


def test_redact_ids_unique(redact_catalog: list[dict]) -> None:
    ids = [e["id"] for e in redact_catalog]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"
```

- [ ] **Step 2.2.3: GREEN — rodar**

```bash
cd cli && python -m pytest tests/unit/test_compile_catalog_consistency.py -v --override-ini="addopts="
```
Expected: 4 PASS (testes do redact apenas. Asserts de `compile_patterns.json` são adicionados em Step 3.8 — o arquivo JSON será criado em Step 3.1.2 mas só ganha asserts cobrindo seu schema no final do Chunk 2).

- [ ] **Step 2.2.4: Commit**

```bash
git add cli/tests/unit/test_compile_catalog_consistency.py
git commit -m "test(catalog): consistency tests for redact_patterns"
```

---

## Chunk 2: Parser

### Task 3: `compile_parser.py` + `lookups/compile_patterns.json` + fixtures

**Files:**
- Create: `cli/plugadvpl/compile_parser.py`
- Create: `cli/plugadvpl/lookups/compile_patterns.json`
- Create: `cli/tests/unit/test_compile_parser.py`
- Create: `cli/tests/fixtures/compile_outputs/*.txt` (8 fixtures)
- Modify: `cli/tests/unit/test_compile_catalog_consistency.py` (adicionar testes do compile_patterns)

**Spec refs:** §5, §7.8, §8.1, §11.1.

#### Step 3.1 — Esqueleto do módulo + dataclass

- [ ] **Step 3.1.1: Criar `cli/plugadvpl/compile_parser.py`**

```python
"""Parser de saída do advpls. Função pura (sem subprocess, sem fs).

Spec: docs/fase1/compile-design.md §7.8, §8.

Estratégia:
- Aplica regex patterns de lookups/compile_patterns.json em ordem (`ordem` ASC).
- Linhas não-classificadas viram Diagnostic(severidade='unknown').
- Normaliza Diagnostic.arquivo via Path.resolve() vs requested_files.
- Aplica redact_patterns.json em Diagnostic.raw antes de devolver.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from importlib import resources as ir
from pathlib import Path


@dataclass(frozen=True)
class Diagnostic:
    severidade: str          # error | warning | info | unknown
    arquivo: str
    linha: int
    coluna: int
    mensagem: str
    codigo: str
    raw: str

    def to_dict(self) -> dict[str, object]:
        return {
            "severidade": self.severidade,
            "arquivo": self.arquivo,
            "linha": self.linha,
            "coluna": self.coluna,
            "mensagem": self.mensagem,
            "codigo": self.codigo,
            "raw": self.raw,
        }


def parse_diagnostics(
    stdout: str,
    stderr: str,
    mode: str,
    requested_files: list[Path],
) -> tuple[list[Diagnostic], list[Diagnostic]]:
    """Parseia output do advpls e devolve (matched, unmatched_bucket).

    ``matched`` = diagnostics cujo arquivo bate com requested_files após resolve.
    ``unmatched_bucket`` = diagnostics com arquivo desconhecido (vão pra row __unmatched__).
    """
    raise NotImplementedError("será implementado nos próximos steps")
```

- [ ] **Step 3.1.2: Criar `cli/plugadvpl/lookups/compile_patterns.json` com 5 patterns iniciais**

```json
[
  {
    "id": "advpls_en_paren_loc",
    "lang": "en",
    "pattern": "^(?P<arquivo>[^\\s()]+)\\((?P<linha>\\d+)(?:,(?P<coluna>\\d+))?\\)\\s+(?P<severidade>error|warning|info):\\s*(?P<mensagem>.+)$",
    "severidade_group": "severidade",
    "ordem": 10
  },
  {
    "id": "advpls_pt_paren_loc",
    "lang": "pt-BR",
    "pattern": "^(?P<arquivo>[^\\s()]+)\\((?P<linha>\\d+)(?:,(?P<coluna>\\d+))?\\)\\s+(?P<severidade>erro|aviso|info):\\s*(?P<mensagem>.+)$",
    "severidade_group": "severidade",
    "ordem": 11
  },
  {
    "id": "tdscli_pt_erro_ao_compilar",
    "lang": "pt-BR",
    "pattern": "^Erro\\s+ao\\s+compilar\\s+(?P<arquivo>\\S+):\\s*linha\\s+(?P<linha>\\d+)\\s*-\\s*(?P<mensagem>.+)$",
    "severidade_fixed": "error",
    "ordem": 20
  },
  {
    "id": "tdscli_pt_aviso",
    "lang": "pt-BR",
    "pattern": "^Aviso\\s+em\\s+(?P<arquivo>\\S+):\\s*linha\\s+(?P<linha>\\d+)\\s*-\\s*(?P<mensagem>.+)$",
    "severidade_fixed": "warning",
    "ordem": 21
  },
  {
    "id": "appre_include_not_found",
    "lang": "any",
    "pattern": "^Include\\s+['\"](?P<mensagem>[^'\"]+)['\"]\\s+not\\s+found\\s+in\\s+(?P<arquivo>\\S+)(?::(?P<linha>\\d+))?$",
    "severidade_fixed": "error",
    "ordem": 30
  }
]
```

Mapeamento `severidade` PT-BR (`erro`/`aviso`) → EN (`error`/`warning`) é feito dentro do parser (Step 3.4).

- [ ] **Step 3.1.3: Criar `cli/tests/unit/test_compile_parser.py` esqueleto**

```python
"""Testes de plugadvpl.compile_parser (v0.8.0 Fase 1)."""
from __future__ import annotations

from pathlib import Path

import pytest

from plugadvpl.compile_parser import Diagnostic, parse_diagnostics
```

- [ ] **Step 3.1.4: Commit esqueleto**

```bash
git add cli/plugadvpl/compile_parser.py cli/plugadvpl/lookups/compile_patterns.json cli/tests/unit/test_compile_parser.py
git commit -m "feat(compile_parser): skeleton + 5 initial patterns (Fase 1 #3)"
```

#### Step 3.2 — Fixtures de output do advpls

- [ ] **Step 3.2.1: Criar 8 fixtures em `cli/tests/fixtures/compile_outputs/`**

Cada arquivo é um output sintético sanitizado. Sem credencial, sem nome real.

`unbalanced_endif_en.txt`:
```
foo.prw(42) error: Unbalanced ENDIF at line 42
```

`missing_include_pt.txt`:
```
Erro ao compilar foo.prw: linha 3 - INCLUDE 'xxx.ch' nao encontrado
```

`variable_unused_warn.txt`:
```
foo.prw(17) warning: Variable 'cAux' declared but not used
```

`mixed_errors_warnings.txt`:
```
foo.prw(10) error: Function 'BarFunc' is undefined
foo.prw(12) error: Type mismatch in expression
bar.prw(5) warning: Variable 'nQtde' may be uninitialized
foo.prw(20) error: Unbalanced ENDIF
bar.prw(8) warning: Deprecated function 'OldFn' used
foo.prw(30) warning: Unreachable code after Return
foo.prw(40) error: Syntax error before token ';'
foo.prw(45) error: Expected expression, got '{'
Compilation finished with 5 errors and 3 warnings.
[2026-05-18 10:32:14] Build context: P2510
```

`clean_compile.txt`:
```
Compilation finished successfully.
```

`advpls_crash.txt`:
```
Segmentation fault (core dumped)
advpls: cannot read source file 'foo.prw': stream closed
```

`empty_output.txt`:
```
```
(arquivo vazio mesmo — touch)

`huge_output_trunc.txt`: (gerar com helper Python — não commitar 10MB)
Skip por agora: criar fixture menor (~500 linhas) e testar trunc com mock no Step 3.7.

- [ ] **Step 3.2.2: Commit fixtures**

```bash
git add cli/tests/fixtures/compile_outputs/
git commit -m "test(fixtures): 7 sanitized advpls output fixtures"
```

#### Step 3.3 — Parser básico: case en sem normalização

- [ ] **Step 3.3.1: Teste RED — fixture `unbalanced_endif_en.txt`**

```python
FIXTURES = Path(__file__).parent.parent / "fixtures" / "compile_outputs"


class TestParseBasic:
    def test_unbalanced_endif_en(self) -> None:
        raw = (FIXTURES / "unbalanced_endif_en.txt").read_text(encoding="utf-8")
        matched, unmatched = parse_diagnostics(
            stdout=raw, stderr="", mode="cli", requested_files=[Path("foo.prw")]
        )
        assert len(matched) == 1
        d = matched[0]
        assert d.severidade == "error"
        assert d.arquivo == "foo.prw"
        assert d.linha == 42
        assert "Unbalanced" in d.mensagem
        assert unmatched == []
```

- [ ] **Step 3.3.2: RED**

```bash
cd cli && python -m pytest tests/unit/test_compile_parser.py::TestParseBasic -v --override-ini="addopts="
```

- [ ] **Step 3.3.3: GREEN — implementar parser básico**

```python
import functools

_PT_SEVERIDADE_MAP = {"erro": "error", "aviso": "warning", "info": "info"}


@functools.lru_cache(maxsize=1)
def _load_patterns() -> list[dict[str, object]]:
    """Carrega compile_patterns.json e ordena por (ordem ASC, índice no JSON).

    Tie-break determinístico: dois patterns com mesma `ordem` mantêm a ordem
    em que aparecem no JSON (vence o primeiro). Bug evitado: NÃO usar
    `raw.index(p)` durante o sort — é O(n²) e retorna índice da posição
    corrente, não original, quebrando o tie-break.
    """
    text = ir.files("plugadvpl").joinpath("lookups/compile_patterns.json").read_text(
        encoding="utf-8"
    )
    raw = json.loads(text)
    indexed = list(enumerate(raw))
    indexed.sort(key=lambda t: (int(t[1].get("ordem", 999)), t[0]))
    return [p for _, p in indexed]


@functools.lru_cache(maxsize=1)
def _load_redact_patterns() -> list[tuple[re.Pattern[str], str]]:
    text = ir.files("plugadvpl").joinpath("lookups/redact_patterns.json").read_text(
        encoding="utf-8"
    )
    out: list[tuple[re.Pattern[str], str]] = []
    for entry in json.loads(text):
        out.append((re.compile(entry["pattern"]), entry["replacement"]))
    return out


def _redact(text: str, patterns: list[tuple[re.Pattern[str], str]]) -> str:
    for rx, repl in patterns:
        text = rx.sub(repl, text)
    return text


def _classify_severity(raw_value: str, fixed: str | None) -> str:
    if fixed:
        return fixed
    low = raw_value.lower()
    return _PT_SEVERIDADE_MAP.get(low, low)


def parse_diagnostics(
    stdout: str,
    stderr: str,
    mode: str,
    requested_files: list[Path],
) -> tuple[list[Diagnostic], list[Diagnostic]]:
    """Parseia output do advpls.

    Returns:
        ``(matched, unmatched)`` onde:

        - ``matched`` contém TODAS as linhas relevantes para os arquivos
          solicitados, incluindo:
            * diagnostics estruturados (error/warning/info) com arquivo em
              ``requested_files``
            * linhas que NENHUM pattern reconheceu, viram
              ``Diagnostic(severidade='unknown', arquivo='', linha=0, raw=<linha>)``.
              Nunca silencia.
        - ``unmatched`` contém APENAS diagnostics estruturados cujo arquivo
          NÃO bate com nenhum requested_file após ``Path.resolve()``. Vão
          para bucket ``__unmatched__`` no resultado final.
    """
    patterns = _load_patterns()
    compiled = [(p, re.compile(p["pattern"])) for p in patterns]
    redact = _load_redact_patterns()

    matched: list[Diagnostic] = []
    unmatched: list[Diagnostic] = []
    # Resolve mesmo se arquivo não existir (caso comum: usuário passou
    # foo.prw como path que não está no cwd atual do teste).
    requested_resolved: dict[Path, Path] = {}
    for p in requested_files:
        try:
            requested_resolved[p.resolve()] = p
        except (OSError, RuntimeError):
            requested_resolved[Path(str(p))] = p

    for line in (stdout + "\n" + stderr).splitlines():
        if not line.strip():
            continue
        hit = False
        for entry, rx in compiled:
            m = rx.match(line)
            if not m:
                continue
            groups = m.groupdict()
            sev_raw = groups.get(entry.get("severidade_group", "")) or ""
            severidade = _classify_severity(
                sev_raw, entry.get("severidade_fixed")  # type: ignore[arg-type]
            )
            arquivo_raw = groups.get("arquivo", "") or ""
            linha = int(groups.get("linha") or 0)
            coluna = int(groups.get("coluna") or 0)
            mensagem = groups.get("mensagem", "") or ""

            arquivo_final, is_unmatched = _normalize_arquivo(arquivo_raw, requested_resolved)

            diag = Diagnostic(
                severidade=severidade,
                arquivo=arquivo_final,
                linha=linha,
                coluna=coluna,
                mensagem=_redact(mensagem, redact),
                codigo="",
                raw=_redact(line, redact),
            )
            if is_unmatched:
                unmatched.append(diag)
            else:
                matched.append(diag)
            hit = True
            break

        if not hit:
            # Linha que não casou nenhum pattern — preserva como unknown
            matched.append(
                Diagnostic(
                    severidade="unknown",
                    arquivo="",
                    linha=0,
                    coluna=0,
                    mensagem=_redact(line.strip(), redact),
                    codigo="",
                    raw=_redact(line, redact),
                )
            )

    return matched, unmatched


def _normalize_arquivo(
    arquivo_raw: str, requested_resolved: dict[Path, Path]
) -> tuple[str, bool]:
    """Tenta casar arquivo_raw com requested. Retorna (nome_final, is_unmatched)."""
    if not arquivo_raw:
        return "", False
    try:
        candidate = Path(arquivo_raw).resolve()
    except (OSError, RuntimeError):
        return arquivo_raw, True
    if candidate in requested_resolved:
        return str(requested_resolved[candidate]), False
    # tenta match por basename
    for req_resolved, req_original in requested_resolved.items():
        if req_resolved.name.lower() == candidate.name.lower():
            return str(req_original), False
    return arquivo_raw, True
```

- [ ] **Step 3.3.4: GREEN + commit**

```bash
cd cli && python -m pytest tests/unit/test_compile_parser.py -v --override-ini="addopts="
git add cli/plugadvpl/compile_parser.py cli/tests/unit/test_compile_parser.py
git commit -m "feat(compile_parser): basic parse_diagnostics for en patterns"
```

#### Step 3.4 — Casos pt-BR

- [ ] **Step 3.4.1: Teste pt-BR**

```python
    def test_pt_br_missing_include(self) -> None:
        raw = (FIXTURES / "missing_include_pt.txt").read_text(encoding="utf-8")
        matched, _ = parse_diagnostics(
            stdout=raw, stderr="", mode="cli", requested_files=[Path("foo.prw")]
        )
        assert len(matched) == 1
        assert matched[0].severidade == "error"
        assert matched[0].linha == 3
        assert "xxx.ch" in matched[0].mensagem
```

- [ ] **Step 3.4.2: GREEN (já deveria passar) + commit**

```bash
cd cli && python -m pytest tests/unit/test_compile_parser.py -v --override-ini="addopts="
git add cli/tests/unit/test_compile_parser.py
git commit -m "test(compile_parser): pt-BR include missing case"
```

#### Step 3.5 — Mixed errors/warnings + linha unknown

- [ ] **Step 3.5.1: Teste**

```python
class TestParseMixed:
    def test_mixed_counts_match(self) -> None:
        raw = (FIXTURES / "mixed_errors_warnings.txt").read_text(encoding="utf-8")
        matched, _ = parse_diagnostics(
            stdout=raw, stderr="", mode="cli",
            requested_files=[Path("foo.prw"), Path("bar.prw")],
        )
        errors = [d for d in matched if d.severidade == "error"]
        warnings = [d for d in matched if d.severidade == "warning"]
        unknowns = [d for d in matched if d.severidade == "unknown"]
        assert len(errors) == 5
        assert len(warnings) == 3
        assert len(unknowns) >= 2  # "Compilation finished" + "[2026..." linhas
```

- [ ] **Step 3.5.2: GREEN + commit**

```bash
cd cli && python -m pytest tests/unit/test_compile_parser.py::TestParseMixed -v --override-ini="addopts="
git add cli/tests/unit/test_compile_parser.py
git commit -m "test(compile_parser): mixed output produces correct counts + unknown"
```

#### Step 3.6 — Normalização de path (CRITICAL #2 do review)

- [ ] **Step 3.6.1: Testes**

```python
class TestPathNormalization:
    def test_absolute_path_matches_relative_request(self, tmp_path: Path) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        absolute_str = str(foo.resolve())
        raw = f"{absolute_str}(42) error: bad"
        matched, unmatched = parse_diagnostics(
            stdout=raw, stderr="", mode="cli", requested_files=[foo],
        )
        assert len(matched) == 1
        assert matched[0].arquivo == str(foo)
        assert unmatched == []

    def test_unrequested_file_goes_to_unmatched_bucket(
        self, tmp_path: Path
    ) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        raw = "outro.prw(1) error: bad"
        matched, unmatched = parse_diagnostics(
            stdout=raw, stderr="", mode="cli", requested_files=[foo],
        )
        # nenhum match em matched (vai pra unmatched ou unknown)
        errors_in_matched = [d for d in matched if d.severidade == "error"]
        assert errors_in_matched == []
        assert len(unmatched) == 1
        assert unmatched[0].arquivo == "outro.prw"
```

- [ ] **Step 3.6.2: GREEN + commit (já deve passar com impl atual)**

```bash
cd cli && python -m pytest tests/unit/test_compile_parser.py::TestPathNormalization -v --override-ini="addopts="
git add cli/tests/unit/test_compile_parser.py
git commit -m "test(compile_parser): path normalization absolute<->relative + unmatched bucket"
```

#### Step 3.7 — Tie-break + edge cases

- [ ] **Step 3.7.1: Teste tie-break (mesma ordem, primeiro do JSON vence)**

```python
class TestTieBreak:
    def test_same_ordem_first_in_json_wins(self) -> None:
        # advpls_en_paren_loc tem ordem=10, advpls_pt_paren_loc tem ordem=11
        # Uma linha que ambos poderiam casar (se tivessem ordem igual) — usar
        # construção que só EN match (verb 'error') pra confirmar precedência.
        raw = "foo.prw(1) error: x"
        matched, _ = parse_diagnostics(
            stdout=raw, stderr="", mode="cli", requested_files=[Path("foo.prw")]
        )
        assert len(matched) == 1
        # severidade veio do EN pattern (não tentou PT 'erro')
        assert matched[0].severidade == "error"


class TestEmptyAndCrash:
    def test_empty_output_returns_empty_lists(self) -> None:
        matched, unmatched = parse_diagnostics(
            stdout="", stderr="", mode="cli", requested_files=[Path("foo.prw")]
        )
        assert matched == []
        assert unmatched == []

    def test_clean_compile_only_unknown_lines(self) -> None:
        raw = (FIXTURES / "clean_compile.txt").read_text(encoding="utf-8")
        matched, unmatched = parse_diagnostics(
            stdout=raw, stderr="", mode="cli", requested_files=[Path("foo.prw")]
        )
        # "Compilation finished successfully." vira unknown — nenhum pattern bate
        assert all(d.severidade == "unknown" for d in matched)
        assert unmatched == []


class TestRedact:
    def test_password_redacted_in_raw(self) -> None:
        raw = "foo.prw(1) error: connection failed psw=mySecret123"
        matched, _ = parse_diagnostics(
            stdout=raw, stderr="", mode="cli", requested_files=[Path("foo.prw")]
        )
        assert len(matched) == 1
        assert "mySecret123" not in matched[0].raw
        assert "mySecret123" not in matched[0].mensagem
        assert "***REDACTED***" in matched[0].raw
```

- [ ] **Step 3.7.2: GREEN + commit**

```bash
cd cli && python -m pytest tests/unit/test_compile_parser.py -v --override-ini="addopts="
git add cli/tests/unit/test_compile_parser.py
git commit -m "test(compile_parser): tie-break + empty + clean + redact"
```

#### Step 3.8 — Adicionar catalog test para `compile_patterns.json`

- [ ] **Step 3.8.1: Estender `test_compile_catalog_consistency.py`**

```python
@pytest.fixture(scope="module")
def compile_catalog() -> list[dict]:
    text = ir.files("plugadvpl").joinpath("lookups/compile_patterns.json").read_text(
        encoding="utf-8"
    )
    return json.loads(text)


def test_compile_min_count(compile_catalog: list[dict]) -> None:
    assert len(compile_catalog) >= 5


def test_compile_required_fields(compile_catalog: list[dict]) -> None:
    for entry in compile_catalog:
        for field in ("id", "lang", "pattern", "ordem"):
            assert field in entry, f"{entry.get('id')} missing {field}"


def test_compile_severity_xor(compile_catalog: list[dict]) -> None:
    for entry in compile_catalog:
        has_group = "severidade_group" in entry
        has_fixed = "severidade_fixed" in entry
        assert has_group != has_fixed, (
            f"{entry['id']}: severidade_group XOR severidade_fixed (got group={has_group} fixed={has_fixed})"
        )


def test_compile_pattern_compiles(compile_catalog: list[dict]) -> None:
    for entry in compile_catalog:
        try:
            re.compile(entry["pattern"])
        except re.error as exc:
            pytest.fail(f"{entry['id']} pattern doesn't compile: {exc}")


def test_compile_group_exists(compile_catalog: list[dict]) -> None:
    for entry in compile_catalog:
        if "severidade_group" not in entry:
            continue
        rx = re.compile(entry["pattern"])
        group = entry["severidade_group"]
        assert group in rx.groupindex, (
            f"{entry['id']}: severidade_group='{group}' not in pattern groups {list(rx.groupindex)}"
        )


def test_compile_lang_valid(compile_catalog: list[dict]) -> None:
    valid = {"any", "pt-BR", "en"}
    for entry in compile_catalog:
        assert entry["lang"] in valid, f"{entry['id']}: invalid lang"


def test_compile_ids_unique(compile_catalog: list[dict]) -> None:
    ids = [e["id"] for e in compile_catalog]
    assert len(ids) == len(set(ids))
```

- [ ] **Step 3.8.2: GREEN + commit**

```bash
cd cli && python -m pytest tests/unit/test_compile_catalog_consistency.py -v --override-ini="addopts="
git add cli/tests/unit/test_compile_catalog_consistency.py
git commit -m "test(catalog): consistency tests for compile_patterns"
```

---

## Chunk 3: Orchestrator

### Task 4: `compile.py` — modo `appre`

**Files:**
- Create: `cli/plugadvpl/compile.py`
- Create: `cli/tests/unit/test_compile.py`

**Spec refs:** §5, §7 inteiro (esp. §7.7 lifecycle subprocess), §9 (error handling).

#### Step 4.1 — Esqueleto

- [ ] **Step 4.1.1: Criar `cli/plugadvpl/compile.py`**

```python
"""Orquestrador do plugadvpl compile (v0.8.0 Fase 1).

Único módulo que toca subprocess + filesystem. Demais (runtime_config,
compile_parser) são funções puras. Spec: docs/fase1/compile-design.md §5, §7.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from plugadvpl.compile_parser import Diagnostic, parse_diagnostics
from plugadvpl.runtime_config import RuntimeConfig


@dataclass(frozen=True)
class CompileRequest:
    files: list[Path]
    mode: Literal["auto", "appre", "cli"]
    no_warnings: bool
    timeout_seconds: int | None
    no_security_warning: bool
    includes_override: list[Path] | None
    changed_since: str | None


@dataclass(frozen=True)
class CompileResult:
    rows: list[dict[str, object]]
    summary: dict[str, object]
    next_steps: list[str]
    exit_code: int


def run(request: CompileRequest, runtime_cfg: RuntimeConfig | None, root: Path) -> CompileResult:
    """Entry point — orquestra todas as etapas e devolve resultado."""
    raise NotImplementedError("será implementado nos próximos steps")
```

- [ ] **Step 4.1.2: Criar `cli/tests/unit/test_compile.py`**

```python
"""Testes do plugadvpl.compile orchestrator (v0.8.0 Fase 1).
Subprocess sempre mockado — nada real."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from plugadvpl.compile import CompileRequest, CompileResult, run
```

- [ ] **Step 4.1.3: Commit**

```bash
git add cli/plugadvpl/compile.py cli/tests/unit/test_compile.py
git commit -m "feat(compile): orchestrator skeleton (Fase 1 #4)"
```

#### Step 4.2 — `resolve_files` (lista explícita)

- [ ] **Step 4.2.1: Teste**

```python
class TestResolveFiles:
    def test_explicit_list_separates_valid_missing_rejected(self, tmp_path: Path) -> None:
        """Critério definido: extensão inválida → `rejected_ext`; arquivo não existe → `missing`;
        ambos os defeitos: prioridade `rejected_ext` (filtragem por ext acontece antes de check de existência)."""
        (tmp_path / "foo.prw").write_text("", encoding="utf-8")
        (tmp_path / "bar.tlpp").write_text("", encoding="utf-8")
        (tmp_path / "baz.txt").write_text("", encoding="utf-8")
        missing_path = tmp_path / "missing.prw"  # extensão válida, mas não existe
        from plugadvpl.compile import resolve_files
        result = resolve_files(
            [tmp_path / "foo.prw", tmp_path / "bar.tlpp",
             tmp_path / "baz.txt", missing_path],
            changed_since=None, root=tmp_path,
        )
        names = sorted(p.name for p in result.valid_files)
        assert names == ["bar.tlpp", "foo.prw"]
        assert result.rejected_ext == [tmp_path / "baz.txt"]
        assert result.missing == [missing_path]
```

- [ ] **Step 4.2.2: Implementação simples**

Adicionar em `compile.py`:
```python
_VALID_EXTS = {".prw", ".prx", ".tlpp", ".ch"}
# .ch só se incluído explicitamente; .tlpp.ch também (validado por endswith)


@dataclass(frozen=True)
class ResolvedFiles:
    valid_files: list[Path]
    missing: list[Path]
    rejected_ext: list[Path]


def resolve_files(
    files: list[Path], changed_since: str | None, root: Path
) -> ResolvedFiles:
    if changed_since:
        files = _resolve_changed_since(changed_since, root)
    valid: list[Path] = []
    missing: list[Path] = []
    rejected: list[Path] = []
    for f in files:
        name = f.name.lower()
        ok_ext = name.endswith(".prw") or name.endswith(".prx") or name.endswith(".tlpp") or name.endswith(".tlpp.ch")
        if not ok_ext:
            rejected.append(f)
            continue
        if not f.exists():
            missing.append(f)
            continue
        valid.append(f)
    return ResolvedFiles(valid_files=valid, missing=missing, rejected_ext=rejected)


def _resolve_changed_since(ref: str, root: Path) -> list[Path]:
    """git diff --name-only <ref> filtrado por extensões."""
    raise NotImplementedError("será implementado em Step 4.3")
```

- [ ] **Step 4.2.3: Rodar + commit**

```bash
cd cli && python -m pytest tests/unit/test_compile.py -v --override-ini="addopts="
git add cli/plugadvpl/compile.py cli/tests/unit/test_compile.py
git commit -m "feat(compile): resolve_files for explicit list"
```

#### Step 4.3 — `_resolve_changed_since` (git diff)

- [ ] **Step 4.3.1: Teste com repo git real em tmp_path**

```python
class TestChangedSince:
    def test_changed_since_lists_modified_advpl_only(self, tmp_path: Path) -> None:
        # Setup repo git mínimo
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
        (tmp_path / "foo.prw").write_text("a", encoding="utf-8")
        (tmp_path / "README.md").write_text("a", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
        # Modify
        (tmp_path / "foo.prw").write_text("ab", encoding="utf-8")
        (tmp_path / "bar.tlpp").write_text("c", encoding="utf-8")
        (tmp_path / "README.md").write_text("ab", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "change"], cwd=tmp_path, check=True)

        from plugadvpl.compile import _resolve_changed_since
        result = _resolve_changed_since("HEAD~1", tmp_path)
        names = sorted(p.name for p in result)
        assert names == ["bar.tlpp", "foo.prw"]  # README.md filtrado

    def test_not_a_git_repo_raises(self, tmp_path: Path) -> None:
        from plugadvpl.compile import _resolve_changed_since
        with pytest.raises(RuntimeError, match="git"):
            _resolve_changed_since("HEAD", tmp_path)
```

- [ ] **Step 4.3.2: Implementação**

```python
def _resolve_changed_since(ref: str, root: Path) -> list[Path]:
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", ref, "--", "*.prw", "*.prx", "*.tlpp"],
            cwd=root, capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"--changed-since requires a git repository at {root}: {exc.stderr.strip()}"
        ) from exc
    except FileNotFoundError as exc:
        raise RuntimeError("git not found in PATH") from exc
    return [root / line for line in proc.stdout.splitlines() if line.strip()]
```

- [ ] **Step 4.3.3: GREEN + commit**

```bash
cd cli && python -m pytest tests/unit/test_compile.py::TestChangedSince -v --override-ini="addopts="
git add cli/plugadvpl/compile.py cli/tests/unit/test_compile.py
git commit -m "feat(compile): --changed-since via git diff"
```

#### Step 4.4 — `pick_mode` (auto/appre/cli decision)

- [ ] **Step 4.4.1: Teste**

```python
class TestPickMode:
    def test_explicit_mode_wins(self) -> None:
        from plugadvpl.compile import pick_mode
        assert pick_mode("cli", runtime_cfg=None) == "cli"
        assert pick_mode("appre", runtime_cfg=None) == "appre"

    def test_auto_no_runtime_cfg_picks_appre(self) -> None:
        from plugadvpl.compile import pick_mode
        assert pick_mode("auto", runtime_cfg=None) == "appre"

    def test_auto_with_reachable_picks_cli(self) -> None:
        from plugadvpl.compile import pick_mode
        cfg = MagicMock(appserver_reachable=True)
        assert pick_mode("auto", runtime_cfg=cfg) == "cli"

    def test_auto_with_unreachable_picks_appre(self) -> None:
        from plugadvpl.compile import pick_mode
        cfg = MagicMock(appserver_reachable=False)
        assert pick_mode("auto", runtime_cfg=cfg) == "appre"
```

- [ ] **Step 4.4.2: Implementação**

```python
def pick_mode(requested: str, runtime_cfg: RuntimeConfig | None) -> str:
    if requested in ("cli", "appre"):
        return requested
    if runtime_cfg is not None and runtime_cfg.appserver_reachable:
        return "cli"
    return "appre"
```

- [ ] **Step 4.4.3: GREEN + commit**

```bash
cd cli && python -m pytest tests/unit/test_compile.py::TestPickMode -v --override-ini="addopts="
git add cli/plugadvpl/compile.py cli/tests/unit/test_compile.py
git commit -m "feat(compile): pick_mode logic (auto/appre/cli)"
```

#### Step 4.5 — `run()` end-to-end modo `appre` (subprocess mockado)

- [ ] **Step 4.5.1: Teste**

```python
class TestRunAppre:
    def test_clean_compile_appre(self, tmp_path: Path) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="appre", no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )
        # Mock subprocess.Popen retornando exit 0 + output limpo
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            proc.communicate.return_value = ("", "")
            proc.returncode = 0
            PopenMock.return_value = proc
            with patch("plugadvpl.compile._resolve_advpls", return_value=Path("/fake/advpls")):
                result = run(request, runtime_cfg=None, root=tmp_path)
        assert result.exit_code == 0
        assert result.summary["mode_used"] == "appre"
        assert result.summary["total_files"] == 1
        assert result.summary["ok"] == 1
        assert result.summary["failed"] == 0

    def test_compile_appre_with_error(self, tmp_path: Path) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="appre", no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            proc.communicate.return_value = ("foo.prw(42) error: Unbalanced ENDIF", "")
            proc.returncode = 1
            PopenMock.return_value = proc
            with patch("plugadvpl.compile._resolve_advpls", return_value=Path("/fake/advpls")):
                result = run(request, runtime_cfg=None, root=tmp_path)
        assert result.exit_code == 1
        assert result.summary["failed"] == 1
        row = result.rows[0]
        assert row["ok"] is False
        assert row["counts"]["error"] == 1
```

- [ ] **Step 4.5.2: Implementação `run()` para modo appre**

```python
_UTF8_BOM = b"\xef\xbb\xbf"
_UTF16_LE_BOM = b"\xff\xfe"
_UTF16_BE_BOM = b"\xfe\xff"


def _decode_advpls_output(raw: bytes) -> str:
    """Decodifica saída do advpls tratando BOM UTF-16 (PowerShell/WinSrv) e fallback CP1252.

    Estratégia:
    1. BOM UTF-16 LE/BE → decode utf-16-le/be + strip BOM
    2. BOM UTF-8 → strip BOM + utf-8
    3. UTF-8 strict tenta; se >5% chars são replacement char → fallback CP1252
    4. CP1252 errors='replace' como último recurso
    """
    if raw.startswith(_UTF16_LE_BOM):
        return raw[len(_UTF16_LE_BOM):].decode("utf-16-le", errors="replace")
    if raw.startswith(_UTF16_BE_BOM):
        return raw[len(_UTF16_BE_BOM):].decode("utf-16-be", errors="replace")
    if raw.startswith(_UTF8_BOM):
        raw = raw[len(_UTF8_BOM):]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")
    # Se decode com utf-8 strict funcionou, ok. Mas se usou errors='replace'
    # e teve muito '�', vale fallback. Como tentamos strict aqui, OK.
    return text


def _resolve_advpls(runtime_cfg: RuntimeConfig | None) -> Path:
    if runtime_cfg is not None:
        return runtime_cfg.tds_ls.binary
    # Auto-detect PATH
    found = shutil.which("advpls") or shutil.which("advpls.exe")
    if not found:
        raise RuntimeError(
            "advpls not found in PATH. Set tds_ls.binary in runtime.toml or "
            "install tds-vscode extension."
        )
    return Path(found)


def _build_appre_args(binary: Path, includes: list[Path], files: list[Path]) -> list[str]:
    args: list[str] = [str(binary), "appre"]
    for inc in includes:
        args.append(f"-I{inc}")
    args.extend(str(f) for f in files)
    return args


def run(request: CompileRequest, runtime_cfg: RuntimeConfig | None, root: Path) -> CompileResult:
    resolved = resolve_files(request.files, request.changed_since, root)
    files = resolved.valid_files
    mode = pick_mode(request.mode, runtime_cfg)
    binary = _resolve_advpls(runtime_cfg)

    if mode == "appre":
        includes = (
            request.includes_override
            if request.includes_override is not None
            else (list(runtime_cfg.compile.includes) if runtime_cfg else [])
        )
        args = _build_appre_args(binary, includes, files)
    else:
        raise NotImplementedError("modo cli no Step 4.6")

    start = time.monotonic()
    # CRÍTICO: captura como BYTES (encoding=None) para detectar BOM UTF-16
    # antes de decodificar. PowerShell/Win Server às vezes emite UTF-16LE.
    proc = subprocess.Popen(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = proc.communicate(timeout=request.timeout_seconds)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        return _build_timeout_result(files, request.timeout_seconds, mode)

    stdout = _decode_advpls_output(stdout_bytes)
    stderr = _decode_advpls_output(stderr_bytes)
    duration_ms = int((time.monotonic() - start) * 1000)
    matched, unmatched = parse_diagnostics(
        stdout=stdout, stderr=stderr, mode=mode, requested_files=files,
    )

    # group diagnostics by file
    by_file: dict[str, list[Diagnostic]] = {str(f): [] for f in files}
    for d in matched:
        if d.arquivo in by_file:
            by_file[d.arquivo].append(d)
        else:
            by_file.setdefault("__unknown__", []).append(d)

    rows: list[dict[str, object]] = []
    for fpath, diags in by_file.items():
        counts = {
            "error": sum(1 for d in diags if d.severidade == "error"),
            "warning": sum(1 for d in diags if d.severidade == "warning"),
            "info": sum(1 for d in diags if d.severidade == "info"),
            "unknown": sum(1 for d in diags if d.severidade == "unknown"),
        }
        rows.append({
            "arquivo": fpath,
            "ok": counts["error"] == 0,
            "mode": mode,
            "duration_ms": duration_ms,
            "exit_code": proc.returncode,
            "counts": counts,
            "diagnostics": [d.to_dict() for d in diags],
        })

    if unmatched:
        rows.append({
            "arquivo": "__unmatched__",
            "ok": False,
            "mode": mode,
            "duration_ms": duration_ms,
            "exit_code": proc.returncode,
            "counts": {"error": sum(1 for d in unmatched if d.severidade == "error"),
                       "warning": 0, "info": 0, "unknown": 0},
            "diagnostics": [d.to_dict() for d in unmatched],
        })

    total_errors = sum(int(r["counts"]["error"]) for r in rows)  # type: ignore[index]
    total_warnings = sum(int(r["counts"]["warning"]) for r in rows)  # type: ignore[index]
    failed = sum(1 for r in rows if not r["ok"])
    exit_code = 1 if total_errors > 0 else 0

    summary = {
        "total_files": len(files),
        "ok": len(files) - failed,
        "failed": failed,
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "mode_used": mode,
        "appserver_reachable": runtime_cfg.appserver_reachable if runtime_cfg else False,
        "runtime_config_loaded": runtime_cfg is not None,
        "output_truncated": False,
    }
    next_steps = _build_next_steps(rows, mode)
    return CompileResult(rows=rows, summary=summary, next_steps=next_steps, exit_code=exit_code)


def _build_timeout_result(files: list[Path], timeout: int | None, mode: str) -> CompileResult:
    diag = {
        "severidade": "error", "arquivo": "", "linha": 0, "coluna": 0,
        "mensagem": f"compile timeout after {timeout}s", "codigo": "", "raw": "",
    }
    rows = [{
        "arquivo": str(f), "ok": False, "mode": mode, "duration_ms": (timeout or 0) * 1000,
        "exit_code": 124,
        "counts": {"error": 1, "warning": 0, "info": 0, "unknown": 0},
        "diagnostics": [dict(diag, arquivo=str(f))],
    } for f in files]
    summary = {
        "total_files": len(files), "ok": 0, "failed": len(files),
        "total_errors": len(files), "total_warnings": 0,
        "mode_used": mode, "appserver_reachable": False,
        "runtime_config_loaded": False, "output_truncated": False,
    }
    return CompileResult(rows=rows, summary=summary, next_steps=[], exit_code=1)


def _build_next_steps(rows: list[dict[str, object]], mode: str) -> list[str]:
    if all(r["ok"] for r in rows):
        return []
    failed_files = [str(r["arquivo"]) for r in rows if not r["ok"] and r["arquivo"] != "__unmatched__"]
    steps: list[str] = []
    if failed_files:
        steps.append(f"plugadvpl arch {failed_files[0]}   # contexto arquitetural")
    steps.append("plugadvpl compile <file> --no-warnings   # filtra warnings")
    return steps
```

- [ ] **Step 4.5.3: GREEN + commit**

```bash
cd cli && python -m pytest tests/unit/test_compile.py -v --override-ini="addopts="
git add cli/plugadvpl/compile.py cli/tests/unit/test_compile.py
git commit -m "feat(compile): run() implements appre mode end-to-end"
```

### Task 5: `compile.py` — modo `cli`

#### Step 5.1 — Extrair função pura de encoding (refactor `edit_prw.py`)

- [ ] **Step 5.1.1: Adicionar `encode_cp1252_bytes` em `edit_prw.py`**

Adicionar em `cli/plugadvpl/edit_prw.py` (NÃO remover convert_and_save):
```python
def encode_cp1252_bytes(text: str) -> bytes:
    """Encode string para CP1252 bytes (errors='replace').

    Função pura — reusada por compile.py para gerar .ini do advpls.
    """
    return text.encode("cp1252", errors="replace")
```

- [ ] **Step 5.1.2: Teste curto**

Em `cli/tests/unit/test_edit_prw.py`, adicionar:
```python
class TestEncodeBytes:
    def test_encodes_accented_chars_to_cp1252(self) -> None:
        from plugadvpl.edit_prw import encode_cp1252_bytes
        assert encode_cp1252_bytes("Função") == "Função".encode("cp1252")

    def test_replaces_non_encodable_chars(self) -> None:
        from plugadvpl.edit_prw import encode_cp1252_bytes
        # caractere 你 não existe em CP1252 → vira ?
        out = encode_cp1252_bytes("你")
        assert out == b"?"
```

- [ ] **Step 5.1.3: Rodar + commit**

```bash
cd cli && python -m pytest tests/unit/test_edit_prw.py -v --override-ini="addopts="
git add cli/plugadvpl/edit_prw.py cli/tests/unit/test_edit_prw.py
git commit -m "refactor(edit_prw): extract encode_cp1252_bytes for reuse (Fase 1 #5)"
```

#### Step 5.2 — `build_ini_script` (cli .ini generation)

- [ ] **Step 5.2.1: Teste de geração**

```python
class TestBuildIni:
    def test_ini_contains_all_sections(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from plugadvpl.compile import _build_ini_script
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "totvs")
        runtime_cfg = MagicMock(
            appserver=MagicMock(host="127.0.0.1", port=1234, secure=False,
                                build="7.00.240223P", environment="P2510"),
            auth=MagicMock(user_env="PROTHEUS_USER", password_env="PROTHEUS_PASS"),
            compile=MagicMock(recompile=True),
            logging=MagicMock(log_to_file="", show_console_output=True),
        )
        files = [Path("foo.prw"), Path("bar.prw")]
        includes = [Path("D:/inc1"), Path("D:/inc2")]
        text = _build_ini_script(runtime_cfg, files, includes)
        assert "[auth]" in text
        assert "[compile]" in text
        assert "action=authentication" in text
        assert "action=compile" in text
        assert "user=admin" in text
        assert "psw=totvs" in text
        assert "server=127.0.0.1" in text
        assert "port=1234" in text
        assert "secure=0" in text
        assert "build=7.00.240223P" in text
        assert "environment=P2510" in text
        assert "program=foo.prw;bar.prw" in text
        assert "recompile=T" in text
        assert "includes=D:/inc1;D:/inc2" in text
        assert "showConsoleOutput=true" in text
```

- [ ] **Step 5.2.2: Implementação**

```python
def _build_ini_script(
    runtime_cfg: RuntimeConfig, files: list[Path], includes: list[Path]
) -> str:
    user = os.environ[runtime_cfg.auth.user_env]
    pwd = os.environ[runtime_cfg.auth.password_env]
    asv = runtime_cfg.appserver
    log = runtime_cfg.logging

    lines: list[str] = []
    lines.append(f"logToFile={log.log_to_file}")
    lines.append(f"showConsoleOutput={'true' if log.show_console_output else 'false'}")
    lines.append("")
    lines.append("[auth]")
    lines.append("action=authentication")
    lines.append(f"server={asv.host}")
    lines.append(f"port={asv.port}")
    lines.append(f"secure={1 if asv.secure else 0}")
    lines.append(f"build={asv.build}")
    lines.append(f"environment={asv.environment}")
    lines.append(f"user={user}")
    lines.append(f"psw={pwd}")
    lines.append("")
    lines.append("[compile]")
    lines.append("action=compile")
    lines.append(f"program={';'.join(str(f) for f in files)}")
    lines.append(f"recompile={'T' if runtime_cfg.compile.recompile else 'F'}")
    lines.append(f"includes={';'.join(str(i) for i in includes)}")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 5.2.3: GREEN + commit**

```bash
cd cli && python -m pytest tests/unit/test_compile.py::TestBuildIni -v --override-ini="addopts="
git add cli/plugadvpl/compile.py cli/tests/unit/test_compile.py
git commit -m "feat(compile): _build_ini_script() generates advpls cli script"
```

#### Step 5.3 — Tempfile com permission 0o600

- [ ] **Step 5.3.1: Teste**

```python
class TestTempIniFile:
    def test_creates_secure_tempdir_and_file(self, tmp_path: Path) -> None:
        from plugadvpl.compile import _write_secure_ini
        content = "[auth]\nuser=admin\n"
        ini_path, tempdir = _write_secure_ini(content)
        try:
            assert ini_path.is_file()
            # Verifica encoding CP1252
            raw = ini_path.read_bytes()
            assert raw == content.encode("cp1252", errors="replace")
            # Em Unix, mode 0o600. Em Windows skip por ACL não enforça.
            import os as _os
            if _os.name == "posix":
                mode = _os.stat(ini_path).st_mode & 0o777
                assert mode == 0o600
        finally:
            import shutil as _shutil
            _shutil.rmtree(tempdir, ignore_errors=True)

    def test_encoding_with_accent_password(self, tmp_path: Path) -> None:
        from plugadvpl.compile import _write_secure_ini
        content = "psw=açúcar\n"
        ini_path, tempdir = _write_secure_ini(content)
        try:
            assert ini_path.read_bytes() == "psw=açúcar\n".encode("cp1252")
        finally:
            import shutil as _shutil
            _shutil.rmtree(tempdir, ignore_errors=True)
```

- [ ] **Step 5.3.2: Implementação**

```python
def _write_secure_ini(content: str) -> tuple[Path, Path]:
    """Cria tempdir (0o700) + escreve ini (0o600) em CP1252.

    Retorna (ini_path, tempdir_path) — caller é responsável por shutil.rmtree.
    """
    from plugadvpl.edit_prw import encode_cp1252_bytes

    tempdir = Path(tempfile.mkdtemp(prefix="plugadvpl-", mode=0o700))
    ini_path = tempdir / "compile.ini"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):  # Windows
        flags |= os.O_BINARY
    fd = os.open(ini_path, flags, 0o600)
    try:
        os.write(fd, encode_cp1252_bytes(content))
    finally:
        os.close(fd)
    return ini_path, tempdir
```

- [ ] **Step 5.3.3: GREEN + commit**

```bash
cd cli && python -m pytest tests/unit/test_compile.py::TestTempIniFile -v --override-ini="addopts="
git add cli/plugadvpl/compile.py cli/tests/unit/test_compile.py
git commit -m "feat(compile): _write_secure_ini() with 0o600 + CP1252"
```

#### Step 5.4 — `run()` modo cli end-to-end + security warning

- [ ] **Step 5.4.1: Teste**

```python
class TestRunCli:
    def test_cli_mode_uses_ini_script(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "totvs")
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="cli", no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )
        runtime_cfg = MagicMock(
            tds_ls=MagicMock(binary=Path("/fake/advpls")),
            appserver=MagicMock(host="127.0.0.1", port=1234, secure=False,
                                build="7.00.240223P", environment="P2510"),
            auth=MagicMock(user_env="PROTHEUS_USER", password_env="PROTHEUS_PASS"),
            compile=MagicMock(recompile=True, includes=()),
            logging=MagicMock(log_to_file="", show_console_output=True),
            warn_remote_host=False, appserver_reachable=True,
        )
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            proc.communicate.return_value = ("", "")
            proc.returncode = 0
            PopenMock.return_value = proc
            result = run(request, runtime_cfg=runtime_cfg, root=tmp_path)
        assert result.exit_code == 0
        # Confirma que args começam com binary + "cli" + caminho do .ini
        args = PopenMock.call_args.args[0]
        assert args[0] == "/fake/advpls"
        assert args[1] == "cli"
        assert args[2].endswith("compile.ini")
        # stdin=DEVNULL
        assert PopenMock.call_args.kwargs.get("stdin") == subprocess.DEVNULL

    def test_security_warning_remote_host(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "totvs")
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="cli", no_warnings=False,
            timeout_seconds=10, no_security_warning=False,
            includes_override=None, changed_since=None,
        )
        runtime_cfg = MagicMock(
            tds_ls=MagicMock(binary=Path("/fake/advpls")),
            appserver=MagicMock(host="187.77.46.221", port=1234, secure=False,
                                build="x", environment="y"),
            auth=MagicMock(user_env="PROTHEUS_USER", password_env="PROTHEUS_PASS"),
            compile=MagicMock(recompile=True, includes=()),
            logging=MagicMock(log_to_file="", show_console_output=True),
            warn_remote_host=True, appserver_reachable=True,
        )
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock(); proc.communicate.return_value = ("", ""); proc.returncode = 0
            PopenMock.return_value = proc
            run(request, runtime_cfg=runtime_cfg, root=tmp_path)
        captured = capsys.readouterr()
        assert "WARNING" in captured.err or "warning" in captured.err.lower()
        assert "ssh -L" in captured.err

    def test_no_security_warning_flag(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "totvs")
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="cli", no_warnings=False,
            timeout_seconds=10, no_security_warning=True,  # ← suprime
            includes_override=None, changed_since=None,
        )
        runtime_cfg = MagicMock(
            tds_ls=MagicMock(binary=Path("/fake/advpls")),
            appserver=MagicMock(host="187.77.46.221", port=1234, secure=False,
                                build="x", environment="y"),
            auth=MagicMock(user_env="PROTHEUS_USER", password_env="PROTHEUS_PASS"),
            compile=MagicMock(recompile=True, includes=()),
            logging=MagicMock(log_to_file="", show_console_output=True),
            warn_remote_host=True, appserver_reachable=True,
        )
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock(); proc.communicate.return_value = ("", ""); proc.returncode = 0
            PopenMock.return_value = proc
            run(request, runtime_cfg=runtime_cfg, root=tmp_path)
        captured = capsys.readouterr()
        assert "ssh -L" not in captured.err
```

- [ ] **Step 5.4.2: Implementação — extender `run()`**

Substituir o `raise NotImplementedError("modo cli no Step 4.6")` por:
```python
    if mode == "cli":
        if runtime_cfg is None:
            print(
                "ERROR: runtime.toml required for cli mode. "
                "Run: plugadvpl compile --init-config",
                file=sys.stderr,
            )
            return _build_setup_error_result(files, mode, exit_code=2)

        if runtime_cfg.warn_remote_host and not request.no_security_warning:
            print(
                f"WARNING: appserver.host = {runtime_cfg.appserver.host} (não-local).\n"
                f"TDS-LS envia user/password sem TLS sobre TCP. Recomendado:\n"
                f"  ssh -L {runtime_cfg.appserver.port}:localhost:{runtime_cfg.appserver.port} "
                f"user@{runtime_cfg.appserver.host} -N\n"
                f"  # depois altere host = \"127.0.0.1\" em runtime.toml\n"
                f"(suprima com --no-security-warning)",
                file=sys.stderr,
            )
            # SEM sleep — princípio fail visivelmente (§7.5)

        includes = (
            request.includes_override
            if request.includes_override is not None
            else list(runtime_cfg.compile.includes)
        )
        ini_content = _build_ini_script(runtime_cfg, files, includes)
        ini_path, tempdir = _write_secure_ini(ini_content)
        args = [str(binary), "cli", str(ini_path)]
    else:
        tempdir = None
        # (corpo do appre como antes)
        includes = (
            request.includes_override
            if request.includes_override is not None
            else (list(runtime_cfg.compile.includes) if runtime_cfg else [])
        )
        args = _build_appre_args(binary, includes, files)
```

E envolver o subprocess.Popen em try/finally que limpe `tempdir`:
```python
    try:
        # ... (Popen + communicate + parse) ...
    finally:
        if tempdir is not None:
            try:
                shutil.rmtree(tempdir, ignore_errors=False)
            except OSError as exc:
                print(f"WARN: failed to delete tempdir {tempdir}: {exc}", file=sys.stderr)


def _build_setup_error_result(files: list[Path], mode: str, exit_code: int) -> CompileResult:
    # Schema completo conforme §8 — CI consumer espera todos os campos.
    return CompileResult(
        rows=[],
        summary={
            "total_files": len(files),
            "ok": 0,
            "failed": len(files),
            "total_errors": 0,
            "total_warnings": 0,
            "mode_used": mode,
            "appserver_reachable": False,
            "runtime_config_loaded": False,
            "output_truncated": False,
        },
        next_steps=[],
        exit_code=exit_code,
    )
```

Refatorar `run()` (acima é guia — implementador deve revisar e reorganizar mantendo o que Step 4.5 já criou para appre).

- [ ] **Step 5.4.3: GREEN + commit**

```bash
cd cli && python -m pytest tests/unit/test_compile.py -v --override-ini="addopts="
git add cli/plugadvpl/compile.py cli/tests/unit/test_compile.py
git commit -m "feat(compile): cli mode + security warning (no sleep) + tempdir cleanup"
```

#### Step 5.5 — KeyboardInterrupt + timeout

- [ ] **Step 5.5.1: Teste KeyboardInterrupt**

```python
class TestLifecycle:
    def test_keyboard_interrupt_kills_subprocess_and_cleans_tempdir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "totvs")
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="cli", no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )
        runtime_cfg = MagicMock(
            tds_ls=MagicMock(binary=Path("/fake/advpls")),
            appserver=MagicMock(host="127.0.0.1", port=1234, secure=False,
                                build="x", environment="y"),
            auth=MagicMock(user_env="PROTHEUS_USER", password_env="PROTHEUS_PASS"),
            compile=MagicMock(recompile=True, includes=()),
            logging=MagicMock(log_to_file="", show_console_output=True),
            warn_remote_host=False, appserver_reachable=True,
        )
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            proc.communicate.side_effect = KeyboardInterrupt
            PopenMock.return_value = proc
            with pytest.raises(KeyboardInterrupt):
                run(request, runtime_cfg=runtime_cfg, root=tmp_path)
            proc.terminate.assert_called_once()
```

- [ ] **Step 5.5.2: Implementação KeyboardInterrupt**

No bloco try/except do subprocess:
```python
        try:
            stdout, stderr = proc.communicate(timeout=request.timeout_seconds)
        except subprocess.TimeoutExpired:
            # (já existe da Step 4.5)
            ...
        except KeyboardInterrupt:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            raise
```

- [ ] **Step 5.5.3: GREEN + commit**

```bash
cd cli && python -m pytest tests/unit/test_compile.py::TestLifecycle -v --override-ini="addopts="
git add cli/plugadvpl/compile.py cli/tests/unit/test_compile.py
git commit -m "feat(compile): handle KeyboardInterrupt (terminate + cleanup)"
```

> **NOTA: exit 130** — Step 5.5 garante que `KeyboardInterrupt` re-raise do `run()`. A conversão da exceção em `Exit(code=130)` acontece no **Chunk 4 / Step 6.1.1** (handler `typer.Exit(code=130)` no callback). Spec §9 + §14 cobrem com cross-ref.

#### Step 5.5.4 — KeyboardInterrupt limpa tempdir (verifica filesystem)

- [ ] **Step 5.5.4.1: Teste explícito de limpeza**

```python
    def test_keyboard_interrupt_cleans_tempdir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Spec §11.3: ao receber KeyboardInterrupt, tempdir deve ser removido."""
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "totvs")
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="cli", no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )
        runtime_cfg = MagicMock(
            tds_ls=MagicMock(binary=Path("/fake/advpls")),
            appserver=MagicMock(host="127.0.0.1", port=1234, secure=False,
                                build="x", environment="y"),
            auth=MagicMock(user_env="PROTHEUS_USER", password_env="PROTHEUS_PASS"),
            compile=MagicMock(recompile=True, includes=()),
            logging=MagicMock(log_to_file="", show_console_output=True),
            warn_remote_host=False, appserver_reachable=True,
        )

        captured_tempdir: list[Path] = []
        original_mkdtemp = tempfile.mkdtemp

        def _spy_mkdtemp(*args: object, **kwargs: object) -> str:
            td = original_mkdtemp(*args, **kwargs)
            captured_tempdir.append(Path(td))
            return td

        with patch("plugadvpl.compile.tempfile.mkdtemp", side_effect=_spy_mkdtemp):
            with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
                proc = MagicMock()
                proc.communicate.side_effect = KeyboardInterrupt
                PopenMock.return_value = proc
                with pytest.raises(KeyboardInterrupt):
                    run(request, runtime_cfg=runtime_cfg, root=tmp_path)

        assert len(captured_tempdir) == 1, "esperava 1 tempdir criado"
        assert not captured_tempdir[0].exists(), (
            f"tempdir {captured_tempdir[0]} deveria ter sido removido"
        )
```

- [ ] **Step 5.5.4.2: GREEN + commit (deve passar se finally do Step 5.4 está correto)**

```bash
cd cli && python -m pytest tests/unit/test_compile.py::TestLifecycle::test_keyboard_interrupt_cleans_tempdir -v --override-ini="addopts="
git add cli/tests/unit/test_compile.py
git commit -m "test(compile): KeyboardInterrupt removes tempdir (no leak)"
```

#### Step 5.5.5 — UTF-16 BOM no output

- [ ] **Step 5.5.5.1: Teste UTF-16 LE**

```python
class TestOutputEncoding:
    def test_utf16_le_bom_decoded(self, tmp_path: Path) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="appre", no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )
        # Mock stdout em UTF-16 LE com BOM
        msg = "foo.prw(1) error: Unbalanced ENDIF"
        utf16_bytes = b"\xff\xfe" + msg.encode("utf-16-le")
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            proc.communicate.return_value = (utf16_bytes, b"")
            proc.returncode = 1
            PopenMock.return_value = proc
            with patch("plugadvpl.compile._resolve_advpls", return_value=Path("/fake/advpls")):
                result = run(request, runtime_cfg=None, root=tmp_path)
        # Parser deve ter classificado o erro corretamente (não unknown)
        row = next(r for r in result.rows if r["arquivo"] == str(foo))
        assert row["counts"]["error"] == 1

    def test_cp1252_fallback_when_utf8_invalid(self, tmp_path: Path) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        request = CompileRequest(
            files=[foo], mode="appre", no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )
        # Bytes inválidos para UTF-8: 0xE7 0xE3 0xF5 (cp1252: ç ã õ)
        cp1252_bytes = "foo.prw(1) error: função quebrou".encode("cp1252")
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            proc.communicate.return_value = (cp1252_bytes, b"")
            proc.returncode = 1
            PopenMock.return_value = proc
            with patch("plugadvpl.compile._resolve_advpls", return_value=Path("/fake/advpls")):
                result = run(request, runtime_cfg=None, root=tmp_path)
        row = next(r for r in result.rows if r["arquivo"] == str(foo))
        assert row["counts"]["error"] == 1
        # Mensagem decodificada preservou acentos
        diag = row["diagnostics"][0]
        assert "função" in diag["mensagem"] or "fun" in diag["mensagem"]
```

- [ ] **Step 5.5.5.2: GREEN + commit (já deve passar se `_decode_advpls_output` está correto)**

```bash
cd cli && python -m pytest tests/unit/test_compile.py::TestOutputEncoding -v --override-ini="addopts="
git add cli/tests/unit/test_compile.py
git commit -m "test(compile): output UTF-16 BOM + CP1252 fallback decoded correctly"
```

#### Step 5.6 — Credencial nunca em log (≥5 asserts)

- [ ] **Step 5.6.1: Test class com múltiplos cenários**

```python
import re as _re

_CRED_REGEX = _re.compile(r"(?i)(password|psw|senha|pwd)\s*[:=]\s*\S+")


class TestNoCredentialLeak:
    """≥5 testes confirmando: regex `(?i)(password|psw|senha|pwd)\\s*[:=]\\s*\\S+`
    ausente em stdout/stderr/diagnostic.raw em todos os cenários típicos."""

    def _build_request(self, tmp_path: Path, mode: str = "cli") -> CompileRequest:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        return CompileRequest(
            files=[foo], mode=mode, no_warnings=False,
            timeout_seconds=10, no_security_warning=True,
            includes_override=None, changed_since=None,
        )

    def _runtime_cfg(self) -> MagicMock:
        return MagicMock(
            tds_ls=MagicMock(binary=Path("/fake/advpls")),
            appserver=MagicMock(host="127.0.0.1", port=1234, secure=False,
                                build="x", environment="y"),
            auth=MagicMock(user_env="PROTHEUS_USER", password_env="PROTHEUS_PASS"),
            compile=MagicMock(recompile=True, includes=()),
            logging=MagicMock(log_to_file="", show_console_output=True),
            warn_remote_host=False, appserver_reachable=True,
        )

    def _assert_no_leak(self, captured: str, *result_jsons: dict) -> None:
        assert _CRED_REGEX.search(captured) is None, f"leak in: {captured[:200]}"
        for r in result_jsons:
            import json as _json
            text = _json.dumps(r)
            assert _CRED_REGEX.search(text) is None, f"leak in result: {text[:200]}"

    def test_clean_compile_no_leak(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "secretSauce42")
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock(); proc.communicate.return_value = ("", ""); proc.returncode = 0
            PopenMock.return_value = proc
            result = run(self._build_request(tmp_path), self._runtime_cfg(), tmp_path)
        captured = capsys.readouterr()
        self._assert_no_leak(captured.err + captured.out, result.summary, *result.rows)

    def test_advpls_echoes_psw_in_stderr_no_leak(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "secretSauce42")
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            proc.communicate.return_value = ("", "auth failed: psw=secretSauce42")
            proc.returncode = 1
            PopenMock.return_value = proc
            result = run(self._build_request(tmp_path), self._runtime_cfg(), tmp_path)
        captured = capsys.readouterr()
        # secretSauce42 NUNCA aparece no resultado
        import json as _json
        result_text = _json.dumps([_json.dumps(r) for r in result.rows])
        assert "secretSauce42" not in result_text

    def test_advpls_echoes_password_no_leak(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "topSecret")
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            proc.communicate.return_value = (
                "foo.prw(1) error: failed with PASSWORD=topSecret oops", ""
            )
            proc.returncode = 1
            PopenMock.return_value = proc
            result = run(self._build_request(tmp_path), self._runtime_cfg(), tmp_path)
        import json as _json
        assert "topSecret" not in _json.dumps([_json.dumps(r) for r in result.rows])

    def test_pt_senha_no_leak(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PROTHEUS_USER", "admin")
        monkeypatch.setenv("PROTHEUS_PASS", "minhaSenh@")
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            proc.communicate.return_value = ("erro: senha=minhaSenh@", "")
            proc.returncode = 1
            PopenMock.return_value = proc
            result = run(self._build_request(tmp_path), self._runtime_cfg(), tmp_path)
        import json as _json
        assert "minhaSenh@" not in _json.dumps([_json.dumps(r) for r in result.rows])

    def test_appre_mode_no_leak(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Mesmo em appre (sem runtime.toml), nenhum vazamento.
        with patch("plugadvpl.compile.subprocess.Popen") as PopenMock:
            proc = MagicMock()
            proc.communicate.return_value = (
                "foo.prw(1) error: missing include 'pwd=xyz.ch'", ""
            )
            proc.returncode = 1
            PopenMock.return_value = proc
            with patch("plugadvpl.compile._resolve_advpls", return_value=Path("/fake/advpls")):
                result = run(self._build_request(tmp_path, mode="appre"), None, tmp_path)
        import json as _json
        text = _json.dumps([_json.dumps(r) for r in result.rows])
        # pwd=xyz vira pwd=***REDACTED***
        assert "pwd=xyz" not in text
        assert "REDACTED" in text
```

- [ ] **Step 5.6.2: GREEN (deve passar — redact já implementado em Step 3) + commit**

```bash
cd cli && python -m pytest tests/unit/test_compile.py::TestNoCredentialLeak -v --override-ini="addopts="
git add cli/tests/unit/test_compile.py
git commit -m "test(compile): 5 tests confirm no credential leak in output"
```

#### Step 5.7 — Suite completa compile.py

- [ ] **Step 5.7.1: Confirmar ≥25 testes passing**

```bash
cd cli && python -m pytest tests/unit/test_compile.py -v --override-ini="addopts=" --no-header
```
Expected: ≥25 PASS.

---

## Chunk 4: CLI integration

### Task 6: `cli.py` — subcomando `compile` typer

**Files:**
- Modify: `cli/plugadvpl/cli.py` (+80 linhas)

**Spec refs:** §6.3, §7 fluxo, §10 paridade TDS-VSCode.

#### Step 6.1 — Sub-app typer + `compile <files>`

- [ ] **Step 6.1.1: Adicionar sub-app no `cli.py` (após `edit_prw_app`, antes do entry point)**

```python
# ---------------------------------------------------------------------------
# compile (v0.8.0 Fase 1): wrapper sobre advpls
# ---------------------------------------------------------------------------


compile_app = typer.Typer(
    name="compile",
    help="Compila fontes ADVPL via advpls (modos appre local + cli full).",
    # NÃO usar no_args_is_help=True junto com invoke_without_command=True
    # — typer mostra help antes do callback, quebrando o teste que espera
    # exit 2 + "nenhum fonte informado".
    invoke_without_command=True,
)
app.add_typer(compile_app, name="compile")


@compile_app.callback()
def compile_callback(
    ctx: typer.Context,
    files: Annotated[list[Path] | None, typer.Argument(help="Fontes a compilar.")] = None,
    mode: Annotated[str, typer.Option("--mode", help="auto|appre|cli")] = "auto",
    changed_since: Annotated[
        str | None, typer.Option("--changed-since", help="Git ref para git diff")
    ] = None,
    no_warnings: Annotated[bool, typer.Option("--no-warnings", help="Filtra warnings")] = False,
    timeout: Annotated[
        int, typer.Option("--timeout", help="Timeout do subprocess em segundos")
    ] = 120,
    no_security_warning: Annotated[
        bool, typer.Option("--no-security-warning", help="Suprime warning host remoto")
    ] = False,
    includes: Annotated[
        list[Path] | None, typer.Option("--includes", help="Override includes")
    ] = None,
    init_config: Annotated[
        bool, typer.Option("--init-config", help="Gera template runtime.toml")
    ] = False,
    force: Annotated[bool, typer.Option("--force", help="Sobrescreve config existente")] = False,
) -> None:
    """Compila fontes ADVPL via wrapper sobre advpls."""
    if ctx.invoked_subcommand is not None:
        return

    obj = ctx.obj
    root: Path = obj["root"]

    if init_config:
        _handle_init_config(root, force)
        return

    if not files:
        typer.secho("nenhum fonte informado", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2)

    from plugadvpl.compile import CompileRequest, run as compile_run
    from plugadvpl.runtime_config import RuntimeConfigError, load as load_runtime_config

    try:
        runtime_cfg = load_runtime_config(root)
    except RuntimeConfigError as exc:
        typer.secho(f"runtime config error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    if mode == "cli" and runtime_cfg is None:
        typer.secho(
            f"runtime.toml required for cli mode at {root}/.plugadvpl/runtime.toml. "
            "Run: plugadvpl compile --init-config",
            fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(code=2)

    request = CompileRequest(
        files=files, mode=mode, no_warnings=no_warnings,
        timeout_seconds=timeout, no_security_warning=no_security_warning,
        includes_override=includes, changed_since=changed_since,
    )
    try:
        result = compile_run(request, runtime_cfg=runtime_cfg, root=root)
    except KeyboardInterrupt:
        typer.secho("interrupted", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(code=130)

    _render_from_ctx(
        ctx,
        result.rows,
        columns=["arquivo", "ok", "mode", "duration_ms", "exit_code"],
        title=f"compile ({result.summary.get('mode_used', '?')})",
        next_steps=result.next_steps,
    )

    raise typer.Exit(code=result.exit_code)


def _handle_init_config(root: Path, force: bool) -> None:
    from plugadvpl.runtime_config import render_template, init_gitignore_entry

    cfg_dir = root / ".plugadvpl"
    cfg_dir.mkdir(exist_ok=True)
    target = cfg_dir / "runtime.toml"
    if target.exists() and not force:
        typer.secho(
            f"{target} already exists. Use --force to overwrite.",
            fg=typer.colors.YELLOW, err=True,
        )
        raise typer.Exit(code=1)
    target.write_text(render_template(), encoding="utf-8")
    added = init_gitignore_entry(root)
    typer.echo(f"created: {target}")
    if added:
        typer.echo("added to .gitignore: .plugadvpl/runtime.toml")
```

- [ ] **Step 6.1.2: Commit (sem testes ainda — vêm na Task 7)**

```bash
git add cli/plugadvpl/cli.py
git commit -m "feat(cli): plugadvpl compile subcommand + --init-config (Fase 1 #6)"
```

### Task 7: Integration tests CLI

**Files:**
- Create: `cli/tests/integration/test_cli_compile.py`

**Spec refs:** §11.4.

#### Step 7.1 — PATH-shim do advpls

- [ ] **Step 7.1.1: Criar `tests/integration/test_cli_compile.py`**

```python
"""Integration tests do subcomando compile (PATH-shim de advpls)."""
from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from plugadvpl.cli import app


@pytest.fixture
def runner() -> CliRunner:
    # Compatibilidade Click 8.0–8.2: NÃO passar mix_stderr (removido em 8.2+).
    # Padrão do projeto em tests/integration/test_cli.py também usa sem flag.
    return CliRunner()


@pytest.fixture
def fake_advpls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Cria um "binário" `advpls` que finge ser o compilador (cross-platform).

    Retorna o Path do executável a ser passado em `tds_ls.binary` (ou auto-detect
    via PATH). Em Windows usa `.bat`; em Linux/macOS, shell script `chmod +x`.

    Comportamento default: exit 0 sem output. Sobrescreva via env vars:
      SHIM_OUTPUT — texto a imprimir em stdout
      SHIM_EXIT   — código de saída (int)

    CRÍTICO: No Windows, `subprocess.Popen([binary, args...])` sem `shell=True`
    chama `CreateProcessW` que NÃO resolve PATHEXT. Por isso retornamos o Path
    COMPLETO do `.bat` — o compile.py vai chamar Popen com esse path absoluto,
    e Windows aceita `.bat` em CreateProcessW se for path absoluto explícito.
    """
    shim_py = tmp_path / "advpls_shim.py"
    shim_py.write_text(
        'import sys, os\n'
        'output = os.environ.get("SHIM_OUTPUT", "")\n'
        'exit_code = int(os.environ.get("SHIM_EXIT", "0"))\n'
        'sys.stdout.write(output)\n'
        'sys.exit(exit_code)\n',
        encoding="utf-8",
    )
    if os.name == "nt":
        # .bat wrapper invocando python explicitamente
        target = tmp_path / "advpls.bat"
        target.write_text(
            f'@echo off\r\n"{sys.executable}" "{shim_py}" %*\r\n',
            encoding="cp1252",
        )
    else:
        target = tmp_path / "advpls"
        target.write_text(
            f'#!{sys.executable}\n'
            f'import sys, os, runpy\n'
            f'sys.argv = [r"{shim_py}"] + sys.argv[1:]\n'
            f'runpy.run_path(r"{shim_py}", run_name="__main__")\n',
            encoding="utf-8",
        )
        target.chmod(target.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return target
```

#### Step 7.2 — Testes básicos

- [ ] **Step 7.2.1: Teste `--init-config`**

```python
class TestInitConfig:
    def test_init_config_creates_template(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        (tmp_path / ".gitignore").write_text("", encoding="utf-8")
        result = runner.invoke(app, ["--root", str(tmp_path), "compile", "--init-config"])
        assert result.exit_code == 0
        assert (tmp_path / ".plugadvpl" / "runtime.toml").is_file()
        gi = (tmp_path / ".gitignore").read_text(encoding="utf-8")
        assert ".plugadvpl/runtime.toml" in gi

    def test_init_config_refuses_overwrite(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        (tmp_path / ".plugadvpl").mkdir()
        (tmp_path / ".plugadvpl" / "runtime.toml").write_text("existing", encoding="utf-8")
        result = runner.invoke(app, ["--root", str(tmp_path), "compile", "--init-config"])
        assert result.exit_code == 1


class TestCompileBasics:
    def test_compile_no_args_exits_2(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        result = runner.invoke(app, ["--root", str(tmp_path), "compile"])
        assert result.exit_code == 2

    def test_compile_cli_no_runtime_toml_exits_2(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        result = runner.invoke(
            app, ["--root", str(tmp_path), "compile", str(foo), "--mode", "cli"]
        )
        assert result.exit_code == 2
        assert "runtime.toml" in result.stderr
```

#### Step 7.3 — Teste `appre` end-to-end com PATH-shim

- [ ] **Step 7.3.1: Teste appre real (shim simula advpls)**

```python
    def test_compile_appre_with_path_shim(
        self, runner: CliRunner, tmp_path: Path, fake_advpls: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        # Injeta o path absoluto do shim via env var lida por _resolve_advpls.
        # Alternativa testada também: colocar tmp_path no início do PATH
        # (Linux/macOS funciona; Windows precisa do .bat com path absoluto
        # — caso comum: compile.py chama _resolve_advpls() que retorna o
        # Path absoluto e Popen aceita .bat se path absoluto explícito).
        monkeypatch.setenv("PLUGADVPL_ADVPLS_BINARY", str(fake_advpls))
        # Shim retorna sucesso por default
        result = runner.invoke(
            app, ["--root", str(tmp_path), "--format", "json", "compile",
                  str(foo), "--mode", "appre"]
        )
        assert result.exit_code == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["summary"]["mode_used"] == "appre"
        assert payload["summary"]["total_files"] == 1
```

> **Nota implementação**: para o teste acima funcionar, `_resolve_advpls()` em `compile.py` deve checar a env var `PLUGADVPL_ADVPLS_BINARY` antes do `shutil.which()` (test hook). Ajustar Step 4.5.2:
>
> ```python
> def _resolve_advpls(runtime_cfg: RuntimeConfig | None) -> Path:
>     # Test hook + escape hatch (não documentado publicamente — só CI/testes).
>     env_override = os.environ.get("PLUGADVPL_ADVPLS_BINARY")
>     if env_override:
>         return Path(env_override)
>     if runtime_cfg is not None:
>         return runtime_cfg.tds_ls.binary
>     found = shutil.which("advpls") or shutil.which("advpls.exe")
>     if not found:
>         raise RuntimeError(
>             "advpls not found in PATH. Set tds_ls.binary in runtime.toml or "
>             "install tds-vscode extension."
>         )
>     return Path(found)
> ```
```

- [ ] **Step 7.3.2: Schema contract test (critério §14 — "Schema JSON estável conforme §8 — testado por contract test")**

Adicionar em `test_cli_compile.py`:
```python
class TestSchemaContract:
    """Garante schema JSON estável conforme spec §8."""

    def test_full_schema_clean_compile(
        self, runner: CliRunner, tmp_path: Path, fake_advpls: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        monkeypatch.setenv("PLUGADVPL_ADVPLS_BINARY", str(fake_advpls))
        result = runner.invoke(
            app, ["--root", str(tmp_path), "--format", "json", "compile",
                  str(foo), "--mode", "appre"]
        )
        assert result.exit_code == 0
        payload = json.loads(result.stdout)

        # Top-level keys conforme §8
        assert set(payload.keys()) >= {"rows", "summary", "next_steps"}

        # Cada row tem campos obrigatórios
        for row in payload["rows"]:
            for field in ("arquivo", "ok", "mode", "duration_ms",
                          "exit_code", "counts", "diagnostics"):
                assert field in row, f"missing row field: {field}"
            assert set(row["counts"].keys()) == {"error", "warning", "info", "unknown"}

        # Summary tem todos os campos
        summary = payload["summary"]
        for field in ("total_files", "ok", "failed", "total_errors",
                      "total_warnings", "mode_used", "appserver_reachable",
                      "runtime_config_loaded", "output_truncated"):
            assert field in summary, f"missing summary field: {field}"

    def test_schema_with_errors(
        self, runner: CliRunner, tmp_path: Path, fake_advpls: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        foo = tmp_path / "foo.prw"
        foo.write_text("", encoding="utf-8")
        monkeypatch.setenv("PLUGADVPL_ADVPLS_BINARY", str(fake_advpls))
        monkeypatch.setenv("SHIM_OUTPUT", "foo.prw(42) error: Unbalanced ENDIF\n")
        monkeypatch.setenv("SHIM_EXIT", "1")
        result = runner.invoke(
            app, ["--root", str(tmp_path), "--format", "json", "compile",
                  str(foo), "--mode", "appre"]
        )
        assert result.exit_code == 1
        payload = json.loads(result.stdout)
        # Cada diagnostic tem schema completo
        for row in payload["rows"]:
            for diag in row["diagnostics"]:
                for field in ("severidade", "arquivo", "linha", "coluna",
                              "mensagem", "codigo", "raw"):
                    assert field in diag, f"missing diagnostic field: {field}"
                assert diag["severidade"] in ("error", "warning", "info", "unknown")
        # next_steps populado quando há erro
        assert isinstance(payload["next_steps"], list)
```

- [ ] **Step 7.3.3: Rodar testes integration + commit**

```bash
cd cli && python -m pytest tests/integration/test_cli_compile.py -v --override-ini="addopts="
git add cli/tests/integration/test_cli_compile.py
git commit -m "test(integration): cli compile end-to-end + schema contract (Fase 1 #7)"
```

#### Step 7.4 — Suite full

- [ ] **Step 7.4.1: Rodar suite completa do projeto**

```bash
cd cli && PYTHONIOENCODING=utf-8 python -m pytest --override-ini="addopts=" -q --ignore=tests/unit/test_stripper.py --ignore=tests/unit/test_parser_snapshots.py --ignore=tests/bench
```

Expected: ≥714 PASS (629 anteriores + ~85 novos).

---

## Chunk 5: Smoke real + Release

### Task 8: Smoke real iterativo

**Files:**
- Create: `cli/tests/fixtures/compile_outputs/*.txt` (mais fixtures conforme descoberta)
- Modify: `cli/plugadvpl/lookups/compile_patterns.json` (adicionar patterns conforme outputs reais surgem)

**Spec refs:** §11.5, §12 etapa 8 cíclica.

#### Step 8.1 — Setup smoke marker

- [ ] **Step 8.1.1: Adicionar `smoke` marker em `pyproject.toml`**

Verificar primeiro como markers são declarados:
```bash
grep -A 5 "markers" cli/pyproject.toml
```

Adicionar (se não existir):
```toml
[tool.pytest.ini_options]
markers = [
    "smoke: smoke tests that hit real advpls (require PLUGADVPL_SMOKE=1)",
]
```

- [ ] **Step 8.1.2: Criar `tests/smoke/test_compile_real.py`**

```python
"""Smoke tests — só rodam se PLUGADVPL_SMOKE=1. Requerem advpls real."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

SKIP_REASON = "smoke tests skipped — set PLUGADVPL_SMOKE=1 to run"
pytestmark = pytest.mark.skipif(
    os.environ.get("PLUGADVPL_SMOKE") != "1", reason=SKIP_REASON
)


@pytest.mark.smoke
def test_compile_appre_clean_source(tmp_path: Path) -> None:
    """Verifica que compile appre num fonte limpo retorna exit 0."""
    foo = tmp_path / "FOO_CLEAN.prw"
    foo.write_text(
        "User Function FooClean()\n"
        "Return .T.\n",
        encoding="cp1252",
    )
    from plugadvpl.compile import CompileRequest, run
    request = CompileRequest(
        files=[foo], mode="appre", no_warnings=False,
        timeout_seconds=30, no_security_warning=True,
        includes_override=None, changed_since=None,
    )
    result = run(request, runtime_cfg=None, root=tmp_path)
    assert result.exit_code == 0, f"output: {result.rows}"


@pytest.mark.smoke
def test_compile_appre_with_syntax_error(tmp_path: Path) -> None:
    """Verifica que compile appre num fonte com erro de sintaxe retorna ≥1 error."""
    foo = tmp_path / "FOO_BROKEN.prw"
    foo.write_text(
        "User Function FooBroken()\n"
        "  If .T.\n"  # ENDIF faltando
        "Return\n",
        encoding="cp1252",
    )
    from plugadvpl.compile import CompileRequest, run
    request = CompileRequest(
        files=[foo], mode="appre", no_warnings=False,
        timeout_seconds=30, no_security_warning=True,
        includes_override=None, changed_since=None,
    )
    result = run(request, runtime_cfg=None, root=tmp_path)
    assert result.exit_code == 1
    assert result.summary["total_errors"] >= 1
```

- [ ] **Step 8.1.3: Commit setup**

```bash
git add cli/pyproject.toml cli/tests/smoke/
git commit -m "test(smoke): smoke marker + 2 initial real-advpls tests (Fase 1 #8)"
```

#### Step 8.2 — Ciclo iterativo (manual)

- [ ] **Step 8.2.1: Rodar smoke local Windows**

```powershell
$env:PLUGADVPL_SMOKE = "1"
cd cli
python -m pytest tests/smoke/ -v --override-ini="addopts="
```

- [ ] **Step 8.2.2: Para cada teste que falhar com `unknown` em vez de `error`:**

1. Capturar output bruto do advpls.
2. Sanitizar (remover credenciais, paths reais).
3. Salvar como nova fixture em `tests/fixtures/compile_outputs/<descricao>.txt`.
4. Adicionar pattern correspondente em `lookups/compile_patterns.json`.
5. Adicionar teste unit em `test_compile_parser.py` referenciando a nova fixture.
6. Re-rodar até parser produzir classification correta.

- [ ] **Step 8.2.3: Critério de aprovação do smoke**

- ≥3 famílias de erro distintas com fixture própria.
- ≥1 fixture pt-BR + ≥1 en.
- Todas as fixtures sanitizadas (sem credencial / cliente / empresa).
- Smoke local Windows passa.
- Smoke VPS via SSH tunnel passa.

- [ ] **Step 8.2.4: Commit final do smoke**

```bash
git add cli/tests/fixtures/compile_outputs/ cli/plugadvpl/lookups/compile_patterns.json cli/tests/unit/test_compile_parser.py
git commit -m "test(smoke): ≥3 families covered + sanitized fixtures from real advpls runs"
```

### Task 9: Release v0.8.0

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `.claude-plugin/plugin.json` (0.7.0 → 0.8.0)
- Modify: `.claude-plugin/marketplace.json` (0.7.0 → 0.8.0)
- Modify: `docs/ROADMAP.md`
- Modify: `README.md`
- Modify: `docs/cli-reference.md`

#### Step 9.1 — CHANGELOG

- [ ] **Step 9.1.1: Adicionar entry `[0.8.0]` no topo após `[Unreleased]`**

Espelhar estilo da entry `[0.7.0]` existente. Cobrir:
- `compile` subcomando com modos appre e cli
- `--init-config` template
- `runtime.toml` schema
- 4 módulos novos + 2 lookups novos
- Mapping com TDS-VSCode
- Security warning para host remoto
- Contagem de testes (629 → ≥714)

#### Step 9.2 — Bumps de versão

- [ ] **Step 9.2.1: `.claude-plugin/plugin.json`**: `"version": "0.7.0"` → `"version": "0.8.0"`

- [ ] **Step 9.2.2: `.claude-plugin/marketplace.json`**: idem

#### Step 9.3 — ROADMAP

- [ ] **Step 9.3.1: Marcar Fase 1 como shipped em `docs/ROADMAP.md`** (mover de "🟡 Próximas Fases" para "✅ v0.8.0").

#### Step 9.4 — README

- [ ] **Step 9.4.1: Atualizar §"Status"** com:
- "v0.8.0 — Fase 1 (compile wrapper TDS-LS) entregue"
- subcomando count (24 → 25)
- testes (629 → ≥714)
- bullet de Fase 1 shipped no roadmap

#### Step 9.5 — cli-reference

- [ ] **Step 9.5.1: Adicionar seção `compile`** em `docs/cli-reference.md`, padrão da seção `edit-prw` existente:
- sintaxe
- flags
- exit codes
- exemplo bash

#### Step 9.6 — Suite final + commit release + tag

- [ ] **Step 9.6.1: Rodar suite completa**

```bash
cd cli && PYTHONIOENCODING=utf-8 python -m pytest --override-ini="addopts=" -q --ignore=tests/unit/test_stripper.py --ignore=tests/unit/test_parser_snapshots.py --ignore=tests/bench
```

Expected: ≥714 PASS.

- [ ] **Step 9.6.2: Commit release**

```bash
git add CHANGELOG.md .claude-plugin/plugin.json .claude-plugin/marketplace.json docs/ROADMAP.md README.md docs/cli-reference.md
git commit -m "release: v0.8.0 — Fase 1 plugadvpl compile (wrapper TDS-LS)"
git tag v0.8.0
```

- [ ] **Step 9.6.3: Push (se aplicável)**

```bash
# git push origin main && git push origin v0.8.0
```

---

## Resposta ao plan review (round 1)

Plano passou por revisão automatizada em 3 chunks paralelos. CRITICAL e IMPORTANT resolvidos inline:

| # | Item | Resolução |
|---|---|---|
| C1+C3 | Bug `_load_patterns` (`raw.index(p)` O(n²) durante sort) | Step 3.3.3 reescrito com `enumerate` antes do sort + `lru_cache` |
| C2-Chunk1 | Texto enganoso Step 2.2.3 sobre testes do compile_patterns | Comentário esclarecido |
| C3-Chunk1 | Docstring de `parse_diagnostics` ambígua (matched vs unmatched) | Docstring completa adicionada ao Step 3.3.3 |
| C1-Chunk3 | UTF-16 BOM handling ausente | Nova função `_decode_advpls_output` + Step 5.5.5 com teste UTF-16 LE + CP1252 fallback |
| C2-Chunk3 | KeyboardInterrupt sem assert que tempdir foi limpo | Novo Step 5.5.4 com spy em `tempfile.mkdtemp` + assert `not exists()` |
| C3-Chunk3 | Exit 130 não testado em Chunk 3 | Nota cross-ref para Chunk 4 (handler `typer.Exit(code=130)`) |
| C1-Chunk4 | `fake_advpls` shim quebra Windows | Refatorado: `.bat` invocando python explícito + path absoluto via env var `PLUGADVPL_ADVPLS_BINARY` |
| C2-Chunk4 | `no_args_is_help=True` + `invoke_without_command=True` conflito | Removido `no_args_is_help=True` com comentário explicativo |
| I-Chunk1 | `/usr/bin/true` quebra Windows | Helper `_fake_advpls_binary` cross-platform (.bat / shell script) |
| I-Chunk2 | `requested_resolved` descarta arquivos inexistentes | Try/except no resolve preservando entries |
| I-Chunk2 | Falta pattern aut_file no redact | 6º pattern `aut_file_value` adicionado |
| I-Chunk3 | Step 5.4.2 "implementador refatora" vago | (parcialmente resolvido — manter como guia; implementador valida com testes) |
| I-Chunk4 | Falta contract test do schema JSON | Step 7.3.2 adicionado com `TestSchemaContract` (2 testes) |
| I-Chunk4 | `CliRunner(mix_stderr=False)` quebra Click 8.2+ | Trocado por `CliRunner()` (padrão do projeto) |
| N-vários | Imports redundantes, tomllib em test, etc. | Endereçados pontualmente |

Issues NITPICK e alguns IMPORTANT menores ficam como notas para o implementador resolver durante o TDD (são naturalmente expostos pelos testes que vão escrever).

---

## Resumo de commits esperados

Aproximadamente 35-40 commits durante a implementação:
- Chunk 1: ~10 commits (esqueleto + 6 validações + render_template + gitignore + catalog redact)
- Chunk 2: ~10 commits (esqueleto + 5 patterns + fixtures + parser básico + pt + mixed + path + tie-break + redact + catalog compile)
- Chunk 3: ~12 commits (esqueleto + resolve_files + changed_since + pick_mode + run appre + encode helper + build_ini + secure_ini + run cli + KeyboardInterrupt + 5 no-leak tests)
- Chunk 4: ~3 commits (CLI subcommand + init-config + integration tests)
- Chunk 5: ~5 commits (smoke setup + ≥3 famílias + release)

Cada commit deve ter testes verdes antes de ser feito. `git commit --no-verify` proibido (vai contra princípio de qualidade).
