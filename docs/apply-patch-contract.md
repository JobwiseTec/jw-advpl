# U6_APPLY_PATCH — contrato canônico do `apply-patch`

> **Status:** especificação de referência · **Licença deste doc:** CC-BY-4.0
> **Versão:** v0.1.0 (Fase 2 / issue #4) · **Sub-plugin:** `plugadvpl-ops`
> **Base:** [Fase 0 research](../gaps/U6_APPLY_PATCH_RESEARCH.md) (smoke-validado 2026-06-16) + [spec Fase 1](superpowers/specs/2026-06-16-u6-apply-patch-design.md)

Define o contrato de **input**, **output JSON**, **códigos de erro** e **audit trail** do `plugadvpl-ops apply-patch` — aplicação de `.PTM` via `advpls cli action=patchApply` com backup, idempotência por hash e rollback.

> ⚠️ **Aviso de produção.** Aplicar patch altera o RPO no lugar. Em server `prod`,
> `--confirm-prod` é obrigatório, backup é forçado, e `allow_prod=false` no
> `runtime.toml` bloqueia totalmente. Ver [PROD safety](#prod-safety).

---

## Input

### Formas aceitas

| Input | Tratamento |
|---|---|
| `arquivo.PTM` | aplicado direto |
| `arquivo.zip` | **descompactado internamente** (híbrido D7); lista `.PTM` em ordem alfabética; aplica um a um |
| diretório | varre `*.PTM` (não-recursivo) em ordem alfabética |

> O advpls **não** faz backup nem detecta "já aplicado" — ambos são responsabilidade do plugin.
> O advpls **aceita** ZIP nativamente, mas o plugin descompacta para manter controle por-`.PTM`
> (ordem, hash, backup granular). Ver [Decisão ZIP](../gaps/U6_APPLY_PATCH_RESEARCH.md#decisão-zip--híbrido-aceita-zip-descompacta-internamente).

### CLI

```bash
plugadvpl-ops apply-patch <input> --use-server <name> [opções]

# opções
--dry-run               # valida e mostra o plano, não aplica
--confirm-prod          # obrigatório se o server é prod
--no-backup             # proibido se o server é prod
--apply-old             # passa applyOldProgram=True (aplica recursos antigos também)
--list-applied          # lista patches já aplicados no env (lê patches_applied)
--rollback <patch-id>   # restaura o RPO de backup daquele patch (granular)
--rollback-batch <ts>   # restaura o RPO do início da batch (cascata)
--json                  # saída JSON (default: humano + JSON em --json)
```

### `.ini` gerado por patch (1 `advpls cli` por `.PTM` — decisão D-impl)

```ini
logToFile=<tmp>/apply_patch_<n>.log
showConsoleOutput=true

[auth]
action=authentication
server=<host>
port=<port>
secure=<0|1>          ; SEMPRE numérico — "false"/"true" → [ERROR] stoi (smoke)
build=<build|AUTO>
environment=<env>
user=<user>
psw=<pwd>

[patchApply]
action=patchApply
patchFile=<path_absoluto>.ptm
localPatch=True
applyOldProgram=<False|True>   ; False = aplica só recursos novos (partial)

[defragRPO]                     ; só na ÚLTIMA invocação da batch
action=defragRPO
```

---

## Output JSON

```json
{
  "ok": true,
  "server": "qa",
  "environment": "protheus_cmp",
  "build": "7.00.240223P",
  "batch_ts": "20260616_122345",
  "summary": { "applied": 2, "partial": 1, "skipped": 1, "failed": 0 },
  "patches": [
    {
      "ptm_name": "hotfix_001_tttm120_op.ptm",
      "ptm_hash": "sha256:9f2b…",
      "status": "applied",
      "backup_path": "rpo_backup/qa/20260616_122345/hotfix_001….ptm.rpo",
      "log_path": "logs/qa/20260616_122345/patch_1.log",
      "detail": null
    },
    {
      "ptm_name": "hotfix_002_tttm120_op.ptm",
      "ptm_hash": "sha256:1a4c…",
      "status": "partial",
      "backup_path": "…",
      "log_path": "…",
      "detail": "Only new sources applied (applyOldProgram OFF)"
    },
    {
      "ptm_name": "ja_aplicado.ptm",
      "ptm_hash": "sha256:77de…",
      "status": "skipped",
      "detail": "hash já em patches_applied (env qa)"
    }
  ]
}
```

### Campos

| Campo | Tipo | Descrição |
|---|---|---|
| `ok` | bool | `true` se nenhum patch falhou (`failed=0`). `partial` **não** zera `ok`. |
| `server` / `environment` / `build` | string | contexto da aplicação |
| `batch_ts` | string | `YYYYMMDD_HHMMSS` — agrupa a execução (chave do rollback-batch) |
| `summary` | object | contagem por status |
| `patches[]` | array | um item por `.PTM` processado |
| `patches[].status` | enum | `applied` \| `partial` \| `skipped` \| `failed` |
| `patches[].ptm_hash` | string | `sha256:<hex>` — chave de idempotência |
| `patches[].backup_path` | string\|null | RPO backup pré-patch (null se `--no-backup` em não-prod) |
| `patches[].detail` | string\|null | motivo (partial/skip/falha) |

### Status por patch — **derivado do PARSE do log, não do exit code**

> ⚠️ **Smoke 2026-06-16:** o advpls retorna exit `0` mesmo em aplicação parcial.
> O status **DEVE** vir do parse do `logToFile`, não de `$?`.

| status | Como é detectado no log |
|---|---|
| `applied` | `Patch (<nome>) successfully applied.` **sem** o warning de outdated |
| `partial` | `successfully applied.` **+** `'applyOldProgram' was NOT set. Only new sources are being applied.` |
| `skipped` | hash já presente em `patches_applied` (não chega a invocar advpls) |
| `failed` | ausência de `successfully applied.` / `[ERROR]` fatal (ver abaixo) |

**`[ERROR]` benigno (NÃO é falha):** `Unable to connect to the server…` seguido de
reconexão sem-secure é a negociação normal TLS→plain. O parser ignora esse `[ERROR]`
específico quando há `Appserver detected with build version:` logo após.

---

## Códigos de saída (processo)

| Código | Significado |
|---|---|
| 0 | Sucesso — todos `applied`/`partial`/`skipped`, nenhum `failed` |
| 2 | Erro de uso (input inválido, prod sem `--confirm-prod`, `--no-backup` em prod) |
| 3 | Server unreachable / auth falhou (`[ERROR] stoi` por `secure` não-numérico cai aqui) |
| 4 | ≥1 patch `failed` — rollback executado, sequência abortada |
| 5 | Lock ocupado (`~/.plugadvpl/locks/<env>.lock` — outra batch em andamento) |
| 6 | `allow_prod=false` bloqueou aplicação em server prod |

---

## Audit trail

Por batch, grava-se sob `~/.plugadvpl/ops/apply-patch/<env>/<batch_ts>/`:

```
<batch_ts>/
├── manifest.json        # cópia do Output JSON acima
├── patch_1.log          # logToFile do advpls (por patch)
├── patch_2.log
└── backups/             # RPO pré-patch (se backup ligado)
    ├── <ptm_1>.rpo
    └── <ptm_2>.rpo
```

E na tabela `patches_applied` (migration `034`):

```sql
patches_applied(env, build, ptm_name, ptm_hash, applied_at, log_path, batch_ts, backup_path)
UNIQUE(env, ptm_hash)   -- idempotência
```

Retenção de backups: **keep 10 por env** (configurável em `runtime.toml`); rotação por contagem.

---

## PROD safety

Quando o server é marcado `prod` em `servers.json`:

- `--confirm-prod` **obrigatório** — ausência → exit 2.
- backup **forçado** — `--no-backup` rejeitado → exit 2.
- `allow_prod=false` no `runtime.toml` → bloqueio total, exit 6.
- audit trail estendido (manifest + logs + backups sempre).

---

## Encoding

- `.ini` gerado em **CP1252** (reúso de `compile.py:_write_secure_ini`), tempdir `0o700` / arquivo `0o600`.
- `secure` **sempre numérico** (`0`/`1`) — string `false`/`true` → `[ERROR] stoi` (smoke).
- Log do advpls decodificado tratando BOM UTF-16 (PowerShell) + fallback CP1252 (reúso `compile.py:decode_output`).
- `psw` **nunca** persistido em audit/log — só no `.ini` temporário (apagado no finally).

---

## Reference implementation

Scripts PowerShell + Bash do ciclo de RPO (compile / apply-patch / troca-quente) —
projeto pessoal de estudo, base da Fase 0. A entrar em `docs/reference-impl/` sob **MIT**
após sanitização (remover link de Drive e qualquer referência identificável).

Pontos do reference impl **endurecidos** pelo plugin:

- ❌ reference confia no exit code → ✅ plugin parseia o log (detecta partial-apply)
- ❌ reference idempotência por mover arquivo → ✅ plugin por hash em `patches_applied`
- ❌ reference sem backup no fluxo de patch → ✅ plugin faz backup versionado pré-patch
- ❌ reference `rm -rf` na limpeza → ✅ plugin move conservador
- ❌ reference deixa `psw` em plaintext no `.ini` do build dir → ✅ plugin usa `.ini` temporário 0600 apagado no finally

---

## Doc oficial TOTVS

TDS-CLI (`advpls`): https://github.com/totvs/tds-ls/blob/master/TDS-cli-script.md —
parâmetros do `patchApply`: `patchFile`, `localPatch`, `applyOldProgram`.
