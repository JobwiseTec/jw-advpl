# U5 — `ingest-protheus` Design Spec

| Item | Valor |
|---|---|
| **Data** | 2026-05-21 (rev 2 — pivot após receber `COLETADB.tlpp` real) |
| **Status** | Spec aprovada; Fase 3 em pivot para contract real |
| **Issue tracker** | [#3](https://github.com/JoniPraia/plugadvpl/issues/3) |
| **Universo** | U5 — Live Protheus Inspector |
| **Target release** | v0.10.0 (core) |
| **Volume** | ~5-7 dias implementação distribuídos em 2-3 semanas |
| **Bloqueador anterior** | ✅ Resolvido — `COLETADB.tlpp` recebido em [`gaps/COLETADB.tlpp`](../../../gaps/COLETADB.tlpp) (2026-05-21) |
| **Pivot** | Contract real é **bundle pattern (CSV chunks via REST)**, não JSON inline. Veja Seção 5-bis. Seção 5 fica como histórico/aprendizado |

## 1. Propósito

Adicionar comando `plugadvpl ingest-protheus` que consome **dicionário Protheus via REST API ao vivo** (servido pelo `COLETADB.tlpp` instalado no AppServer do cliente), preenchendo o mesmo schema SQLite que hoje é populado por `ingest-sx` (CSV exportado do Configurador).

**Não substitui** `ingest-sx` — coexiste. Workflow offline preservado pra clientes que não vão liberar instalação no AppServer.

## 2. Motivação (resumo)

| Hoje (CSV) | Amanhã (REST) |
|---|---|
| Cliente exporta SX manualmente do Configurador | Plugin chama endpoint, pega JSON |
| Foto estática — vira velho rápido | Sempre o estado atual do banco |
| Limitado às ~11 tabelas que Configurador emite | Pode expor custom tables `Z*`/`X*` específicas do cliente |
| Workflow de N passos manuais | 1 comando |
| Sem detecção de drift | `sx-drift` reporta mudanças em prod sem commit |

Detalhes completos no [issue #3](https://github.com/JoniPraia/plugadvpl/issues/3).

## 3. Decisões fundamentais

| Decisão | Escolha | Justificativa |
|---|---|---|
| Comando novo vs flag em `ingest-sx` | **Comando novo `ingest-protheus`** | Workflows diferentes (REST vs filesystem), erros diferentes (rede vs encoding), config diferente. Comando dedicado evita union types na CLI |
| Cliente HTTP | **`httpx` (sync)** | Já é dep transitiva via uv ecosystem. Sync simplifica (não há paralelismo a ganhar aqui — single endpoint sequencial) |
| Schema do índice | **Reusa schema atual (migration 002)** | Os 11 SX tables permanecem. Custom tables (se COLETADB expuser) ganham migration 003 separada — fora do MVP |
| Persistência da config REST | **`runtime.toml` seção `[coletadb]`** | Igual padrão do `[appserver]`/`[auth]` já existente |
| Auth | **Reusa `credentials.py` (keyring OS)** | Bearer token ou Basic — config decide. Plugin já sabe keyring |
| Modo offline (CSV) | **Preservado intacto** | `ingest-sx` continua funcionando idêntico. Zero regressão |
| Auto-install do COLETADB | **Fase 4c, opt-in via flag `--install-server-component`** | Fora do MVP. Reusa `plugadvpl compile` quando entrar |
| Drift detection | **Comando separado `sx-drift`, Fase 4a** | Fora do MVP. `ingest-protheus` v1 só consome, não compara |

## 4. Arquitetura geral

```
┌───────────────────────────────┐
│  cli.py                       │   <- novo subcomando `ingest-protheus`
│   └─ ingest_protheus_cmd()    │
└──────────┬────────────────────┘
           │
           ▼
┌───────────────────────────────┐
│  coletadb_client.py (novo)    │   <- httpx client, retry, auth, paginação
│   └─ ColetaDBClient           │
│        ├─ health()            │
│        ├─ list_tables()       │
│        ├─ get_table_data()    │
│        └─ get_dump()          │
└──────────┬────────────────────┘
           │  JSON normalizado
           ▼
┌───────────────────────────────┐
│  ingest_rest.py (novo)        │   <- adapter: JSON do REST -> rows do schema
│   └─ ingest_via_rest()        │      Reusa _insert_* do ingest_sx.py
└──────────┬────────────────────┘
           │
           ▼
┌───────────────────────────────┐
│  index.db (schema atual)      │   <- mesma tabela `campos`, `gatilhos`, etc.
└───────────────────────────────┘
```

**Princípio**: separar **transporte** (`coletadb_client`) de **persistência** (`ingest_rest`). Cliente HTTP é testável standalone com mocks. Adapter reusa lógica de insert do `ingest_sx.py` (não duplica).

## 5-bis. Contrato REST REAL (após receber `COLETADB.tlpp` em 2026-05-21)

**Esta seção substitui a Seção 5 (que fica como histórico de aprendizado).**

O `COLETADB.tlpp` real implementa um **workflow bundle**: servidor gera arquivos CSV locais, cliente baixa em chunks de 4MB. Mais simples que JSON inline e reusa toda a machinery existente do `ingest_sx`.

### 5-bis.1 Endpoints (2, ambos POST)

```
POST /coletadb/run      -> gera CSVs no servidor + retorna manifest JSON
POST /coletadb/file     -> baixa bytes de um arquivo em chunks
```

Pré-requisito appserver.ini: `[HTTPV11]`/`[HTTPURI]` com `Security=1` (Basic auth nativa do AppServer).

### 5-bis.2 POST `/coletadb/run`

**Request** (body JSON, todos opcionais):
```json
{
  "modo": "enxuto",
  "threshold": 10,
  "base_dir": "\\temp\\",
  "ini_dir": "<path do AppServer*.ini>"
}
```

- `modo`: `"enxuto"` (só tabelas com ≥ threshold rows) ou `"completo"` (todas as SX)
- `threshold`: mínimo de linhas pra tabela contar como ativa (default 10)
- `base_dir`: pasta onde o bundle é criado (default `\temp\`)
- `ini_dir`: pasta dos `appserver*.ini` pra extrair jobs (default `DescobreRootPath()`)

**Response 200**:
```json
{
  "bundle_id": "abc123-uuid...",
  "bundle_dir": "\\temp\\20260521_153000_abc\\",
  "modo": "enxuto",
  "threshold": 10,
  "chunk_size": 4194304,
  "files": [
    {
      "name": "SX3.csv",
      "path": "\\temp\\20260521_153000_abc\\SX3.csv",
      "size_bytes": 12345678,
      "chunks": 3,
      "sha256": "abc..."
    }
  ]
}
```

**Errors**: 400 (JSON inválido), 422 (modo inválido), 500 (DB inacessível, etc.)

### 5-bis.3 POST `/coletadb/file`

**Request** (body JSON):
```json
{
  "path": "\\temp\\20260521_153000_abc\\SX3.csv",
  "offset": 0,
  "limit": 4194304
}
```

- `path`: full path do arquivo (do manifest)
- `offset`: byte offset (default 0)
- `limit`: bytes a ler (default 4MB, máximo 4MB)

**Response 200**:
- Body: bytes do chunk (binário, `Content-Type: application/octet-stream`)
- Header `X-Total-Size`: tamanho total do arquivo
- Header `X-Chunk-Range`: `<start>-<end>/<total>`
- Header `Content-Length`: bytes deste chunk

**Errors**:
- 400 — path ausente, path traversal (`..`), extensão não-csv
- 404 — arquivo não existe ou inacessível
- 416 — offset alem do EOF

### 5-bis.4 Cobertura — mais rica que esperado

Spec original previa 11 tabelas SX. COLETADB real entrega **muito mais**:

| Bloco | Conteúdo |
|---|---|
| SX padrão | SIX, SX1, SX2, SX3, SX5, SX6, SX7, SX9, SXA, SXB, SXG (11) |
| **SX extras** | **XXA, XAM, XAL** (+3 — novos no plugadvpl) |
| **MPMENU** | MPMENU_MENU, _FUNCTION, _ITEM, _I18N, _KEY_WORDS, _RW (6) |
| **SCHEDULES** | Agendamentos do scheduler interno (DBSelectArea sob SCHEDULES) |
| **JOBS** | Parse do `appserver*.ini` (multi-INI, recursivo) |
| **RECORD_COUNTS** | Inventário de rows físicas por tabela (DBMS query) |

MVP foca em **só SX padrão** (paridade com `ingest_sx`). XXA/XAM/XAL + MPMENU/SCHEDULES/JOBS/RECORD_COUNTS ficam pra **Fase 4** (extends schema, comandos novos).

### 5-bis.5 Auth

Não há `Authorization` no fluxo de `oRest:` do `.tlpp` — usa **Basic auth nativa do AppServer** via `Security=1` em `[HTTPURI]` do appserver.ini. Cliente envia `Authorization: Basic <base64>` direto, AppServer valida user/senha do dicionário Protheus.

**Implicação prática**: plugin reusa `credentials.py` (keyring) — **mesmo user/senha** do `compile` funciona aqui. Sem necessidade de bearer token separado.

### 5-bis.6 Encoding

- **JSON envelope**: UTF-8 (`DecodeUtf8`/`EncodeUtf8` no fonte)
- **CSVs gerados**: **CP1252** (encoding canonical do Configurador)
- Detecção via `chardet` no `_read_csv` já existente — já funciona

### 5-bis.7 Versionamento

Sem `/health` dedicado. Versão é `CDB_VERSION = "1.0.0"` hardcoded no fonte, retornada no manifest do `/run` (no MVP, **não exposta** — mas dá pra ler do response body). Health check standalone do plugin = fazer `/run` em modo=enxuto threshold=999999 (extrai zero, valida só conectividade).

### 5-bis.8 Workflow do cliente (plugin)

```
1. POST /coletadb/run com {"modo":"enxuto","threshold":10}
2. Recebe manifest com files[]
3. Para cada file no manifest:
   a. Loop POST /coletadb/file com offset += chunk_size
   b. Reassembly em tmp local
   c. Verifica sha256
4. Chama ingest_sx(tmp_dir, db_path) -- REUSA machinery existente
5. Cleanup tmp
```

### 5-bis.9 Não cobertos no MVP (pra Fase 4)

- XXA/XAM/XAL — exigem migrations novas no schema
- MPMENU — outro Universo (menus)
- SCHEDULES/JOBS — Universo 3 (workflow)
- RECORD_COUNTS — popula tabela `tabelas.num_rows` (já existe column placeholder)

---

## 5. Contrato REST original (**OBSOLETO** — mantido como histórico)

> Esta seção foi a especulação inicial antes de receber o `COLETADB.tlpp`. Documentei errado: assumi JSON inline, endpoints `/health`/`/tables`/`/dump`, bearer token. Real é bundle CSV + 2 endpoints POST + Basic auth do AppServer. Veja Seção 5-bis acima.

### 5.1 Endpoints

```
GET  /rest/coletadb/health
GET  /rest/coletadb/tables
GET  /rest/coletadb/dump?tables=SX1,SX3,SX7&format=full
GET  /rest/coletadb/table/{nome}
```

### 5.2 Health

```http
GET /rest/coletadb/health
Authorization: Bearer <token>

200 OK
{
  "version": "1.0.0",
  "protheus_build": "7.00.240223P",
  "exposed_tables": ["SX1", "SX2", "SX3", "SX5", "SX6", "SX7", "SX9", "SXA", "SXB", "SXG", "SIX"],
  "extras": ["Z01", "Z02"]
}
```

### 5.3 Dump completo

```http
GET /rest/coletadb/dump?tables=SX3
Authorization: Bearer <token>

200 OK
{
  "table": "SX3",
  "row_count": 187633,
  "rows": [
    {
      "X3_ARQUIVO": "SA1",
      "X3_CAMPO": "A1_COD",
      "X3_TIPO": "C",
      "X3_TAMANHO": 6,
      "X3_DECIMAL": 0,
      "X3_TITULO": "Codigo",
      "X3_DESCRIC": "Codigo do Cliente",
      ...
    },
    ...
  ]
}
```

Formato espelha o CSV atual do Configurador — colunas com nome físico `X3_*`/`X2_*`/etc., facilita reuso do `ingest_sx._insert_*`.

### 5.4 Paginação (se necessária pra tabelas grandes)

```http
GET /rest/coletadb/dump?tables=SX3&offset=0&limit=10000

200 OK
{
  "table": "SX3",
  "row_count": 187633,
  "offset": 0,
  "limit": 10000,
  "has_more": true,
  "next_offset": 10000,
  "rows": [...]
}
```

Cliente faz loop de paginação até `has_more=false`.

### 5.5 Códigos de erro

| Status | Significado | Ação do cliente |
|---|---|---|
| 200 | OK | Processa |
| 401 | Auth inválida | Limpa keyring, pede novamente |
| 403 | Tabela não exposta | Avisa, segue com as outras |
| 404 | Endpoint não existe | "COLETADB não instalado, instalar?" |
| 5xx | Server error | Retry exponencial (3 tentativas), depois aborta |

### 5.6 Validação contra real

Quando `COLETADB.tlpp` chegar:
- Comparar campo-a-campo o JSON real vs o esperado
- Adaptar `coletadb_client.py` pra normalizar diffs (rename de chaves, ordem diferente, etc.)
- Atualizar este doc com schema validado, remover marcador "ESPECULATIVO"

## 6. Config (alinhada ao protocolo real)

Auth reusa `credentials.py` (mesmo padrão do `compile`) — não precisa seção `[coletadb]` separada para auth. Resolução por camadas:
1. `--user`/`--password` direto
2. Env vars `PROTHEUS_USER`/`PROTHEUS_PASS` (mesmo padrão do compile)
3. Keyring do OS (`plugadvpl` service, key `<endpoint>:user`/`<endpoint>:password`)

Endpoint pode vir de `--endpoint` flag ou `[coletadb] endpoint = "..."` no `runtime.toml`:

```toml
[coletadb]
endpoint = "http://protheus-cliente:8181/rest/coletadb"
modo = "enxuto"                   # "enxuto" | "completo"
threshold = 10                    # rows minimas pra tabela contar como ativa
base_dir = "\\temp\\"             # path NO SERVIDOR onde bundle e criado
ini_dir = ""                      # vazio = DescobreRootPath() no servidor
timeout_s = 60                    # timeout do /run pode ser alto (gera CSVs)
retry_count = 3
verify_ssl = true
chunk_size = 4194304              # 4MB, deve casar com CDB_API_CHUNK do servidor
```

## 7. CLI surface

```bash
# Workflow basico
plugadvpl ingest-protheus --endpoint http://protheus:8181/rest/coletadb --user U --password P

# Auth via env vars
PROTHEUS_USER=U PROTHEUS_PASS=P plugadvpl ingest-protheus --endpoint ...

# Modo completo (todas SX, nao so ativas)
plugadvpl ingest-protheus --endpoint ... --modo completo --user U --password P

# Threshold customizado
plugadvpl ingest-protheus --endpoint ... --threshold 100 --user U --password P

# Dry-run (so health-check via /run + descarta manifest)
plugadvpl ingest-protheus --endpoint ... --dry-run --user U --password P

# Verbose (mostra progress de cada chunk)
plugadvpl ingest-protheus --endpoint ... -v --user U --password P

# JSON output (CI/CD)
plugadvpl ingest-protheus --endpoint ... --format json --user U --password P
```

**Removido do MVP** (vs Seção 5 obsoleta):
- ~~`--tables SX1,SX3`~~ — servidor extrai bundle completo (filtragem pos-download não vale a pena)
- ~~`--token`~~ — auth é Basic (AppServer Security=1)
- ~~`--check`~~ standalone — agora `--dry-run` faz o papel

## 8. Output esperado

### 8.1 Human-friendly (default)

```
[INFO] Conectando em http://protheus-cliente:8181/rest/coletadb...
[INFO] Health OK: COLETADB v1.0.0, build 7.00.240223P, 11 tabelas expostas
[INFO] Baixando SX1 (59.498 rows)... OK em 1.2s
[INFO] Baixando SX2 (XX rows)... OK em 0.4s
...
[INFO] Ingest completo: 11/11 tabelas, 421.234 rows em 18.3s
[OK] Indice atualizado em ./.plugadvpl/index.db
```

### 8.2 JSON (--format json)

```json
{
  "ok": true,
  "endpoint": "http://protheus-cliente:8181/rest/coletadb",
  "coletadb_version": "1.0.0",
  "protheus_build": "7.00.240223P",
  "tables": [
    {"name": "SX1", "rows": 59498, "duration_ms": 1200, "status": "ok"},
    {"name": "SX2", "rows": 234, "duration_ms": 400, "status": "ok"},
    ...
  ],
  "total_rows": 421234,
  "duration_ms": 18300,
  "db_path": "./.plugadvpl/index.db"
}
```

## 9. Estratégia de testes

### 9.1 Unit (`cli/tests/unit/test_coletadb_client.py`)

- Mock `httpx.Client` via `respx` ou `httpx.MockTransport`
- Cada endpoint testado isoladamente: health, list_tables, get_dump, paginação
- Auth: bearer e basic
- Erros: 401, 403, 404, 5xx + retry
- Timeout
- SSL verify on/off

### 9.2 Integration (`cli/tests/integration/test_ingest_protheus.py`)

- Fake REST server em fixtures (httpx mock transport)
- Roda `ingest_protheus()` end-to-end
- Verifica DB resultante == DB que `ingest_sx` produz com o mesmo dataset
- **Crucial**: garante paridade funcional entre os 2 ingestores

### 9.3 Smoke (`cli/tests/smoke/test_coletadb_real.py`, opcional)

- Contra endpoint real (`@pytest.mark.smoke`, skipa se env var `COLETADB_REAL_ENDPOINT` não setada)
- Valida que JSON real bate com schema deste doc
- Pula no CI default, roda local quando endpoint disponível

### 9.4 TDD red→green

Cada componente:
1. Test falhando (red)
2. Implementação mínima pra passar (green)
3. Refactor sem quebrar

Sem CLI implementada antes do client + adapter testados isoladamente.

## 10. Fases de entrega (refinamento do issue #3)

### Fase 0 — Research (BLOQUEADO)

- ⏸ Aguarda `COLETADB.tlpp` do autor
- Saída: validação do contract da Seção 5 contra source real

### Fase 1 — Spec MD (este doc) — **APROVAÇÃO necessária**

### Fase 2 — Contract canônico (0.5 dia)

- `docs/coletadb-contract.md` — versão pública/agnóstica da Seção 5 deste doc
- Permite outras impls (não só o `.tlpp`) conformantes

### Fase 3 — Implementação (3-4 dias, TDD)

1. **Test fixtures** — JSON examples por endpoint
2. **`coletadb_client.py`** — TDD red→green
3. **`ingest_rest.py`** — adapter, reusa `ingest_sx._insert_*`
4. **`cli.py`** — subcomando `ingest-protheus`
5. **Migration 003 ENV?** — não, schema reusado. Sem migration.
6. **Validação cruzada**: roda CSV ingest + REST ingest contra mesmo dataset → DB idêntico

### Fase 4 — Custom tables + drift + auto-install (FORA do MVP)

- 4a `sx-drift` — comando novo, compara DB local vs REST atual
- 4b Custom tables `Z*`/`X*` — migration 004 se necessário
- 4c Auto-install do COLETADB — usa `plugadvpl compile`

### Fase 5 — Skill + docs (1 dia)

- Skill `/plugadvpl:ingest-protheus`
- README — seção "Ingestão via REST"
- `docs/factory-architecture.md` — diagrama CSV path + REST path coexistindo

### Fase 6 — Release v0.10.0

- Bump major-minor (feature significativa)
- CHANGELOG completo
- Tag anotada

## 11. Schema impact

**MVP: zero mudança de schema.** Reusa as 11 tabelas SX criadas pela migration 002. Mesmo `_insert_*` lógica do `ingest_sx.py`.

Fase 4b (custom tables) terá migration própria — fora do MVP.

## 12. Auth strategy

```python
# Resolução em camadas (igual padrao do [auth] do compile):
1. env var (COLETADB_TOKEN) — CI/CD friendly
2. keyring do OS (service="plugadvpl-coletadb", key=<server>:token)
3. erro com 2 paminhos didáticos
```

Plugin **nunca grava token em arquivo** (igual padrão das credenciais do AppServer).

Comandos:
- `plugadvpl ingest-protheus --set-token <server>` (prompt seguro, salva no keyring)
- `plugadvpl ingest-protheus --clear-token <server>` (remove)

## 13. Error handling

| Erro | UX |
|---|---|
| Endpoint não responde | "Conectividade falhou. Tente: 1) ping, 2) check VPN, 3) `--check`" |
| 401 unauthorized | "Token inválido. Renove com `--set-token <server>`" |
| 404 endpoint | "COLETADB não encontrado em <url>. Instalado? Em Fase 4c teremos `--install-server-component`. Por agora: peça ao TI do cliente pra compilar `COLETADB.tlpp`." |
| Tabela ausente no response | Warning, ingestor segue com as outras |
| Schema diff vs esperado | Erro estruturado: "Campo X3_ZZZ desconhecido. Atualize plugadvpl ou abra issue." |
| Timeout | Retry exponencial (3×), depois aborta com hint de aumentar `timeout_s` |

## 14. Critérios de aceitação

1. ✅ `plugadvpl ingest-protheus --use-server <X>` popula `index.db` com mesma estrutura que `ingest-sx` faria
2. ✅ DB resultante passa em **todos** os testes existentes do `ingest_sx` (paridade funcional total)
3. ✅ `plugadvpl status` reporta tabelas SX populadas corretamente
4. ✅ `plugadvpl impacto <campo>` funciona idêntico, independente da fonte (CSV ou REST)
5. ✅ Cobertura de testes ≥ 90% nos módulos novos
6. ✅ Suite full continua 855+ passed sem regressão
7. ✅ Auth via keyring funciona em Win + macOS + Linux (CI matrix)
8. ✅ Documentação atualizada (README + skill + docs/architecture)

## 15. O que NÃO entra no MVP (anti-scope)

- ❌ Substituir `ingest-sx` (CSV preservado)
- ❌ Cliente runtime genérico do Protheus (Categoria B do `gaps/ideias.md`)
- ❌ Escrita no Protheus via REST — só leitura
- ❌ Execução de queries SQL ad-hoc
- ❌ `sx-drift` (Fase 4a, posterior)
- ❌ Custom tables `Z*`/`X*` (Fase 4b)
- ❌ Auto-install do COLETADB (Fase 4c)
- ❌ UI/dashboard — só CLI

## 16. Open questions (a resolver na Fase 0 quando `.tlpp` chegar)

1. Formato real do JSON: campos com nome físico (`X3_ARQUIVO`) ou normalizado (`tabela`)?
2. Paginação: o COLETADB suporta? Como?
3. Auth: bearer? basic? algo custom com hash Sha2_256 que o autor mencionou?
4. `/health` retorna versão do COLETADB e/ou do Protheus?
5. Tabelas extras (`Z*`/`X*`) expostas via mesmo `/dump` ou endpoint separado?
6. Rate limiting? Concurrent requests permitidos?

Cada uma vira ajuste pontual na Seção 5 + adapter no `coletadb_client.py`.

## 17. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Contrato real difere muito do especulativo | Cliente é fino, adapter centraliza normalização — refactor localizado |
| `.tlpp` nunca chega | Plano B: contract permanece especulativo, server impl genérica (Go/Python servindo o mesmo schema) também serve |
| Performance ruim em base grande | Paginação obrigatória + benchmark vs CSV ingest |
| Drift de schema futuro do Protheus | Health endpoint reporta versão, plugin avisa "schema versão X não suportado, atualize plugadvpl" |
| Tokens vazando em logs | Reusa `redact_secrets` pattern já existente no `ingest.py` |

## 18. Próximos passos (pós-aprovação desta spec)

1. ✅ Spec aprovada por @JoniPraia
2. → Cria PR feature branch `feat/u5-ingest-protheus`
3. → Fase 2 (contract canônico) — 0.5 dia
4. → Fase 3 (implementação TDD) — 3-4 dias
5. → Fase 5 (skill + docs) — 1 dia
6. → Release v0.10.0

Quando `.tlpp` chegar (não-bloqueante pra Fase 3):
- Valida contract real vs Seção 5
- Adapta `coletadb_client.py` se houver diff
- Roda smoke test

---

**Aguardando aprovação da spec antes de iniciar Fase 2.**
