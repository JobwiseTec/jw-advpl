---
description: Indexa Dicionário SX via REST API do COLETADB (Universo 5) — workflow ao vivo, sem CSV manual
disable-model-invocation: true
arguments: [opcoes]
allowed-tools: [Bash]
---

# `/plugadvpl:ingest-protheus`

Indexa o Dicionário SX (SX1..SXG + SIX) via REST API do `COLETADB.tlpp` instalado no AppServer Protheus do cliente. Substitui o workflow manual do `ingest-sx` (CSV exportado do Configurador) por **dump ao vivo via HTTP**.

Convive com `/plugadvpl:ingest-sx` — quem não tem `COLETADB` instalado continua usando CSV.

Pré-requisito: rodar `/plugadvpl:init` antes (cria `.plugadvpl/index.db`).

## Como funciona (bundle pattern)

```
1. POST /coletadb/run     -> servidor gera CSVs locais em \temp\<ts>_<uuid>\
                          -> retorna manifest com paths, sizes, sha256
2. POST /coletadb/file    -> cliente baixa cada CSV em chunks de 4MB
                          -> reassembly + verifica sha256
3. ingest_sx(tmp_dir)     -> reusa machinery existente do CSV path
```

Auth via **HTTP Basic** (AppServer `Security=1`) — mesmas credenciais do `/plugadvpl:compile`.

## Uso

```
/plugadvpl:ingest-protheus --endpoint <url> [--user U] [--password P]
/plugadvpl:ingest-protheus --endpoint <url> --modo completo
/plugadvpl:ingest-protheus --endpoint <url> --dry-run
```

## Argumentos

- `--endpoint URL` — base REST do Protheus (ex: `http://protheus:8181/rest`). **Obrigatório**.
- `--user USER` — Basic auth user. Fallback: env var `PROTHEUS_USER`.
- `--password PASS` — Basic auth password. Fallback: env var `PROTHEUS_PASS`.
- `--modo {enxuto|completo}` — `enxuto` (só tabelas com ≥ threshold rows, default) ou `completo` (todas as SX).
- `--threshold N` — min de linhas pra tabela contar como ativa (default 10, só em modo enxuto).
- `--base-dir PATH` — pasta NO SERVIDOR onde bundle é criado (default `\temp\`).
- `--ini-dir PATH` — pasta NO SERVIDOR dos `appserver*.ini` (default `DescobreRootPath()`).
- `--dry-run` — só roda `/coletadb/run` e mostra manifest, não baixa nem ingere.
- `--timeout-run N` — timeout do `/coletadb/run` (default 300s — gera CSVs).
- `--timeout-file N` — timeout do `/coletadb/file` por chunk (default 60s).

## Execucao

```bash
uvx plugadvpl@0.32.0 ingest-protheus $ARGUMENTS
```

## Exemplos

- `/plugadvpl:ingest-protheus --endpoint http://protheus:8181/rest --user admin --password $PASS`
- `PROTHEUS_USER=admin PROTHEUS_PASS=$PASS /plugadvpl:ingest-protheus --endpoint http://protheus:8181/rest`
- `/plugadvpl:ingest-protheus --endpoint http://protheus:8181/rest --modo completo` (todas SX, inclusive vazias)
- `/plugadvpl:ingest-protheus --endpoint http://protheus:8181/rest --dry-run` (preview do manifest sem download)

## Pré-requisitos no AppServer

O `COLETADB.tlpp` (~1800 linhas, license **MIT**, reference impl em [`docs/reference-impl/coletadb.tlpp`](../../docs/reference-impl/coletadb.tlpp)) precisa estar **compilado e ativo** no AppServer. Caso `/run` retorne **404**, peça ao TI do cliente pra:

1. Copiar `docs/reference-impl/coletadb.tlpp` pro RPO custom
2. Compilar via TDS-VSCode ou `plugadvpl compile coletadb.tlpp`
3. Confirmar `[HTTPV11]` + `[HTTPURI]` habilitados no `appserver.ini`:
   ```ini
   [HTTPV11]
   ENABLE=1
   PORT=8080
   
   [HTTPURI]
   URL=/rest
   PrepareIn=<emp>,<fil>
   Security=1
   CORSEnable=1
   ```

Em release futura (Fase 4c) — flag `--install-server-component` fará isso automático via `plugadvpl compile`.

## Saida

Saída em duas partes:

1. Counters do bundle: `files_downloaded`, `bytes_downloaded`, `bundle_id`, `duration_ms`
2. Counters do ingest interno: rows por tabela SX (mesma estrutura do `ingest-sx`)

Re-rodar é idempotente — cada `/run` gera novo `bundle_id`; `ingest_sx` faz `INSERT OR REPLACE`.

## Paridade com ingest-sx

O DB resultante deste comando é **funcionalmente idêntico** ao produzido por `/plugadvpl:ingest-sx` rodado contra o CSV equivalente. Comandos downstream (`/plugadvpl:impacto`, `/plugadvpl:gatilho`, `/plugadvpl:sx-status`) funcionam idêntico independente da fonte.

## Diferenças de ingest-sx

| | `ingest-sx` (CSV) | `ingest-protheus` (REST) |
|---|---|---|
| Pré-requisito | CSV exportado do Configurador | `COLETADB.tlpp` no AppServer |
| Freshness | Foto do momento da exportação | Estado atual do banco |
| Trabalho do dev | Pedir export → receber zip → descompactar → ingest | 1 comando |
| Auth | Não precisa | Basic (mesmas creds do compile) |
| Tabelas | 11 SX padrão | **21 tabelas** (11 SX + XXA/XAM/XAL + 6 MPMENU + SCHEDULES + JOBS + RECORD_COUNTS — cobertura 100% do bundle) |
| Drift detection | Não | Sim (Fase 4a, futuro) |
| Conectividade | Não (offline) | Sim (HTTP ao AppServer) |

## Erros comuns

- **`--endpoint obrigatorio`** — passe `--endpoint <url>`
- **`Auth obrigatoria`** — passe `--user`/`--password` ou defina `PROTHEUS_USER`/`PROTHEUS_PASS`
- **`404 Not Found em /coletadb/run`** — COLETADB não compilado no AppServer (vide pré-requisitos)
- **`401 Unauthorized`** — user/senha inválidos
- **`sha256 mismatch em X.csv`** — arquivo corrompido durante transfer (rede flaky) — rode novamente
- **`Conectividade falhou`** — AppServer fora do ar, VPN, firewall, ou `[HTTPV11]` desabilitado

## Roadmap

- ✅ **Fase 3** (v0.11.0) — comando básico via bundle pattern (11 SX padrão)
- ✅ **Fase 4b** (v0.12.0 + v0.13.0) — cobertura 21/21 (XXA/XAM/XAL + MPMENU/SCHEDULES/JOBS + RECORD_COUNTS)
- 🔜 **Fase 4a** — `plugadvpl sx-drift` (compara DB local vs estado atual via REST)
- 🔜 **Fase 4c** — auto-install do COLETADB via `plugadvpl compile`
- 🔜 **Hash com algoritmo dinâmico** — server v1.0.3+ emite `hash_algo` (sha256/sha1/md5) + `hash_partial`. Cliente Python honra (v0.13.1+, em PR)
