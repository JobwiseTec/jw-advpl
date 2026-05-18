# Fase 1 — `plugadvpl compile` (wrapper TDS-LS)

**Status:** design aprovado pelo autor (brainstorming) · pendente review automatizado + implementação
**Release alvo:** v0.8.0
**Audiência:** times ADVPL com pipeline CI ou que querem compilar fora do TDS-VSCode
**Dependência externa:** binário `advpls` (extensão tds-vscode ou `D:\TOTVS\protheus\bin\Appserver`)

Esse documento é a **spec** definitiva da Fase 1. O plano de implementação detalhado (tarefas, ordem, TDD red→green por item) será gerado em seguida via skill `superpowers:writing-plans`.

---

## 1. Contexto e motivação

Hoje o desenvolvedor ADVPL compila exclusivamente via TDS-VSCode (IDE proprietária TOTVS), ou via `tdscli.bat`/`tdscli.sh` legacy difícil de invocar em CI moderno. O plugin já entrega análise estática completa (24 subcomandos, 38 lint rules, dicionário SX, trace), mas para fechar o ciclo "indexar → compilar → executar → testar → deployar" sem abrir o TDS, falta a etapa runtime.

A **Fase 1** entrega o primeiro passo dessa cadeia: `plugadvpl compile <fonte...>` que invoca o binário oficial `advpls` (mesmo compilador da IDE) e devolve resultado **estruturado em JSON** para consumo por CI, scripts e — futuramente — agents Claude Code.

A Fase 0 (v0.7.0) já pavimentou o terreno: regras WS-001/002/003 + XF-001 + ENC-001 + comando `edit-prw` + contrato `U_EXEC` (referência impl MIT). A Fase 1 reusa diretamente o módulo `edit_prw.py` para escrita do script `.ini` em CP1252.

---

## 2. Pesquisa prévia (TDS-LS / advpls)

Consolidado em ~500 palavras de research independente. Pontos críticos:

- **`advpls`** é binário **proprietário** distribuído na extensão `tds-vscode` para Windows/Linux/macOS. Não há fork open-source funcional. Repos: `github.com/totvs/tds-ls` (deprecated, issues vão pro `tds-vscode`) + `github.com/totvs/tds-vscode`.

- **4 modos de operação**: `language-server` (LSP via stdin/stdout JSON-RPC), `cli` (executa script `.ini`), `appre` (pré-processador local, só gera `.ppo`), `tds-cli` (legacy Eclipse compat).

- **`cli` precisa AppServer rodando** (TCP), porque o RPO é gerado servidor-side. **`appre` roda 100% local** mas só detecta erros de pré-processamento (sintaxe + includes + defines).

- **Saída de erro NÃO é estruturada**: documentação oficial admite "output format not specified, exit codes not documented". Mensagens em texto livre pt-BR ou en, sem códigos estáveis (`E001`/`W003`). Modo LSP dá diagnostics JSON-RPC estruturados, mas é overkill para CI batch (lifecycle complexo, requer cliente LSP).

- **Encoding do `.ini`**: o `advpls` lê o script em **CP1252**. Editor em UTF-8 quebra senhas com acento — confirmado pelo autor ("gere o .ini com iconv -t CP1252").

- **Script `.ini` real** usado em produção (fornecido pelo autor):

```ini
logToFile=compile.log
showConsoleOutput=true

[auth]
action=authentication
server=187.77.46.221
port=1234
secure=0
build=7.00.240223P
environment=P2510
user=admin
psw=<senha>

[compile]
action=compile
program=/caminho/local/do/fonte.prw
recompile=T
includes=/caminho/local/includes
```

Invocação: `advpls cli compile.ini`.

- **Segurança**: porta 1234 TCP cru sem TLS. Recomendação do autor: **SSH tunnel local** (`ssh -L 1234:localhost:1234 user@host -N`) com `host=127.0.0.1` no `.ini`. Cloudflare Tunnel não roteia TCP por padrão (só HTTP/HTTPS) — não cobre o `cli` mode.

- **CI público conhecido**: só artigo de Sibanir Lombardi (GitLab CI + TDS-LS Linux) e menções esparsas. Não há wrapper npm/pip/go consolidado da comunidade — esta Fase preenche essa lacuna no ecossistema Python.

---

## 3. Auditoria interna (estado atual v0.7.0)

O que o plugin **já tem** que será reusado:

- **CLI typer com 24 subcomandos** + padrão `_render_from_ctx` + `--format {json,table,md}` + exit codes consistentes.
- **`edit_prw.py`** (Fase 0): `convert_and_save()` e `detect_encoding()` — reusados para gerar `.ini` em CP1252 sem duplicar lógica.
- **`lookups/`** infrastructure: `lookups/funcoes_restritas.json`, `lookups/lint_rules.json` etc. carregados via `importlib.resources`. Padrão será aplicado a `lookups/compile_patterns.json` novo.
- **Catalog consistency tests** (`test_lint_catalog_consistency.py`): padrão de teste que garante drift zero entre catalog e implementação — aplicável a `compile_patterns.json`.
- **Sub-app typer aninhado** (`edit-prw {check,open,save}`) entregue na Fase 0 — `compile` segue mesmo padrão se quiser sub-comandos auxiliares.

O que **não existe** e será criado:

- Módulo de subprocess management.
- Loader de configuração TOML (`runtime.toml`).
- Parser de output do compilador.
- Pattern catalog para diagnostics.

---

## 4. Princípios (herdados da Fase 0)

1. **Sem IP TOTVS no repo**. Mensagens de erro vão para fixtures de teste apenas após sanitização (sem nome de cliente, sem código proprietário, sem credenciais reais).
2. **Opt-in via `runtime.toml`**. Sem config → `compile --mode appre` funciona (modo local). `compile --mode cli` sem config retorna erro claro com instrução de setup.
3. **Sem assumir Docker/Cloudflare**. Plugin não orquestra SSH tunnel, container, nem cloudflared. Documenta que o usuário/CI fica responsável.
4. **Saída JSON estruturada** seguindo padrão do plugin (`--format json` → `{rows: [...], summary: {...}, next_steps: [...]}`).
5. **Credenciais via env var, nunca em arquivo commitado**. Config TOML referencia **nome** da env var (`user_env = "PROTHEUS_USER"`), nunca o valor.
6. **Fail visivelmente, sem retry mágico**. Network blip → erro claro. CI decide retry.
7. **Pasta de cliente nunca citada**. Fixtures sintéticas ou sanitizadas. `customizados-local` pode ser usado pra teste local mas jamais aparece em commits/docs/output.

---

## 5. Arquitetura

```
                                    ┌──────────────────────┐
                                    │ <root>/.plugadvpl/   │
plugadvpl compile foo.prw bar.prw   │ runtime.toml (opt-in)│
       │                            └──────────┬───────────┘
       ▼                                       │
┌──────────────────┐  load_runtime_config()    │
│  cli.py          │◄──────────────────────────┘
│  @app.command    │
│  compile         │
└────┬─────────────┘
     │ CompileRequest(files, mode, runtime_cfg, flags)
     ▼
┌──────────────────────────────────────────────────┐
│  compile.py — orchestrator                       │
│  ├─ resolve_files()    (lista | --changed-since) │
│  ├─ pick_mode()        (auto | cli | appre)      │
│  ├─ resolve_advpls()   (binary path)             │
│  ├─ build_invocation() (cli args ou script.ini)  │
│  └─ run_subprocess()   (timeout + capture)       │
└────┬─────────────────────────────────────────────┘
     │ raw stdout/stderr + exit_code + duration_ms
     ▼
┌──────────────────────────────────────────────────┐
│  compile_parser.py                               │
│  ├─ load_patterns(lookups/compile_patterns.json) │
│  ├─ parse_diagnostics(raw, files)                │
│  └─ classify (error|warning|info|unknown)        │
└────┬─────────────────────────────────────────────┘
     │ list[Diagnostic]
     ▼
┌──────────────────────────────────────────────────┐
│  compile.build_result() — agrega por arquivo,    │
│  calcula counts, decide exit code                │
└────┬─────────────────────────────────────────────┘
     │ CompileResult
     ▼
┌──────────────────┐
│ render()         │ ──► JSON / table / md
│ (existente)      │     exit 0 (sucesso) | 1 (erro) | 2 (config)
└──────────────────┘
```

**4 módulos novos** sob `cli/plugadvpl/`:

| Arquivo | Responsabilidade | Linhas estimadas |
|---|---|---|
| `runtime_config.py` | Carregar/validar `runtime.toml`, resolver env vars. Compartilhado com Fases 2–4. | ~150 |
| `compile.py` | Orchestrator: pick_mode, build invocation, run subprocess, agregar resultado. | ~250 |
| `compile_parser.py` | Regex-based parser do output do advpls + fallback `unknown`. Função pura. | ~120 |
| `cli.py` (existente) | Novo subcomando `compile` (sub-app typer, padrão `edit-prw`). | +80 |

**1 lookup novo**: `lookups/compile_patterns.json` — tabela de regex patterns por idioma (`pt-BR`, `en`, `any`) + severidade + grupos de captura.

**Princípio de isolamento**: cada módulo tem 1 input claro, 1 output claro, zero side effect cruzado.
- `runtime_config.load(root: Path) → RuntimeConfig | None` — função pura (recebe Path, devolve dataclass).
- `compile_parser.parse_diagnostics(raw: str, files: list[str]) → list[Diagnostic]` — função pura (string → lista).
- `compile.py` é o único módulo que toca subprocess + filesystem.

---

## 6. Configuração — `<root>/.plugadvpl/runtime.toml`

Arquivo **opt-in**. Sem ele → comando funciona em modo `appre` apenas. Schema mapeado 1:1 ao `.ini` real do `advpls`:

```toml
# .plugadvpl/runtime.toml — NÃO commitar valores de credencial

[tds_ls]
# Caminho para advpls. Em Windows: D:/TOTVS/protheus/bin/Appserver/advpls.exe
# ou pasta da extensão tds-vscode. Auto-detect tenta PATH + locais comuns.
binary = "D:/TOTVS/protheus/bin/Appserver/advpls.exe"

[appserver]
# RECOMENDAÇÃO: host = "127.0.0.1" + SSH tunnel local.
# Plugin imprime WARNING se host != localhost (porta 1234 sem TLS).
host = "127.0.0.1"
port = 1234
secure = false              # → secure=0/1 no .ini
build = "7.00.240223P"
environment = "P2510"

[auth]
# Convenção: NUNCA valor literal. Sempre nome da env var.
user_env = "PROTHEUS_USER"
password_env = "PROTHEUS_PASS"
aut_file = ""               # opcional — vazio = não inclui no .ini

[compile]
recompile = true            # action=compile, recompile=T
includes = [
    "D:/TOTVS/protheus/includes",
    "D:/projeto/includes_custom",
]
mode = "auto"               # auto | appre | cli
timeout_seconds = 120
include_warnings = true     # se false, filtra warnings na saída

[logging]
# Espelha as 2 chaves globais do .ini do advpls.
log_to_file = ""            # vazio = não passa
show_console_output = true
```

### 6.1 Validações no load (`runtime_config.load`)

Parser TOML: `tomllib` (stdlib Python 3.11+ — alinhado com "sem deps pesadas" §contexto). Nenhuma dep nova.

| Check | Falha → |
|---|---|
| TOML parseável | `RuntimeConfigError("invalid TOML at line N: ...")` |
| Seções obrigatórias presentes (`[tds_ls]`, `[appserver]`, `[auth]`, `[compile]`) | `RuntimeConfigError("missing section: <name>")` |
| `tds_ls.binary` arquivo existe e é executável | `RuntimeConfigError("advpls not found at <path>")` |
| `tds_ls.binary` resolve sem symlink loop (`Path.resolve(strict=True)`) | `RuntimeConfigError("binary path resolution failed: <reason>")` |
| `tds_ls.binary` é symlink → flag `binary_is_symlink=True` na dataclass | warning em stderr (não erro) |
| Env var de `auth.user_env` setada | `RuntimeConfigError("env var PROTHEUS_USER (auth.user_env) is not set")` |
| Env var de `auth.password_env` setada | mesma forma |
| `auth.aut_file` setado → arquivo existe | `RuntimeConfigError("aut_file not found: <path>")` |
| `appserver.host` ∉ `{127.0.0.1, localhost, ::1}` | flag `warn_remote_host = True` (não erro) |
| TCP ping `appserver.host:port` (1s timeout) | flag `appserver_reachable = bool` na dataclass |
| `[logging]` ausente | usa defaults (`log_to_file=""`, `show_console_output=true`) — não erro |

### 6.2 Comportamento sem `runtime.toml`

| Modo | Comportamento |
|---|---|
| `--mode appre` (ou auto sem AppServer) | Funciona se `advpls` está no PATH. Includes não passam (a menos que `--includes` flag CLI). |
| `--mode cli` explícito | Exit 2: `"runtime.toml required for cli mode. Run: plugadvpl compile --init-config"` |
| `--mode auto` (default) | Cai pra `appre` silenciosamente (com log informativo em stderr). |

### 6.3 Subcomando auxiliar `plugadvpl compile --init-config`

- Gera template `<root>/.plugadvpl/runtime.toml` com comentários explicativos por seção.
- Adiciona `.plugadvpl/runtime.toml` ao `.gitignore` (paranoia anti-leak). Skip se já lá.
- Não sobrescreve se já existir; pede `--force`.
- Exit 0 sucesso, 1 se já existe sem `--force`, 2 se erro de I/O.

### 6.4 Princípio crítico

**Nenhuma config é lida fora de `runtime_config.py`**. Esse módulo expõe `dataclass RuntimeConfig` imutável (frozen). Toda decisão downstream consulta a dataclass — nunca relê o TOML, nunca lê env var diretamente fora desse load.

---

## 7. Fluxo de execução

```
1. cli.py recebe args:
   compile foo.prw bar.prw
     [--mode cli|appre|auto]
     [--changed-since <git-ref>]
     [--no-warnings]
     [--timeout <segundos>]
     [--no-security-warning]
     [--includes <path>]     (override)
     [--format json|table|md]

2. runtime_config.load(root) → RuntimeConfig | None
   - Erro → exit 2 com mensagem clara

3. compile.resolve_files(args, --changed-since, root):
   - Lista explícita: filtra extensões .prw/.prx/.tlpp/.tlpp.ch
   - --changed-since <ref>: `git diff --name-only <ref> -- '*.prw' '*.prx' '*.tlpp' '*.tlpp.ch'`
   - Vazio (sem args, sem flag, sem changes) → exit 0 (válido em CI)
   - Glob com '*' → Path.glob, warning se 0 matches
   - Arquivo da lista não existe → diagnostic sintético, continua

4. compile.pick_mode(request, runtime_cfg):
   - --mode explícito: usa direto
   - auto + runtime_cfg.appserver_reachable: "cli"
   - caso contrário: "appre"
   - Log stderr: "mode: cli (appserver 127.0.0.1:1234 reachable)"

5. compile.security_check(runtime_cfg, mode):
   - mode == cli AND warn_remote_host AND NOT --no-security-warning:
     imprime aviso em stderr e CONTINUA imediatamente (sem sleep — princípio
     §4.6 "fail visivelmente sem retry mágico"; sleep mágico em CI é regressão).

6. compile.build_invocation(request, runtime_cfg, mode):
   - mode == cli:
     a) gera dict do script .ini (auth + compile + logging)
     b) cria diretório próprio: `tempfile.mkdtemp(prefix="plugadvpl-", mode=0o700)`
        (no Windows, mode é ignorado mas o uuid no path mitiga reading-by-name;
        documentar limitação Windows: ACL não enforça como Unix permission bits)
     c) grava `compile.ini` com `os.open(path, O_WRONLY|O_CREAT|O_EXCL, 0o600)`
        + bytes em CP1252 (reusa função compartilhada `_encode_cp1252_bytes()`
        do edit_prw.py — extraída para função pura)
     d) args = [binary, "cli", "<tempdir>/compile.ini"]
   - mode == appre:
     args = [binary, "appre", *[f"-I{inc}" for inc in includes], *resolved_files]

7. compile.run_subprocess(args, timeout):
   - usa subprocess.Popen (NÃO run) para controlar lifecycle:
     proc = Popen(args, stdin=subprocess.DEVNULL, stdout=PIPE, stderr=PIPE,
                  encoding="utf-8", errors="replace")
   - explícito stdin=DEVNULL evita bloqueio se advpls algum dia ler stdin
   - try/proc.communicate(timeout=N)/except TimeoutExpired:
       proc.terminate(); proc.wait(timeout=5); proc.kill() se ainda vivo
   - except KeyboardInterrupt:
       proc.terminate(); proc.wait(timeout=5); proc.kill(); raise
       (Windows não propaga SIGINT a child via Popen padrão — terminate explícito)
   - finally: shutil.rmtree(tempdir, ignore_errors=True)
     (warning stderr se falhar — não derruba resultado)
   - Tratamento de encoding do output:
     a) Se stdout/stderr começa com BOM UTF-16LE (0xFF 0xFE) ou UTF-16BE (0xFE 0xFF):
        capturar bytes brutos primeiro (encoding=None), strip BOM, decode utf-16
     b) Se decode utf-8 com errors="replace" produz muitos `�` (>5% chars):
        fallback decode CP1252
     c) Strip BOM UTF-8 (0xEF 0xBB 0xBF) se presente
   - retorna (exit_code, stdout, stderr, duration_ms)

8. compile_parser.parse_diagnostics(stdout, stderr, mode, requested_files):
   - aplica patterns de compile_patterns.json em ordem (`ordem` ASC)
   - cada match → Diagnostic (com arquivo bruto do match)
   - linhas não-classificadas → Diagnostic(severidade="unknown", linha=0, raw=<linha>)
   - patterns são filtrados por `lang` (any | pt-BR | en) conforme heurística simples
     (detecta "Erro" → pt-BR, "error" → en, default any)
   - **normalização de arquivo (CRÍTICO)**:
     a) para cada Diagnostic.arquivo, computa Path.resolve()
     b) cria mapa requested_resolved = {p.resolve(): p_original for p in requested_files}
     c) se diagnostic.arquivo_resolved ∈ requested_resolved: substitui pelo nome original
        passado pelo usuário (mantém consistência de output)
     d) se não bate: arquivo permanece como veio do advpls; flag _unmatched=True
        para o orchestrator agrupar em bucket "__unmatched__" no resultado
   - precedência tie-break: se 2 patterns matcham mesma linha com mesma `ordem`,
     vence o primeiro do JSON (estável). Testado em §11.1.

9. compile.build_result(files, diagnostics, exit_code, mode, runtime_cfg):
   - agrupa diagnostics por arquivo
   - calcula counts {error, warning, info, unknown} por arquivo
   - per-arquivo ok = sem diagnostic severidade=error
   - exit_code do plugin:
     0 se nenhum arquivo tem error
     1 se algum arquivo tem error (compile falhou)
     2 se config/setup falhou (já tratado nos passos 2/5)
   - se total_files=0 → exit 0 (CI-friendly)

10. render() exibe (JSON/table/md) — função existente do plugin
```

---

## 8. Schema de saída JSON (contrato estável)

```json
{
  "rows": [
    {
      "arquivo": "foo.prw",
      "ok": false,
      "mode": "cli",
      "duration_ms": 1842,
      "exit_code": 1,
      "counts": {"error": 2, "warning": 1, "info": 0, "unknown": 0},
      "diagnostics": [
        {
          "severidade": "error",
          "arquivo": "foo.prw",
          "linha": 42,
          "coluna": 0,
          "mensagem": "Unbalanced ENDIF",
          "codigo": "",
          "raw": "foo.prw(42) error: Unbalanced ENDIF"
        },
        {
          "severidade": "warning",
          "arquivo": "foo.prw",
          "linha": 17,
          "coluna": 0,
          "mensagem": "Variable 'cAux' declared but not used",
          "codigo": "",
          "raw": "foo.prw(17) warning: ..."
        }
      ]
    },
    {
      "arquivo": "bar.prw",
      "ok": true,
      "mode": "cli",
      "duration_ms": 920,
      "exit_code": 0,
      "counts": {"error": 0, "warning": 0, "info": 0, "unknown": 0},
      "diagnostics": []
    }
  ],
  "summary": {
    "total_files": 2,
    "ok": 1,
    "failed": 1,
    "total_errors": 2,
    "total_warnings": 1,
    "mode_used": "cli",
    "appserver_reachable": true,
    "runtime_config_loaded": true,
    "output_truncated": false
  },
  "next_steps": [
    "plugadvpl compile foo.prw --no-warnings   # filtra warnings",
    "plugadvpl arch foo.prw                    # contexto arquitetural"
  ]
}
```

### 8.1 Schema do `compile_patterns.json`

```json
[
  {
    "id": "advpls_arquivo_linha",
    "lang": "any",
    "pattern": "^(?P<arquivo>[^()\\s]+)\\((?P<linha>\\d+)(?:,(?P<coluna>\\d+))?\\)\\s+(?P<severidade>error|warning|info):\\s*(?P<mensagem>.+)$",
    "severidade_group": "severidade",
    "ordem": 10
  },
  {
    "id": "tdscli_pt_br_erro",
    "lang": "pt-BR",
    "pattern": "^Erro\\s+ao\\s+compilar\\s+(?P<arquivo>\\S+):\\s*linha\\s+(?P<linha>\\d+)\\s*-\\s*(?P<mensagem>.+)$",
    "severidade_fixed": "error",
    "ordem": 20
  }
]
```

Regras de schema:
- `severidade_group` OU `severidade_fixed` (XOR) — testado pelo catalog consistency.
- `pattern` válido (compila como regex) — testado.
- `ordem` ASC determina precedência de match.
- `lang ∈ {any, pt-BR, en}`.

---

## 9. Error handling

| Situação | Detecção | Tratamento | Exit |
|---|---|---|---|
| `runtime.toml` ausente em `--mode cli` | `runtime_config.load()` retorna `None` | Mensagem `"runtime.toml required for cli mode at <path>. Run: plugadvpl compile --init-config"` | 2 |
| `binary` (advpls) não encontrado | `Path.exists()` no load | Erro + sugere `--mode appre` se `advpls` no PATH funciona | 2 |
| Env var de credencial ausente | `os.environ.get()` retorna `None` | Erro: `"env var PROTHEUS_USER (referenced by auth.user_env) is not set"` | 2 |
| AppServer não responde em modo `cli` | TCP connect timeout 1s | Modo auto: degrada para `appre` + log stderr. Modo `cli` explícito: erro com `host:port` | 2 se `--mode cli` |
| `aut_file` ausente | `Path.exists()` | Erro: `"aut_file not found: <path>"` | 2 |
| Timeout do subprocess | `subprocess.TimeoutExpired` | Mata processo (incl. filhos), diagnostic sintético `error: "compile timeout after Xs"` por arquivo | 1 |
| advpls crash (exit ≠ 0/1) | exit code não esperado | Diagnostic `unknown` com `raw=<stderr>`, NÃO inventa diagnostics | 1 |
| Output >10 MB | size check pós-capture | Trunca em 10 MB, `output_truncated=true` no summary | 1 |
| Fonte com encoding errado | delegado ao advpls | Mensagem do advpls vira diagnostic. `next_steps` sugere `plugadvpl edit-prw check <fonte>` | 1 |
| Glob `*.prw` nos args | `Path.glob` | Expande, warning se 0 matches | 1 |
| Arquivo da lista não existe | `Path.exists()` | Diagnostic sintético `error: "file not found"` só pra esse, demais continuam | 1 |
| `--changed-since` sem repo git | `git diff` exit ≠ 0 | Mensagem clara: `"--changed-since requires a git repository at <root>"` | 2 |
| `--changed-since` retorna vazio | git diff vazio | Sucesso, `summary.total_files=0`. Output válido pra CI. | 0 |
| Tempdir/`.ini` não pode ser criado | `tempfile.mkdtemp` ou `os.open` falha | Erro claro com path tentado. Sem fallback silencioso. | 2 |
| Limpeza do tempdir falha | `shutil.rmtree(ignore_errors=True)` no finally | Warning stderr (`"failed to delete tempdir: <path>"`). Não derruba resultado. | usa exit do compile |
| `KeyboardInterrupt` (Ctrl-C) | except no `run_subprocess` | `proc.terminate()` → `proc.wait(5)` → `proc.kill()` se ainda vivo. Limpa tempdir. Re-raise. | 130 (convenção) |
| Output em UTF-16 (PowerShell/Win Server) | BOM check em `run_subprocess` | Decode utf-16, strip BOM. Funciona transparente p/ parser. | n/a |
| Output em CP1252 (fallback) | >5% `�` em utf-8 decode | Re-decode CP1252. Documentado no log stderr. | n/a |
| Diagnostic com `arquivo` reportado pelo advpls ≠ nome passado pelo usuário | normalização §7.8 | `Path.resolve()` em ambos, se bate → usa nome original do usuário. Não bate → bucket `__unmatched__` no resultado | usa exit do compile |
| Credencial em log do advpls (paranoia) | redact patterns externos em `lookups/redact_patterns.json` | Patterns aplicados em `Diagnostic.raw` E em todo stdout/stderr antes de log. Lista cobre: `password`, `psw`, `senha`, `pwd`, `aut_file` value, hex keys >16 chars. Catalog test garante cada pattern compila. | n/a |

**Convenções**:
- Exit 0 = sucesso (zero errors)
- Exit 1 = compile encontrou error (CI normal)
- Exit 2 = config/setup inválido
- Exit 130 = `KeyboardInterrupt` (convenção POSIX 128+SIGINT)
- Setup errors → stderr; diagnostics → stdout (JSON/table). Permite `compile foo.prw 2>setup.log | jq .`.

**Sem retry automático**. **Sem cache no MVP** (entra em Fase 1.5 se ficar lento). **Sem sleep mágico em warning** (§7.5).

---

## 10. Paridade com TDS-VSCode

Mental model do usuário fica idêntico:

| TDS-VSCode (IDE) | plugadvpl compile (CLI) |
|---|---|
| `View → Servers → +` (wizard) | `plugadvpl compile --init-config` gera template comentado |
| `servers.json` (`~/.totvsls/`) | `<root>/.plugadvpl/runtime.toml` |
| Senha no SecretStorage | env var `PROTHEUS_PASS` |
| Statusbar "Connect" | TCP ping em `pick_mode()` |
| `F9` (compile current) | `plugadvpl compile foo.prw` |
| `Compile All` | `plugadvpl compile --changed-since main` |
| Tab "Problems" | `--format json` → `diagnostics[]` estruturado |

**Diferenças conscientes (out of scope Fase 1)**:

| Feature TDS-VSCode | Status Fase 1 | Justificativa |
|---|---|---|
| Wizard interativo (detecta build/env do AppServer) | TOML manual | YAGNI no MVP — copia do `appserver.ini` |
| Patch/build/debug interativo | Fora de escopo | Fase 3 (`deploy`) cobre patch/build; debug nunca (só LSP) |
| Multi-server picker | 1 server por `runtime.toml` | Multi-profile em Fase 1.5 se demanda surgir |
| Editor in-buffer | Não somos editor | `edit-prw` (Fase 0) cobre o necessário |
| Auto-reconnect | Falha visível, exit 2 | Princípio "fail visivelmente" |

---

## 11. Testing strategy

Suite dividida em 5 camadas, total ~85 novos testes (`629 → ~714` verde). Tempo CI adicional <10s.

### 11.1 Unit — `compile_parser.py` (~30 testes)

Função pura `parse_diagnostics(raw, files) → list[Diagnostic]`. Sem subprocess, sem rede.

**Fixtures em `tests/fixtures/compile_outputs/`** (sanitizadas):
- `unbalanced_endif_en.txt` — `foo.prw(42) error: Unbalanced ENDIF`
- `missing_include_pt.txt` — `Erro ao compilar foo.prw: linha 3 - INCLUDE 'xxx.ch' nao encontrado`
- `variable_unused_warn.txt` — warning típico
- `mixed_errors_warnings.txt` — 5 errors + 3 warnings + 2 linhas não classificáveis
- `clean_compile.txt` — sucesso sem output
- `advpls_crash.txt` — stderr de segfault/exit 139
- `empty_output.txt` — exit 1 sem stdout
- `huge_output_trunc.txt` — >10 MB para validar truncamento

**Por fixture**:
- Conta esperada de error/warning/info/unknown
- Cada `Diagnostic` tem campos obrigatórios não-vazios (exceto `coluna`/`codigo`)
- `mixed_*`: linhas não classificadas viram `unknown` (não silenciam)
- `empty_output`: parser retorna `[]`; orchestrator monta diagnostic sintético
- Catalog consistency: cada pattern em `compile_patterns.json` compila como regex, tem `severidade_group` XOR `severidade_fixed`, grupos referenciados existem
- **Precedência tie-break**: 2 patterns com mesma `ordem` matchando mesma linha → vence o que aparece primeiro no JSON (estável)
- **Normalização de arquivo**: diagnostic com path absoluto Windows (`D:\\full\\path\\foo.prw`) matcheia com input relativo (`foo.prw`) — retorna nome original do usuário
- **Bucket `__unmatched__`**: diagnostic com arquivo que não está em `requested_files` resolved → vai pra bucket separado, não polui rows principais
- **Redact patterns**: linha do output contendo `psw=segredo123` → `Diagnostic.raw` tem `psw=***REDACTED***`. Catalog `redact_patterns.json` testado por consistency.

### 11.2 Unit — `runtime_config.py` (~20 testes)

`load(root) → RuntimeConfig | None`. Sem subprocess, sem rede.

- TOML válido completo → dataclass populada
- TOML ausente → `None` (sem exceção)
- TOML malformado → erro com linha
- Cada validação da §6.1 com cenário positivo + negativo
- Env var resolução: presente, ausente, vazia
- `host` remoto → `warn_remote_host=True`
- TCP ping mockado: reachable / unreachable / timeout
- `--init-config` template: round-trip render → load → mesmo dataclass

### 11.3 Integration — `compile.py` orchestrator (~25 testes)

`subprocess.run` mockado (sem advpls real). Testa orquestração completa.

| Cenário | Mock retorna | Esperado |
|---|---|---|
| 2 fontes ok, modo cli | exit=0, output limpo | rows `ok=true`, summary `failed=0`, exit 0 |
| 1 fonte 1 error 1 warning | exit=1 + output misto | counts corretos, exit 1 |
| 3 fontes modo appre | exit=0 | `mode_used=appre` |
| Auto + AppServer reachable | (mock socket OK) | `mode_used=cli` |
| Auto + AppServer unreachable | (mock socket fail) | `mode_used=appre` + log stderr |
| `--mode cli` + AppServer down | n/a | exit 2 + mensagem |
| Sem runtime.toml + auto | usa appre se PATH | ok |
| `--changed-since HEAD~1` em repo git tmp | git diff retorna 2 files | rows correspondentes |
| `--changed-since` fora de git | git falha | exit 2 |
| `--changed-since` vazio | nada | exit 0 |
| Timeout subprocess | `TimeoutExpired` | diagnostic sintético timeout, exit 1 |
| advpls crash exit 139 | exit=139 | diagnostic `unknown`, exit 1 |
| Output 11 MB | mock retorna grande | `output_truncated=true`, sem perda do parseado |
| `.ini` em CP1252 | tempfile inspecionado | bytes começam com CP1252 da senha com acento (fixture `"açúcar"`) |
| `.ini` é deletado | spy `Path.unlink` | chamado mesmo se subprocess raise |
| Credencial nunca em log | captura stderr completo | regex assert `password|psw` ausente |
| Glob `*.prw` | `Path.glob` | expande, warning se 0 |
| Arquivo inexistente | resolve_files | diagnostic só pra esse, demais OK |
| Security warning host remoto | log stderr | warning impresso, SEM sleep, continua direto (§7.5) |
| `--no-security-warning` | n/a | warning suprimido |
| `KeyboardInterrupt` no meio do compile | mock raise dentro de `proc.communicate` | `proc.terminate()` chamado, tempdir limpo, re-raise, exit 130 |
| Output UTF-16LE com BOM | mock retorna `b"\\xff\\xfe<utf-16-bytes>"` | decode utf-16, parser classifica normal |
| Output com >5% chars `�` em utf-8 | mock retorna bytes mistos cp1252 | fallback decode cp1252, log informativo |
| Diagnostic path absoluto vs input relativo | mock retorna `D:\\proj\\foo.prw(42) error: ...`, input `foo.prw` | row tem `arquivo="foo.prw"` (original do usuário), não absoluto |
| Diagnostic arquivo não solicitado | mock retorna `outro.prw(1) error` para request `foo.prw` | bucket `__unmatched__` no resultado, não em rows |
| Tempdir mode 0o700 (Linux/macOS) | inspeção pós-create | `os.stat` mode bits = 0o700. Skip em Windows (documentar) |
| `.ini` mode 0o600 | inspeção do file criado por `os.open` | mesma forma |
| Stdin DEVNULL | mock Popen verifica kwarg | `stdin == subprocess.DEVNULL` |

### 11.4 Integration CLI — `cli.py` end-to-end (~10 testes)

Padrão `tests/integration/test_cli.py::TestEditPrw*`. `CliRunner` + `runtime.toml` em tmp + mock `advpls` via PATH-shim (script Python que finge ser advpls).

- `compile --init-config` cria template + adiciona ao `.gitignore`
- `--init-config` recusa sobrescrever sem `--force`
- `compile foo.prw --format json` schema bate com contrato da §8
- `compile foo.prw --format table` produz tabela legível
- `compile foo.prw --mode cli` sem runtime.toml → exit 2 + mensagem útil
- `compile foo.prw --mode appre` funciona sem runtime.toml
- `compile` (sem args) → exit 2 + `"nenhum fonte informado"`
- Exit codes consistentes (0/1/2) com a tabela §9
- Separação stderr (setup) vs stdout (diagnostics)
- `next_steps` no JSON populado quando há erros

### 11.5 Smoke real — manual, marcado `@pytest.mark.smoke`

Skip por default; roda se `PLUGADVPL_SMOKE=1`:

- `compile foo_clean.prw` no AppServer local Windows (`D:\TOTVS\protheus\bin\Appserver`)
- `compile foo_with_error.prw` mesmo setup — valida `compile_patterns.json` contra output real
- Via SSH tunnel para VPS (`host=127.0.0.1` após `ssh -L 1234:...`)

**Critério objetivo de aprovação do smoke**:
- Fixtures coletadas no smoke devem cobrir **≥3 famílias de erro distintas** (ex: sintaxe, include faltando, função redefinida) e cada uma vira teste unit do parser antes do release.
- Pelo menos 1 fixture pt-BR + 1 en (cobre os 2 idiomas comuns do advpls).
- Todas as fixtures sanitizadas (sem credencial, sem caminho de cliente, sem nome de empresa).

**Loop de aprendizagem**: cada output real coletado no smoke vira fixture sanitizada em `tests/fixtures/compile_outputs/` + teste unit do parser. Reforça `compile_patterns.json` a cada bug encontrado em uso real.

---

## 12. Ordem de implementação (TDD red→green, commit atômico por etapa)

1. **`runtime_config.py`** (dataclass + load + validações + `--init-config` template + symlink + tomllib) — ~3h
2. **`lookups/redact_patterns.json`** + catalog test — ~1h
3. **`compile_parser.py`** + `lookups/compile_patterns.json` (3-5 patterns iniciais) + fixtures básicas + normalização de arquivo + redact — ~4h
4. **`compile.py` orchestrator** modo `appre` (subprocess mockado, sem AppServer) — ~3h
5. **`compile.py` orchestrator** modo `cli` (mkdtemp 0o700 + os.open 0o600 + Popen + DEVNULL + BOM/encoding + KeyboardInterrupt + security warning) — ~4h
6. **`cli.py`** subcomando `compile` typer (sub-app pattern) + `--init-config` — ~2h
7. **Integration tests** CLI end-to-end (PATH-shim do advpls) — ~2h
8. **Smoke real iterativo** no AppServer local Windows + VPS via SSH tunnel — esse passo é **cíclico com coleta de fixtures**: rodar smoke → capturar output → sanitizar → criar fixture → adicionar/ajustar pattern → re-rodar smoke. Estimar ~3h (1h smoke inicial + 2h para 3 famílias de erro descobertas iterativamente). — ~3h
9. **Release v0.8.0**: CHANGELOG + plugin.json + marketplace.json + ROADMAP + README + cli-reference + commit + tag — ~1h

**Total estimado**: ~23h (~3 dias). Margem: ~4h para imprevistos (parsing surpresas no smoke iterativo, encoding edge cases em Windows Server).

**Dependência entre etapas**: 8 (smoke real iterativo) realimenta 3 (patterns) — espera-se 2-3 iterações pequenas até estabilizar. Etapa 9 só inicia quando ≥3 famílias de erro têm fixture estável.

---

## 13. Out of scope (Fases futuras)

| Feature | Fase planejada |
|---|---|
| Hot-swap RPO (apply-patch, restart) | **Fase 3 — `plugadvpl deploy`** |
| Cliente HTTP do contrato U_EXEC | **Fase 2 — `plugadvpl exec`** |
| Smoke tests + assertions automáticos | **Fase 4 — `plugadvpl smoke` / `test`** |
| Hooks Claude Code (pre-write compile) | **Fase 5** |
| Cache incremental de compile (skip não-modificados) | **Fase 1.5** (se ficar lento na prática) |
| Multi-server profile (`runtime.toml` por env: dev/hml/prod) | **Fase 1.5** |
| LSP mode (diagnostics estruturados nativos) | **Fase 6+** (se Fase 5 mostrar demanda) |
| Wizard interativo de setup | provavelmente nunca (`--init-config` cobre) |

---

## 14. Critérios de aceitação

Todos verificáveis por teste automatizado, exceto onde explicitamente "smoke manual".

- [ ] 4 módulos novos (`runtime_config.py`, `compile.py`, `compile_parser.py`, +cli.py) com responsabilidade isolada conforme §5.
- [ ] `lookups/compile_patterns.json` com ≥5 patterns iniciais cobrindo `en` + `pt-BR`.
- [ ] `lookups/redact_patterns.json` com ≥5 patterns de redaction (password, psw, senha, pwd, aut_file value, hex keys).
- [ ] Subcomando `plugadvpl compile <fonte...>` com flags `--mode`, `--changed-since`, `--no-warnings`, `--timeout`, `--no-security-warning`, `--includes`, `--format`.
- [ ] Subcomando `plugadvpl compile --init-config` gera template + adiciona ao `.gitignore`.
- [ ] Schema JSON estável conforme §8 — testado por contract test (snapshot do schema).
- [ ] ~85 novos testes (30 parser + 20 config + 25 orchestrator + 10 CLI). 100% passing.
- [ ] Catalog consistency test cobre `compile_patterns.json` (pattern compila, severidade XOR, grupos válidos, sem ordem duplicada problemática) E `redact_patterns.json` (cada pattern compila).
- [ ] Suite total ≥714 testes verde (era 629 no v0.7.0).
- [ ] `--mode appre` funciona end-to-end sem AppServer (testado em integration via PATH-shim).
- [ ] `--mode cli` funciona end-to-end com AppServer local Windows + VPS via SSH tunnel **(smoke manual, critério §11.5)**.
- [ ] Security warning impresso em host remoto a menos que `--no-security-warning`, **SEM sleep** (testado em integration).
- [ ] Tempfile `.ini` em CP1252 + permission 0o600 (Linux/macOS — Windows documentado). Tempdir 0o700. Deletado em qualquer caminho (try/finally, KeyboardInterrupt, timeout).
- [ ] **Credencial assertion objetiva**: para todos os testes que rodam o orchestrator end-to-end, regex assert `(?i)(password|psw|senha|pwd)\s*[:=]\s*\S+` ausente em stdout, stderr e qualquer `Diagnostic.raw`. Mínimo 5 testes cobrindo esse assert.
- [ ] `Path.resolve()` normaliza diagnostic.arquivo vs requested_files (testado positiva + negativa com `__unmatched__`).
- [ ] Suporte a output UTF-16 BOM e fallback CP1252 (testado com fixtures binárias).
- [ ] Exit codes: 0 (sucesso), 1 (compile error), 2 (config/setup), 130 (KeyboardInterrupt) — cada um testado.
- [ ] CHANGELOG, plugin.json, marketplace.json, ROADMAP, README, cli-reference sincronizados em v0.8.0.
- [ ] Tag git `v0.8.0` aplicada.
- [ ] Smoke fixtures (≥3 famílias de erro, ≥1 pt-BR + ≥1 en, todas sanitizadas) commitadas em `tests/fixtures/compile_outputs/`.

---

## 15. Anexos

### 15.1 Resumo da pesquisa de URLs (TDS-LS)

- `github.com/totvs/tds-ls` — repo deprecated (issues em `tds-vscode`)
- `github.com/totvs/tds-ls/blob/master/TDS-CLi.md` — referência CLI
- `github.com/totvs/tds-ls/blob/master/TDS-cli-script.md` — formato `.ini`
- `tdn.totvs.com/display/tec/TDS+em+linha+de+comando` — TDN oficial
- `terminaldeinformacao.com/2017/08/08/como-utilizar-tds-por-linha-de-comando-tdscli/` — Daniel Atilio
- `linkedin.com/pulse/integração-contínua-gitlab-cicd-advpl-tds-lslinux-sibanir-lombardi-9mqhf` — único exemplo CI público

### 15.2 Decisões honestas registradas

- LSP mode (Abordagem B) descartado para Fase 1 — overkill para CI batch (~3-4× esforço, lifecycle complexo). Reavaliado em Fase 6+ se hooks Claude Code (Fase 5) demonstrarem demanda por diagnostics in-buffer.
- `tdscli.bat/sh` legacy (Abordagem C) descartado — é mode de compat do próprio `advpls`, sem ganho.
- Sem cache no MVP — `--changed-since` git já entrega 80% do valor de cache.
- Sem retry automático — fail visível é princípio do plugin.
- Sem orquestração de SSH tunnel — fora do escopo (usuário/CI controla).
- Sem `language-server` mode — é Fase 6+.
- **Sem sleep mágico em warning** (decisão pós-review) — sleep em CI é regressão; warning deve ser síncrono e informativo, não bloqueante.

### 15.3 Resposta ao review automatizado

Spec passou por revisão crítica antes do user review gate. CRITICAL e IMPORTANT resolvidos inline:

| Item do review | Resolução |
|---|---|
| C1 — Race condition tempfile credencial | §7.6b/c: `mkdtemp(mode=0o700)` + `os.open(O_EXCL, 0o600)` + `shutil.rmtree` no `finally`. Windows documentado. |
| C2 — Path absoluto vs relativo nos diagnostics | §7.8: normalização explícita via `Path.resolve()` + bucket `__unmatched__`. Teste em §11.1 + §11.3. |
| C3 — Stdin bloqueia subprocess | §7.7: `stdin=subprocess.DEVNULL` explícito. Teste em §11.3. |
| C4 — Output UTF-16 BOM | §7.7: BOM check + fallback UTF-16/CP1252 documentado. Testes em §11.3. |
| I1 — SIGINT/Ctrl-C | §7.7: `try/except KeyboardInterrupt: terminate → wait(5) → kill`. Exit 130. Teste em §11.3. |
| I2 — Symlink traversal | §6.1: `resolve(strict=True)` + flag `binary_is_symlink` + warning. |
| I3 — `sleep(3)` no warning | §7.5: removido. Warning síncrono, continua direto. Registrado em §15.2. |
| I4 — Credencial assertion objetiva | §14: regex `(?i)(password\|psw\|senha\|pwd)\s*[:=]\s*\S+` em mínimo 5 testes. |
| I5 — Redact patterns como lookup | §9 + nova etapa 2 em §12: `lookups/redact_patterns.json` + catalog test. |
| I6 — Pattern precedence tie-break | §7.8 + §11.1: documentado "primeiro do JSON" + teste explícito. |
| N1 — Critério objetivo do smoke | §11.5: ≥3 famílias + 1 pt-BR + 1 en + sanitização. |
| N2 — `tomllib` stdlib | §6.1: explicitado "tomllib stdlib 3.11+, sem dep nova". |
| N3 — Dependência cíclica 7→8 | §12: passos 3 e 8 marcados cíclicos, estimativa ajustada (~21h → ~23h). |
