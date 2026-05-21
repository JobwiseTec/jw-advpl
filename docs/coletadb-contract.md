# COLETADB REST Contract — `plugadvpl ingest-protheus`

> Esta é a especificação **canônica e agnóstica** do contrato REST que o `plugadvpl ingest-protheus` consome. Qualquer servidor que responda esse contrato funciona — não há amarração com a implementação específica do `COLETADB.tlpp`. Reference impl em [`gaps/COLETADB.tlpp`](../gaps/COLETADB.tlpp) (autor: tbarbito, license a confirmar).

| Item | Valor |
|---|---|
| **Versão** | 1.0.0 (validada contra `COLETADB.tlpp` em 2026-05-21) |
| **Status** | Stable (post-pivot da Seção 5 especulativa) |
| **Tipo de transporte** | HTTP/HTTPS REST + JSON envelope + binary chunks |
| **Padrão** | Bundle pattern (servidor gera CSV local; cliente baixa em chunks) |
| **Spec MD** | [`docs/superpowers/specs/2026-05-21-u5-ingest-protheus.md`](superpowers/specs/2026-05-21-u5-ingest-protheus.md) §5-bis |

## 1. Princípio

Servidor **gera arquivos CSV localmente** num bundle versionado (UUID + timestamp) e expõe **download em chunks** via REST. Cliente baixa CSVs e processa offline. **Não há leitura de banco via JSON inline** — formato CSV reusa o mesmo formato exportado pelo Configurador, permitindo que a machinery existente (`ingest_sx`) consuma sem mudança.

## 2. Endpoints

### 2.1 Base path

Cliente concatena o `endpoint` configurado com os paths abaixo. Servidor espera `[HTTPV11]` + `[HTTPURI]` configurados no `appserver.ini` com `Security=1` (auth obrigatória) e `CORSEnable=1` (cliente externo).

```
POST {base}/coletadb/run
POST {base}/coletadb/file
```

Exemplo: se `endpoint = "https://protheus.cliente.com:8181/rest"`, então `POST https://protheus.cliente.com:8181/rest/coletadb/run`.

### 2.2 `POST /coletadb/run` — gera bundle + retorna manifest

**Propósito**: dispara a extração no servidor (DBMS query + escrita de CSVs em disk) e retorna manifest com paths/sizes/hashes.

**Request**:
```http
POST {base}/coletadb/run
Content-Type: application/json
Authorization: Basic <base64(user:pass)>

{
  "modo": "enxuto",
  "threshold": 10,
  "base_dir": "\\temp\\",
  "ini_dir": "<path do AppServer*.ini>"
}
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `modo` | string | não | `"enxuto"` (só tabelas com ≥ threshold rows) ou `"completo"` (todas). Default `"enxuto"` |
| `threshold` | integer | não | Min de linhas pra tabela contar como ativa. Default 10 |
| `base_dir` | string | não | Pasta NO SERVIDOR onde bundle é criado. Default `\temp\` |
| `ini_dir` | string | não | Pasta dos `appserver*.ini` pra extrair jobs. Default = `DescobreRootPath()` |

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

| Campo | Tipo | Descrição |
|---|---|---|
| `bundle_id` | string | UUID do bundle (auditável) |
| `bundle_dir` | string | Path NO SERVIDOR onde os CSVs moram |
| `modo`/`threshold` | echo dos params usados | Útil pra log |
| `chunk_size` | integer | Tamanho do chunk em bytes (4MB padrão) |
| `files[]` | array | Lista de arquivos gerados |
| `files[].name` | string | Nome do arquivo (ex: `SX3.csv`) |
| `files[].path` | string | Full path NO SERVIDOR (usado no `/file`) |
| `files[].size_bytes` | integer | Tamanho total do arquivo |
| `files[].chunks` | integer | Quantos chunks serão necessários |
| `files[].sha256` | string | Hash de integridade (verificação cliente) |

**Errors**: `400` (JSON inválido), `422` (modo inválido), `500` (DB inacessível, falha de escrita).

### 2.3 `POST /coletadb/file` — baixa chunk de um arquivo

**Propósito**: cliente lê os bytes de um arquivo do bundle, com paginação por offset.

**Request**:
```http
POST {base}/coletadb/file
Content-Type: application/json
Authorization: Basic <base64(user:pass)>

{
  "path": "\\temp\\20260521_153000_abc\\SX3.csv",
  "offset": 0,
  "limit": 4194304
}
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `path` | string | sim | Full path do arquivo (do manifest) |
| `offset` | integer | não | Byte offset (default 0) |
| `limit` | integer | não | Bytes a ler (default 4MB, máximo 4MB) |

**Response 200**:
- Body: bytes binários do chunk
- `Content-Type: application/octet-stream`
- Headers customizados:
  - `X-Total-Size: <total bytes>` — tamanho total do arquivo
  - `X-Chunk-Range: <start>-<end>/<total>` — slice deste chunk
  - `Content-Length: <bytes>` — bytes deste chunk

**Loop do cliente**: incrementa `offset += chunk_size` até `offset >= X-Total-Size` ou até ler `size_bytes` bytes acumulados.

**Errors**:
- `400` — path ausente, path traversal (`..`), extensão != `.csv`
- `404` — arquivo não existe ou inacessível
- `416` — offset alem do EOF

## 3. Conteúdo dos arquivos do bundle

| Arquivo | Conteúdo | Formato |
|---|---|---|
| `SIX.csv` | Índices | CP1252, header `INDICE`, `ORDEM`, `CHAVE`, ... |
| `SX1.csv` | Perguntas | CP1252, header `X1_GRUPO`, `X1_ORDEM`, ... |
| `SX2.csv` | Tabelas | CP1252, header `X2_CHAVE`, `X2_NOME`, `X2_MODO`, ... |
| `SX3.csv` | Campos | CP1252, header `X3_ARQUIVO`, `X3_CAMPO`, ... |
| `SX5.csv` | Tabelas genéricas | CP1252, header `X5_FILIAL`, `X5_TABELA`, ... |
| `SX6.csv` | Parâmetros MV_* | CP1252, header `X6_VAR`, `X6_CONTEUD`, ... |
| `SX7.csv` | Gatilhos | CP1252, header `X7_CAMPO`, `X7_SEQUENC`, ... |
| `SX9.csv` | Relacionamentos | CP1252, header `X9_DOM`, `X9_CDOM`, ... |
| `SXA.csv` | Pastas | CP1252, header `XA_ALIAS`, `XA_ORDEM`, ... |
| `SXB.csv` | Consultas F3 | CP1252, header `XB_ALIAS`, `XB_TIPO`, ... |
| `SXG.csv` | Grupos de campo | CP1252, header `XG_GRUPO`, `XG_DESCRIC`, ... |
| `XXA.csv`, `XAM.csv`, `XAL.csv` | (não cobertas no MVP) | — |
| `MPMENU_*.csv` | (não cobertas no MVP) | 6 tabelas (menus completos) |
| `SCHEDULES.csv` | (não cobertas no MVP) | Agendamentos |
| `JOBS.csv` | (não cobertas no MVP) | Parse de `appserver*.ini` |
| `RECORD_COUNTS.csv` | (não cobertas no MVP) | Inventário de rows físicas por tabela |

Formato CSV idêntico ao exportado pelo Configurador → Misc → Exportar Dicionário. Compatível com `ingest_sx` existente.

**MVP do plugadvpl**: consome só os 11 arquivos SX padrão. Os extras (XXA/XAM/XAL, MPMENU, SCHEDULES, JOBS, RECORD_COUNTS) ficam pra Fase 4.

## 4. Autenticação

Servidor **DEVE** usar HTTP Basic auth via `[HTTPURI] Security=1` do appserver.ini. AppServer valida user/senha contra o dicionário do Protheus.

```http
Authorization: Basic <base64(user:pass)>
```

**Sem Bearer tokens** — auth é do AppServer, mesmo padrão do TDS-VSCode/compile. Plugin reusa `credentials.py` (mesmo user/senha do compile).

## 5. Códigos de erro

| Status | Significado | Body |
|---|---|---|
| 200 | Sucesso | Conforme seção 2 |
| 400 | Request inválido (JSON malformado, path traversal, etc.) | `{"error": "msg"}` |
| 401 | Auth ausente ou inválida | (response do AppServer) |
| 403 | Auth ok mas sem permissão pro env | (response do AppServer) |
| 404 | Endpoint não existe (COLETADB não instalado) ou arquivo do bundle não encontrado | `{"error": "msg"}` |
| 416 | Offset alem do EOF do arquivo | `{"error":"...","total_size":N}` |
| 422 | Validação de body (`modo` inválido, etc.) | `{"error": "msg"}` |
| 500 | Erro interno (DB, escrita, etc.) | `{"error": "msg"}` |

Cliente trata:
- **401/403**: limpa keyring, pede credenciais novamente
- **404 em `/run`**: oferece hint "COLETADB não instalado"
- **404 em `/file`**: arquivo do manifest sumiu (TTL do bundle?) — refaz `/run`
- **416**: terminou de baixar, sai do loop
- **5xx**: retry exponencial 3×, depois aborta

## 6. Workflow completo (cliente)

```
1. POST /coletadb/run com {"modo":"enxuto","threshold":10}
   <- manifest com files[]
   
2. Cria tmp dir local
3. Para cada file no manifest:
   a. Loop:
      - POST /coletadb/file com {"path":file.path,"offset":N,"limit":4194304}
      - Acumula bytes no tmp_dir/file.name
      - offset += bytes_lidos
      - Se offset >= file.size_bytes ou status 416, sai do loop
   b. Verifica hashlib.sha256(tmp_dir/file.name).hexdigest() == file.sha256
   
4. Chama ingest_sx(tmp_dir, db_path) -- REUSA machinery existente

5. Cleanup tmp_dir
```

Idempotência: cada `/run` gera novo `bundle_id` (UUID). Bundles antigos ficam no servidor até cleanup manual. Cliente pode usar bundles existentes via `--bundle-id <id>` em release futura (não no MVP).

## 7. Encoding

- **JSON envelope (request body + response body)**: UTF-8 obrigatório (servidor faz `DecodeUtf8`/`EncodeUtf8`)
- **CSVs no bundle**: CP1252 (encoding canonical Protheus). Cliente reusa `chardet` para detectar via `_read_csv` existente

## 8. Performance e limites

| Item | Valor |
|---|---|
| Timeout do `/run` | 60-300s (gera CSVs do dicionário completo, pode demorar) |
| Timeout do `/file` | 30s (lê 4MB de disk + envia) |
| Chunk size | 4 MB (limite REST default = 8 MB; ficamos com folga) |
| Retry count | 3 com backoff exponencial (2, 4, 8s) |
| Concurrent | 1 (sequencial — servidor processa um arquivo por vez via FOpen) |

## 9. Reference implementation

| Impl | Linguagem | License | Source |
|---|---|---|---|
| `COLETADB.tlpp` | TLPP (Protheus 12.1.2410+) | TBD (aguarda autor) | [`gaps/COLETADB.tlpp`](../gaps/COLETADB.tlpp) |

Outras implementações são bem-vindas — desde que conformes a este doc. Servidor pode estar em Python (FastAPI), Go (Gin), Node (Express) — só precisa respeitar os 2 endpoints + auth + chunk pattern.

## 10. Validação de conformidade

Servidor é considerado conforme se passa o conjunto de testes em [`cli/tests/integration/test_ingest_rest.py`](../cli/tests/integration/test_ingest_rest.py) usando-se como endpoint real:

```bash
COLETADB_REAL_ENDPOINT=http://protheus:8181/rest \
PROTHEUS_USER=admin PROTHEUS_PASS=*** \
pytest cli/tests/smoke/test_coletadb_real.py -v
```

## 11. Roadmap do contrato

- **v1.0** (atual) — bundle pattern + 2 endpoints + Basic auth
- **v1.1** (futuro) — TTL do bundle + endpoint `DELETE /coletadb/bundle/{id}` pra cleanup
- **v1.2** (futuro) — endpoint `GET /coletadb/bundle/{id}` pra listar manifests existentes (resume após queda)
- **v2.0** (longo prazo) — XXA/XAM/XAL no schema do plugin, MPMENU/JOBS/SCHEDULES como ingestores próprios
