# Security Hardening (Auditoria 2026-06-09) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar os 6 itens do plano de ação da auditoria `docs/auditoria-seguranca-2026-06-09.md` (A1–A6), um por vez, com TDD e um commit por item.

**Architecture:** Cada item é uma mudança pequena e independente no CLI Python (`cli/plugadvpl`), nos workflows de CI ou nos scripts de bootstrap. Não há feature nova — só endurecimento de código existente, preservando comportamento default onde possível (exceção: A1 muda o default de execução do `restart_cmd` para sem shell, com opt-in explícito).

**Tech Stack:** Python 3.11+ (typer, pytest, uv), GitHub Actions, PowerShell/bash (scripts de install).

**Convenções do projeto que o executor DEVE respeitar:**
- Testes: `cd cli && uv run pytest tests/unit/<arquivo> -q` (nunca mascarar exit code com pipe).
- Lint: `cd cli && uv run ruff check <arquivos tocados>` antes de cada commit.
- Commits convencionais (`fix(escopo): ...`) — CHANGELOG é gerado por git-cliff no release.
- Arquivos Python são UTF-8 (não são .prw — o fluxo edit-prw NÃO se aplica aqui).
- Branch de trabalho: `fix/security-hardening` a partir de `main` atualizado.
- ATENÇÃO (memória do projeto): o token do `gh` pode não ter scope `workflow`. O push de commit que toca `.github/workflows/` pode ser rejeitado. Por isso o item A5 fica em commit separado (Task 4) e, se o push falhar com erro de OAuth/workflow scope, rodar `gh auth refresh -s workflow` ou avisar o usuário — NÃO abandonar os outros commits.

---

## Chunk 1: Setup + P1 (A2 zip-slip, A1 shell=True)

### Task 0: Branch de trabalho

**Files:** nenhum (git apenas)

- [ ] **Step 0.1:** `git checkout main` e conferir com `git branch --show-current` (nunca encadear com `&&` — memória do projeto).
- [ ] **Step 0.2:** `git pull origin main`
- [ ] **Step 0.3:** `git checkout -b fix/security-hardening` e conferir `git branch --show-current` → `fix/security-hardening`.

Os arquivos untracked em `docs/` (estratégias de segurança, HTMLs) não fazem parte deste plano — deixar untracked.

---

### Task 1: A2 — Guarda de zip-slip na extração do `.vsix`

**Files:**
- Modify: `cli/plugadvpl/compile_installer.py:240-248` (loop de extração)
- Test: `cli/tests/unit/test_compile_installer.py` (classe dos testes de download, ~linha 137; reusar o helper de zip fake ~linha 128)

- [ ] **Step 1.1: Escrever o teste que falha.** Colocar dentro da classe `TestExecuteDownload`, seguindo o padrão de `test_download_extracts_only_bin_subdir` (monkeypatch de `Path.home` + `patch("plugadvpl.compile_installer.urllib.request.urlretrieve", ...)`). ATENÇÃO (verificado pelo revisor): o helper existente `_make_fake_vsix(self, tmp_path)` NÃO aceita dict de membros — construir o zip malicioso **inline** com `zipfile.ZipFile` gravando em `tmp_path` (mesmo estilo do helper), importando `_VSIX_ADVPLS_REL`/`_os_subdir` **localmente dentro do teste** (padrão do arquivo) e `shutil` no escopo necessário. O zip malicioso tem um membro cujo nome começa com o prefixo válido mas escapa via `..`:

```python
def test_download_rejects_zip_slip_member(
    self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Membro do .vsix com '..' no path nao pode escrever fora do target_dir."""
    import shutil
    import zipfile

    from plugadvpl.compile_installer import _VSIX_ADVPLS_REL, _os_subdir

    monkeypatch.setattr(Path, "home", lambda: tmp_path / "fake_home")
    prefix = f"{_VSIX_ADVPLS_REL}/{_os_subdir()}"
    evil_vsix = tmp_path / "evil.vsix"
    with zipfile.ZipFile(evil_vsix, "w", zipfile.ZIP_DEFLATED) as zf:
        # membro legítimo (pro plano achar o prefixo) + membro malicioso
        zf.writestr(f"{prefix}/advpls.exe", b"fake binary")
        zf.writestr(f"{prefix}/../../../../evil.txt", b"pwned")

    def fake_retrieve(url, dst):  # noqa: ARG001
        shutil.copy(evil_vsix, dst)

    with patch(
        "plugadvpl.compile_installer.urllib.request.urlretrieve", fake_retrieve
    ):
        plan = ...  # copiar o setup EXATO de test_download_extracts_only_bin_subdir
        result = execute_download(plan)

    assert result.ok is False
    assert "path traversal" in result.error
    # Assert load-bearing: com 4 níveis de '..' o arquivo cairia dentro de
    # fake_home — é o rglob que detecta a regressão pré-fix:
    assert not list((tmp_path / "fake_home").rglob("evil.txt"))
```

> Nota ao executor: o setup de `plan` deve ser copiado do teste vizinho `test_download_extracts_only_bin_subdir` — NÃO inventar assinatura.

- [ ] **Step 1.2: Rodar e ver falhar.** `cd cli && uv run pytest tests/unit/test_compile_installer.py -q` — o teste novo deve FALHAR (hoje o arquivo é escrito fora do target ou o resultado é ok=True).
- [ ] **Step 1.3: Implementação mínima.** Em `compile_installer.py`, dentro do loop de extração, antes de escrever:

```python
resolved_root = target_dir.resolve()
for member in members:
    # member ex: extension/node_modules/.../bin/windows/advpls.exe
    rel = member[len(prefix) :]
    if not rel:  # entry da pasta vazia
        continue
    dst = target_dir / rel
    # Guarda anti zip-slip: membro com ".." não pode escapar do target_dir
    if not dst.resolve().is_relative_to(resolved_root):
        return InstallResult(
            ok=False,
            binary_path=None,
            bytes_written=0,
            error=f"membro suspeito no .vsix (path traversal): {member!r}",
        )
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zf.open(member) as src, dst.open("wb") as out:
        shutil.copyfileobj(src, out)
```

(`Path.is_relative_to` existe desde 3.9; `requires-python = ">=3.11"` — ok.)

- [ ] **Step 1.4: Rodar o arquivo de teste inteiro.** `cd cli && uv run pytest tests/unit/test_compile_installer.py -q` → todos PASS (os testes existentes de extração legítima continuam verdes).
- [ ] **Step 1.5: Lint + commit.**

```bash
cd cli && uv run ruff check plugadvpl/compile_installer.py tests/unit/test_compile_installer.py
git add cli/plugadvpl/compile_installer.py cli/tests/unit/test_compile_installer.py
git commit -m "fix(installer): guarda anti zip-slip na extração do .vsix (auditoria A2)"
```

---

### Task 2: A1 — `restart_cmd` sem `shell=True` por padrão (opt-in `--restart-shell`)

**Files:**
- Modify: `cli/plugadvpl/compile_servers.py:38` (novo campo `restart_shell` no dataclass `Server`)
- Modify: `cli/plugadvpl/tq.py:88-104` (execução sem shell por default)
- Modify: `cli/plugadvpl/cli.py:4863-4976` (opção `--restart-shell` junto de `--set-restart-cmd`) e `cli/plugadvpl/cli.py:5723-5751` (`_handle_set_restart_cmd`)
- Test: `cli/tests/unit/test_tq.py`, `cli/tests/unit/test_compile_servers.py`

**Design (decidido na auditoria):**
- Default novo: `shell=False`. No Windows passa a **string** direto (`CreateProcess` faz o parse e executa `.exe`/`.bat`); em POSIX usa `shlex.split()`.
- Opt-in: campo `Server.restart_shell: bool = False`, configurado via `--set-restart-cmd ... --restart-shell`, mantém `shell=True` para quem precisa de pipes/`&&`/builtins.
- Compat: registries antigos sem a chave carregam com default `False` (mesmo padrão dos campos v0.14/v0.15). Comandos que dependiam de shell passam a falhar com mensagem orientando o `--restart-shell` — documentar no corpo do commit.

- [ ] **Step 2.1: Testes que falham em `test_tq.py`** (seguir padrão `_make_server` + monkeypatch existente; atualizar `_make_server` para aceitar `restart_shell: bool = False`; **adicionar `import os` no topo do arquivo de teste** — hoje ele não importa `os` e os testes novos usam `os.name`):

```python
class TestRestartShellMode:
    """run_tq executa restart_cmd sem shell por default (auditoria A1)."""

    def test_default_does_not_use_shell(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sem restart_shell, subprocess.run NUNCA recebe shell=True."""
        srv = _make_server(restart_cmd="echo restart")
        fake_run = mock.MagicMock(return_value=mock.MagicMock(returncode=0, stderr=""))
        monkeypatch.setattr("plugadvpl.tq.subprocess.run", fake_run)
        run_tq(srv, timeout_s=60, no_healthcheck=True)
        assert fake_run.call_args.kwargs.get("shell") is False
        # Em POSIX o comando vira lista; no Windows permanece string
        cmd_arg = fake_run.call_args.args[0]
        if os.name == "nt":
            assert cmd_arg == "echo restart"
        else:
            assert cmd_arg == ["echo", "restart"]

    def test_restart_shell_optin_uses_shell(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Com restart_shell=True, comportamento legado (shell=True) preservado."""
        srv = _make_server(restart_cmd="a && b", restart_shell=True)
        fake_run = mock.MagicMock(return_value=mock.MagicMock(returncode=0, stderr=""))
        monkeypatch.setattr("plugadvpl.tq.subprocess.run", fake_run)
        run_tq(srv, timeout_s=60, no_healthcheck=True)
        assert fake_run.call_args.kwargs.get("shell") is True
        assert fake_run.call_args.args[0] == "a && b"

    def test_binary_not_found_returns_error_with_hint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """shell=False levanta FileNotFoundError → TqResult ok=False com hint --restart-shell."""
        srv = _make_server(restart_cmd="nao-existe-xyz --flag")
        monkeypatch.setattr(
            "plugadvpl.tq.subprocess.run",
            mock.MagicMock(side_effect=FileNotFoundError("nao-existe-xyz")),
        )
        result = run_tq(srv, timeout_s=60, no_healthcheck=True)
        assert result.ok is False
        assert "--restart-shell" in result.error

    def test_unbalanced_quotes_returns_error(self) -> None:
        """POSIX: shlex.split com aspas desbalanceadas não pode estourar exceção crua."""
        if os.name == "nt":
            pytest.skip("shlex.split só é usado em POSIX")
        srv = _make_server(restart_cmd="echo 'aberto")
        result = run_tq(srv, timeout_s=60, no_healthcheck=True)
        assert result.ok is False
        assert result.restart_exit_code == -3
```

E em `test_compile_servers.py`, compat de registry antigo:

```python
def test_load_registry_without_restart_shell_key_defaults_false(tmp_path, monkeypatch):
    """servers.json gravado por versão antiga (sem restart_shell) carrega com False."""
    # seguir o padrão dos testes existentes do arquivo p/ apontar registry_path a tmp_path
```

- [ ] **Step 2.2: Rodar e ver falhar.** `cd cli && uv run pytest tests/unit/test_tq.py tests/unit/test_compile_servers.py -q` — novos testes FALHAM (`shell` é True hoje; `Server` não tem `restart_shell`).
- [ ] **Step 2.3: Implementar.**

`compile_servers.py` — adicionar após `is_prod`:

```python
restart_shell: bool = False  # v0.32: opt-in shell=True no restart_cmd (auditoria A1)
```

`tq.py` — adicionar `import os` e `import shlex` no topo; substituir o bloco de restart:

```python
    # Restart — sem shell por default (auditoria 2026-06-09, A1).
    # Windows: string direto (CreateProcess parseia e executa .exe/.bat).
    # POSIX: shlex.split. Opt-in shell=True via Server.restart_shell.
    restart_start = time.monotonic()
    try:
        if server.restart_shell:
            argv: str | list[str] = server.restart_cmd
            use_shell = True
        elif os.name == "nt":
            argv = server.restart_cmd
            use_shell = False
        else:
            argv = shlex.split(server.restart_cmd)
            use_shell = False
        proc = subprocess.run(
            argv,
            shell=use_shell,
            capture_output=True,
            text=True,
            timeout=timeout_s + 10,
            check=False,
        )
        restart_exit = proc.returncode
        restart_stderr = (proc.stderr or "").strip()
    except subprocess.TimeoutExpired:
        restart_exit = -2
        restart_stderr = f"restart_cmd timeout após {timeout_s + 10}s"
    except (OSError, ValueError) as exc:
        # OSError cobre FileNotFoundError (subclasse) — listar os dois reprova
        # no ruff B014. ValueError vem do shlex.split (aspas desbalanceadas).
        restart_exit = -3
        restart_stderr = (
            f"falha ao executar restart_cmd sem shell: {exc}. Se o comando usa "
            f"pipes/&&/redirecionamento, reconfigure com: plugadvpl compile "
            f"--set-restart-cmd {server.name} --cmd '...' --restart-shell"
        )
    restart_dur_ms = int((time.monotonic() - restart_start) * 1000)
```

> Nota: o caminho de erro `restart_exit != 0` já existente devolve `error=f"restart_cmd falhou (exit={restart_exit}): {restart_stderr}"` — o hint `--restart-shell` chega ao `TqResult.error` por aí; o teste 3 valida isso.

`cli.py` — junto da opção `--set-restart-cmd` (≈4863), adicionar:

```python
restart_shell: Annotated[
    bool,
    typer.Option(
        "--restart-shell",
        help="Com --set-restart-cmd: executa o comando via shell (pipes/&&). "
        "Default: execução direta, sem shell.",
    ),
] = False,
```

Encadear o valor até `_handle_set_restart_cmd(set_restart_cmd, cmd_value, restart_shell)` (≈4976) e em `_handle_set_restart_cmd` (≈5723): `new_srv = replace(srv, restart_cmd=cmd, restart_shell=use_shell)` + incluir no echo final se shell está ligado.

- [ ] **Step 2.4: Rodar.** `cd cli && uv run pytest tests/unit/test_tq.py tests/unit/test_compile_servers.py -q` → PASS. Rodar também `uv run pytest tests/unit -q -k "cli and tq or restart"` se existirem testes de CLI do tq.
- [ ] **Step 2.5: Lint + commit.**

```bash
cd cli && uv run ruff check plugadvpl/tq.py plugadvpl/compile_servers.py plugadvpl/cli.py tests/unit/test_tq.py tests/unit/test_compile_servers.py
git add -A cli/plugadvpl/tq.py cli/plugadvpl/compile_servers.py cli/plugadvpl/cli.py cli/tests/unit/test_tq.py cli/tests/unit/test_compile_servers.py
git commit -m "fix(tq)!: restart_cmd sem shell=True por default; opt-in --restart-shell (auditoria A1)" -m "BREAKING: comandos de restart que dependiam de pipes/&& precisam reconfigurar com --restart-shell. Erro orienta a migração."
```

---

## Chunk 2: P2 + P3 (A3, A5, A4, A6) e fechamento

### Task 3: A3 — Warning de Basic Auth sobre `http://` remoto no COLETADB

**Files:**
- Modify: `cli/plugadvpl/coletadb_client.py` (novo helper público `is_plaintext_remote_endpoint`)
- Modify: `cli/plugadvpl/cli.py:3011-3045` (comando `ingest-protheus`: emitir warning + flag `--no-security-warning`)
- Test: `cli/tests/unit/test_coletadb_client.py`

- [ ] **Step 3.1: Teste que falha** (helper puro, sem rede):

```python
class TestIsPlaintextRemoteEndpoint:
    """is_plaintext_remote_endpoint — warning de Basic Auth em claro (auditoria A3)."""

    @pytest.mark.parametrize(
        ("endpoint", "expected"),
        [
            ("http://10.0.0.5:8181/rest", True),
            ("http://protheus:8181/rest", True),
            ("http://127.0.0.1:8181/rest", False),
            ("http://localhost:8181/rest", False),
            ("http://[::1]:8181/rest", False),
            ("https://10.0.0.5:8181/rest", False),
            ("HTTP://PROTHEUS:8181/rest", True),
            ("http://127.0.0.2:8181/rest", False),  # toda a faixa 127/8 é loopback
        ],
    )
    def test_detection(self, endpoint: str, expected: bool) -> None:
        assert is_plaintext_remote_endpoint(endpoint) is expected
```

- [ ] **Step 3.2: Rodar e ver falhar** (ImportError — função não existe). `cd cli && uv run pytest tests/unit/test_coletadb_client.py -q`
- [ ] **Step 3.3: Implementar** em `coletadb_client.py`. ATENÇÃO (verificado pelo revisor): o módulo importa só `from urllib.error import ...` e `from urllib.request import ...` — o nome `urllib` NÃO está ligado; é preciso adicionar `from urllib.parse import urlsplit` aos imports:

```python
def is_plaintext_remote_endpoint(endpoint: str) -> bool:
    """True se ``endpoint`` é ``http://`` apontando pra host não-loopback.

    Nesse cenário o Basic Auth (user:password em base64) trafega em claro
    na rede — o caller deve avisar e recomendar HTTPS ou túnel SSH.
    """
    parsed = urlsplit(endpoint)
    if parsed.scheme.lower() != "http":
        return False
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "::1"}:
        return False
    return not host.startswith("127.")
```

Em `cli.py` (`ingest-protheus`), adicionar a opção (mesmo nome do flag já usado no compile, consistência):

```python
no_security_warning: Annotated[
    bool,
    typer.Option("--no-security-warning", help="Suprime aviso de endpoint http:// remoto"),
] = False,
```

E logo após a validação de `endpoint` (≈3017):

```python
from plugadvpl.coletadb_client import is_plaintext_remote_endpoint  # junto do import existente

if not no_security_warning and is_plaintext_remote_endpoint(endpoint):
    typer.secho(
        "WARNING: endpoint http:// em host não-local — user/password (Basic Auth) "
        "trafegam EM CLARO na rede. Use https:// ou túnel SSH "
        "(ssh -L 8181:localhost:8181 user@host -N) e aponte pra 127.0.0.1. "
        "(suprima com --no-security-warning)",
        fg=typer.colors.YELLOW,
        err=True,
    )
```

- [ ] **Step 3.4: Rodar.** `cd cli && uv run pytest tests/unit/test_coletadb_client.py -q` → PASS.
- [ ] **Step 3.5: Lint + commit.**

```bash
cd cli && uv run ruff check plugadvpl/coletadb_client.py plugadvpl/cli.py tests/unit/test_coletadb_client.py
git add cli/plugadvpl/coletadb_client.py cli/plugadvpl/cli.py cli/tests/unit/test_coletadb_client.py
git commit -m "fix(coletadb): avisa quando Basic Auth vai em claro (http:// remoto) (auditoria A3)"
```

---

### Task 4: A5 — `permissions: contents: read` no topo do `ci.yml` (commit separado!)

**Files:**
- Modify: `.github/workflows/ci.yml` (topo, após o bloco `on:`)

- [ ] **Step 4.1:** Inserir após o bloco `on:` (linhas 3-6):

```yaml
# Token mínimo por default (auditoria 2026-06-09, A5). O job `bench`
# declara override próprio (contents/pull-requests: write) pro gh-pages.
permissions:
  contents: read
```

- [ ] **Step 4.2: Validar sintaxe e semântica.** `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))"` (ou `uv run --with pyyaml`). Conferir que o job `bench` (linha ~163) mantém o override `contents: write` + `pull-requests: write`. Conferir que NENHUM outro job do ci.yml faz push/comment (lint, test, smoke, secret-scan só leem) — se algum fizer, dar override nele também.
- [ ] **Step 4.3: Commit separado** (token pode não ter scope workflow):

```bash
git add .github/workflows/ci.yml
git commit -m "ci: permissions contents:read por default no ci.yml (auditoria A5)"
```

Se o `git push` lá no final rejeitar ESTE commit por falta de scope `workflow` no token, rodar `gh auth refresh -s workflow` (interativo) ou, se não for possível, mover este commit pra uma branch própria e avisar o usuário — sem derrubar o resto do PR.

---

### Task 5: A4 — Aviso de chave-dev quando `--privacy` ativo sem `PLUGADVPL_PRIVACY_KEY`

**Files:**
- Modify: `cli/plugadvpl/privacy/config.py` (novo helper `dev_key_warning`)
- Modify: `cli/plugadvpl/cli.py:327` (callback principal: emitir o aviso uma vez)
- Test: `cli/tests/unit/test_privacy.py`

- [ ] **Step 5.1: Teste que falha:**

```python
class TestDevKeyWarning:
    """dev_key_warning — aviso de chave-dev previsível (auditoria A4)."""

    def test_warns_when_enabled_with_dev_key(self) -> None:
        cfg = PrivacyConfig(enabled=True)  # key default, key_explicit=False
        msg = dev_key_warning(cfg)
        assert msg is not None
        assert "PLUGADVPL_PRIVACY_KEY" in msg

    def test_silent_when_key_explicit(self) -> None:
        cfg = PrivacyConfig(enabled=True, key=b"x" * 32, key_explicit=True)
        assert dev_key_warning(cfg) is None

    def test_silent_when_disabled(self) -> None:
        assert dev_key_warning(PrivacyConfig(enabled=False)) is None
```

- [ ] **Step 5.2: Rodar e ver falhar.** `cd cli && uv run pytest tests/unit/test_privacy.py -q`
- [ ] **Step 5.3: Implementar** em `privacy/config.py`:

```python
def dev_key_warning(cfg: PrivacyConfig) -> str | None:
    """Mensagem de aviso quando o mascaramento usa a chave-dev default.

    Tokens HMAC com chave pública são previsíveis: CPF/CNPJ podem ser
    reconstruídos por força bruta de dicionário. Retorna ``None`` quando
    não há o que avisar (privacy off ou chave explícita).
    """
    if not cfg.enabled or cfg.key_explicit:
        return None
    return (
        "WARNING: --privacy ativo com a chave-dev default — tokens de CPF/CNPJ "
        "são previsíveis (reconstruíveis por dicionário). Defina "
        "PLUGADVPL_PRIVACY_KEY com um valor secreto pra tokens não-reversíveis."
    )
```

Em `cli.py` (≈327, logo após `ctx.obj["privacy"] = PrivacyConfig.from_env(...)`):

```python
_privacy_warning = dev_key_warning(ctx.obj["privacy"])
if _privacy_warning:
    typer.secho(_privacy_warning, fg=typer.colors.YELLOW, err=True)
```

(importar `dev_key_warning` junto do import existente de `PrivacyConfig`; exportar em `privacy/__init__.py` `__all__` se o import vier do pacote.)

- [ ] **Step 5.4: Rodar.** `cd cli && uv run pytest tests/unit/test_privacy.py -q` → PASS. Conferir que nenhum teste de determinismo (`test_privacy_determinism.py`) quebrou: `uv run pytest tests/unit -q -k privacy`.
- [ ] **Step 5.5: Lint + commit.**

```bash
cd cli && uv run ruff check plugadvpl/privacy/config.py plugadvpl/privacy/__init__.py plugadvpl/cli.py tests/unit/test_privacy.py
git add cli/plugadvpl/privacy/config.py cli/plugadvpl/privacy/__init__.py cli/plugadvpl/cli.py cli/tests/unit/test_privacy.py
git commit -m "fix(privacy): avisa quando --privacy roda com chave-dev default (auditoria A4)"
```

---

### Task 6: A6 — Pinnar o instalador do uv nos scripts de bootstrap

**Files:**
- Modify: `scripts/install.sh:15`
- Modify: `scripts/install.ps1:39,43`

- [ ] **Step 6.1: Descobrir a release atual do uv e os nomes REAIS dos assets** (não inventar):

```bash
gh api repos/astral-sh/uv/releases/latest --jq '.tag_name'
gh api repos/astral-sh/uv/releases/latest --jq '.assets[].name' | grep -i installer
```

Esperado: assets `uv-installer.sh` e `uv-installer.ps1`. **Se os nomes forem outros, usar os nomes reais retornados.** Se o `gh api` falhar (sem rede/credencial), PARAR esta task e marcar A6 como pendente — não chutar URL.

- [ ] **Step 6.2: Editar `install.sh`** — trocar a linha 15 por (com `<TAG>` real):

```bash
# Pinned (auditoria 2026-06-09, A6): URL de release imutável do GitHub em vez
# de https://astral.sh/uv/install.sh (sempre-latest). Bump junto com releases.
curl -LsSf "https://github.com/astral-sh/uv/releases/download/<TAG>/uv-installer.sh" | sh
```

- [ ] **Step 6.3: Editar `install.ps1`** — trocar as DUAS ocorrências (linhas 39 e 43) de `iex (irm https://astral.sh/uv/install.ps1)` por `iex (irm "https://github.com/astral-sh/uv/releases/download/<TAG>/uv-installer.ps1")` mantendo o fallback winget-primeiro intacto.
- [ ] **Step 6.4: Smoke local** (sem executar o instalador): `bash -n scripts/install.sh` (syntax check) e, no PowerShell, carregar o script com parse-only: `powershell -NoProfile -Command "$null = [System.Management.Automation.Language.Parser]::ParseFile('scripts/install.ps1', [ref]$null, [ref]$errs); $errs.Count"` → `0`. Conferir com `curl -sI` que a URL pinada responde 302/200.
- [ ] **Step 6.5: Commit.**

```bash
git add scripts/install.sh scripts/install.ps1
git commit -m "fix(scripts): pinna instalador do uv em release imutável do GitHub (auditoria A6)"
```

---

### Task 7: Fechamento — suite completa, doc da auditoria, PR

**Files:**
- Modify: `docs/auditoria-seguranca-2026-06-09.md` (marcar status dos itens)

- [ ] **Step 7.1: Suite completa com exit code real** (memória do projeto — sem pipes mascarando):

```bash
cd cli && uv run pytest tests/unit -q > /d/tmp/pytest-hardening.log; echo "EXIT=$?"; tail -5 /d/tmp/pytest-hardening.log
```

Esperado: `EXIT=0`. Se falhar, usar superpowers:systematic-debugging antes de qualquer correção.

- [ ] **Step 7.2: Ruff no escopo todo tocado:** `cd cli && uv run ruff check plugadvpl tests` → sem erros.
- [ ] **Step 7.3: Atualizar a tabela "Plano de ação sugerido" do `docs/auditoria-seguranca-2026-06-09.md`** adicionando coluna/nota "Status: implementado em <commit>" por item (A6 pode ficar "pendente" se Step 6.1 falhou). Commit: `docs(auditoria): marca itens A1-A6 implementados`.
- [ ] **Step 7.4: Push + PR.** `git push -u origin fix/security-hardening` (atenção ao cenário de scope workflow da Task 4). Abrir PR para `main` com `gh pr create` resumindo os 6 itens e linkando a auditoria. NÃO mergear sem o usuário ver.
