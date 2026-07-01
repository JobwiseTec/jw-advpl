# `plugadvpl-ops apply-patch` — Aplicação de `.PTM` — Design (Fase 1)

**Status:** Implemented (2026-06-16 — Fase 3 codada + smoke real OK; ver fim do doc)
**Issue:** [#4 — feat(U6): apply-patch](https://github.com/JoniPraia/plugadvpl/issues/4)
**Decisão arquitetural:** Híbrida (issue #5) — apply-patch nasce no **core** espelhando `tq`; extração do `plugadvpl-ops` é refactor futuro (move tq+apply-patch juntos)
**Base de pesquisa:** [gaps/U6_APPLY_PATCH_RESEARCH.md](../../../gaps/U6_APPLY_PATCH_RESEARCH.md) (Fase 0, smoke-validada)
**Contrato:** [docs/apply-patch-contract.md](../../apply-patch-contract.md) (Fase 2)
**Implementação:** [cli/plugadvpl/apply_patch.py](../../../cli/plugadvpl/apply_patch.py) + `@app.command("apply-patch")` no cli.py + migration `034` + [tests/unit/test_apply_patch.py](../../../cli/tests/unit/test_apply_patch.py) (23 testes)

---

## Contexto

Aplicar patch TOTVS (`.PTM` via `advpls cli` action `patchApply`) é hoje um ritual artesanal: dev recebe ZIP da fábrica, descompacta, roda `.bat`/`.ps1`, torce. Erros clássicos: patch fora de ordem, env errado (QA→PROD), sem backup/rollback, reaplicação acidental.

A Fase 0 mapeou o formato real do `.ini` (a partir dos scripts de referência do Barbito + doc oficial TDS-CLI) e confirmou que **~80% do plumbing já existe** em [cli/plugadvpl/compile.py](../../../cli/plugadvpl/compile.py). Este spec define a feature que **endurece** a lógica artesanal: idempotência por hash (não por mover arquivo), backup versionado do RPO, lock por env, `--confirm-prod`, audit trail.

## Decisões críticas — **aprovadas (2026-06-16)**

| # | Decisão | Resolução | Status |
|---|---------|-----------|--------|
| D1 | Tabela `patches_applied` própria? | **Sim** — migration `034_patches_applied.sql`, grava **por `.PTM`** (não por batch). Resolve o Quirk 2. | ✅ |
| D2 | Backup strategy | **Keep 10 por env**, configurável em `runtime.toml`; backup **obrigatório** quando env=prod. | ✅ |
| D3 | Detecção "já aplicado" | **Hash SHA-256 do `.PTM`** (primário) + check opcional via advpls se o smoke confirmar que existe. | ✅ |
| D4 | PROD safety | `--confirm-prod` obrigatório quando server é prod; backup obrigatório (sem `--no-backup`); respeita `allow_prod=false` no `runtime.toml`; audit trail estendido. | ✅ |
| D5 | Rollback granularity | **Ambos via flag** — `--rollback <patch-id>` (granular) e `--rollback-batch <ts>` (cascata, restaura RPO do início da batch). | ✅ |
| D6 | Ordenação dos `.PTM` | **Alfabética** (alinhado à impl de referência) — `sorted()` do nome. Corrige a suposição "prefixo numérico" da issue. | ✅ |
| D7 | ZIP handling | **Híbrido** — aceita `.zip`, descompacta internamente, aplica `.PTM` a `.PTM` com controle de ordem/hash/backup. | ✅ |
| D8 | Action name | **`patchApply`** (não `applyPatch`) — confirmado na doc oficial + scripts. | ✅ |
| D-impl | Granularidade de invocação | **1 `advpls cli` por `.PTM`** (um `.ini` por patch) — grava `patches_applied` + backup entre patches. Custo: N autenticações; medir overhead no smoke. | ✅ |

## Componentes

### 1. `cli/plugadvpl/apply_patch.py` — orquestrador

> **Decisão 2026-06-16 (revisada):** apply-patch nasce no **core**, espelhando o `tq`
> (`cli/plugadvpl/tq.py` + `@app.command` no `cli.py`), NÃO num pacote `plugadvpl_ops/` separado.
> Motivos: (a) o `tq` — irmão que iria pro mesmo sub-plugin — está no core; (b) o runner de
> migration lê de `importlib.resources.files("plugadvpl")/migrations`, então `034` tem que ficar
> no core de qualquer forma; (c) reúso total do core viraria casca num pacote separado.
> A extração do `plugadvpl_ops` fica como **refactor futuro que move `tq` + `apply-patch` juntos**.

Reúsa de `cli/plugadvpl/`:

| Peça reusada | Origem |
|---|---|
| Geração do `.ini` (`[authentication]` + `logToFile` + CP1252, tempdir `0700`/arquivo `0600`) | `compile.py:174-212` |
| Decode da saída do advpls (BOM UTF-16 + fallback CP1252) | `compile.py:112` (`decode_output`) |
| Invocação `advpls cli <ini>` + exit code | `compile.py` |
| Credenciais (keyring) | `credentials.py` |
| Registry de servers | `compile_servers.py` |
| Config TOML | `runtime_config.py` |

### 2. `.ini` gerado (canônico, da Fase 0)

```ini
logToFile=<tmp>/apply_patch.log
showConsoleOutput=true

[authentication]
action=authentication
server=...
port=...
secure=<0|1>
build=<BUILD_DO_APPSERVER>
environment=...
user=...
psw=...

[patchApply_1]
action=patchApply
patchFile=<tmp>/extracted/patch_aaa.ptm
localPatch=True
applyOldProgram=False

[patchApply_N]
...

[defragRPO]
action=defragRPO
```

**Defaults:** `localPatch=True`, `applyOldProgram=False` (guard-rail nativo), `[defragRPO]` sempre ao final.

> **Decisão de granularidade de invocação (D-impl):** aplicar **1 `advpls cli` por `.PTM`** (um `.ini` por patch) em vez de um `.ini` com N seções. Motivo: a impl de referência junta tudo num call e, se o 3º falha, os 2 primeiros já entraram no RPO mas nenhum é registrado (Quirk 2). Um call por PTM permite gravar `patches_applied` + backup **entre** patches. `defragRPO` roda 1x ao final da batch. *(confirmar no smoke se o overhead de N calls é aceitável; fallback = N seções com parse do log por patch.)*

### 3. Migration `034_patches_applied.sql`

```sql
CREATE TABLE patches_applied (
    id           INTEGER PRIMARY KEY,
    env          TEXT    NOT NULL,
    build        TEXT,
    ptm_name     TEXT    NOT NULL,
    ptm_hash     TEXT    NOT NULL,   -- SHA-256
    applied_at   TEXT    NOT NULL,   -- ISO-8601
    log_path     TEXT,
    batch_ts     TEXT,               -- agrupa patches da mesma execução (pro rollback cascata)
    backup_path  TEXT                -- RPO backup associado (pro rollback granular)
);
CREATE UNIQUE INDEX ux_patches_env_hash ON patches_applied(env, ptm_hash);
```

A `UNIQUE(env, ptm_hash)` é a idempotência: re-aplicar o mesmo `.PTM` no mesmo env vira skip.

### 4. Backup do RPO

advpls **não faz** backup no `patchApply` (Fase 0, Q4). O plugin copia o RPO ativo antes de cada patch → `rpo_backup/<env>/<batch_ts>/<ptm_name>.rpo` (path em `backup_path`). Rotação keep-N (D2).

### 5. Lock por env

`~/.plugadvpl/locks/<env>.lock` durante a batch — evita 2 devs aplicando ao mesmo tempo. Libera no finally.

## CLI surface

```bash
plugadvpl-ops apply-patch ./atualizacao_2026_05.zip --use-server qa
plugadvpl-ops apply-patch ./hotfix.PTM --use-server prd --confirm-prod
plugadvpl-ops apply-patch ./hotfix.PTM --use-server prd --dry-run
plugadvpl-ops apply-patch --list-applied --use-server prd
plugadvpl-ops apply-patch --rollback <patch-id> --use-server qa
plugadvpl-ops apply-patch --rollback-batch <batch-ts> --use-server qa
```

## Fluxo interno (corrigido vs issue)

```
1. Lê creds do keyring + valida server (reachable, RPO writable)
2. Se server.is_prod e não --confirm-prod -> aborta. Se allow_prod=false -> aborta.
3. Adquire lock <env>.lock
4. Input ZIP? -> descompacta em tmp/ (interno, híbrido D7)
5. Lista .PTM em ordem ALFABÉTICA (D6)
6. batch_ts = timestamp da execução
7. Pra cada .PTM (em ordem):
   |- hash SHA-256 -> SELECT em patches_applied WHERE env+hash
   |- já aplicado? -> skip + log
   |- backup do RPO -> rpo_backup/<env>/<batch_ts>/<ptm>.rpo
   |- gera .ini (1 patch) -> advpls cli -> captura/parse log
   |- sucesso? -> INSERT patches_applied (hash, ts, env, build, batch_ts, backup_path)
   |_ falha? -> restaura backup, aborta sequência (rollback até este ponto)
8. defragRPO (1x ao final, se houve ≥1 aplicado)
9. Libera lock
10. Reporta consolidado: N aplicados, M skipped, X falharam (JSON + humano)
```

## Códigos de erro (alinhar com `docs/exec-contract.md`)

| Código | Significado |
|---|---|
| 0 | Sucesso (todos aplicados ou skipped) |
| 2 | Erro de uso (flag faltando, prod sem `--confirm-prod`) |
| 3 | Server unreachable / auth falhou |
| 4 | Patch falhou no advpls (rollback executado) |
| 5 | Lock ocupado (outra batch em andamento) |
| 6 | `allow_prod=false` bloqueou |

## Anti-scope (da issue)

- Não distribui patches TOTVS (IP TOTVS).
- Não substitui TDS-VSCode pro workflow interativo.
- Sem patch reverso se o `.PTM` não suportar.
- Sem aplicação cross-env na mesma chamada (opcional via `--confirm-all-envs`, fora do MVP).

## Compliance

- `docs/reference-impl/` (scripts do Barbito) entra sob MIT **após sanitizar** link do Drive + qualquer referência identificável.
- Fixtures de `.PTM` em `cli/tests/fixtures/patches/` devem ser sintéticas — **nunca** `.PTM` real de cliente. Ver memória `git-compliance-sem-cliente`.

## Smoke test — EXECUTADO 2026-06-16 ✅ (resolve itens da Fase 0)

Rodado nos 2 OS contra `protheus_cmp` real (Linux porta 1234, Windows porta 1235), 3 pacotes oficiais TOTVS aplicados com sucesso + defrag, via os scripts de referência. Detalhes completos em [gaps/U6_APPLY_PATCH_RESEARCH.md](../../../gaps/U6_APPLY_PATCH_RESEARCH.md#smoke-test--executado-2026-06-16-).

**Achados que viram requisito de implementação:**

1. **🐛 `secure` DEVE ser `0`/`1`** — `secure=false` → advpls aborta com `[ERROR] stoi` na auth. Gerador de `.ini` valida numérico (reúso `compile.py`).
2. **⚠️ Exit code 0 não significa sucesso total** — advpls retorna 0 mesmo em **partial-apply** (`applyOldProgram` OFF aplica só recursos novos). O orquestrador **DEVE parsear o log** (`Patch (<nome>) successfully applied.` / `Only new sources are being applied`), não confiar em `$?`. Status no JSON: `applied` vs `partial` vs `failed`.
3. **`[ERROR] Unable to connect` é benigno** — advpls tenta secure→cai pra não-secure. Parser não trata como fatal.
4. **advpls NÃO aborta** em "recursos mais antigos que o RPO" — continua a sequência. defrag roda ao final.

**Risco remanescente pra smoke da Fase 3:** comportamento em **falha DURA** (patch corrompido/build incompatível) não exercitado — testar com `.PTM` propositalmente inválido.
