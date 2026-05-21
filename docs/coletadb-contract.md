# COLETADB REST Contract — `plugadvpl ingest-protheus`

> Esta é a especificação **canônica e agnóstica** do contrato REST que o `plugadvpl ingest-protheus` consome. Qualquer servidor que responda esse contrato funciona — não há amarração com uma implementação específica. A implementação de referência (`COLETADB.tlpp`) vive em [`docs/reference-impl/`](reference-impl/) quando disponível, mas qualquer impl em qualquer linguagem servindo este contrato é suportada.

| Item | Valor |
|---|---|
| **Versão** | 1.0.0 (especulativa, validada na Fase 0 quando reference impl chegar) |
| **Status** | Draft |
| **Tipo de transporte** | HTTP/HTTPS REST + JSON |
| **Inspirado em** | Padrão CSV exportado do Configurador Protheus |
| **Spec MD** | [`docs/superpowers/specs/2026-05-21-u5-ingest-protheus.md`](superpowers/specs/2026-05-21-u5-ingest-protheus.md) |

## 1. Princípio

Servidor expõe **leitura** do dicionário Protheus em formato JSON estável. **Sem escrita.** **Sem execução ad-hoc.** Apenas dump estruturado das tabelas SX e equivalentes.

Qualquer implementação que respeite este contrato pode ser consumida pelo `plugadvpl ingest-protheus` — TLPP, Go, Python, Node, etc. A implementação de referência (`COLETADB.tlpp` em TLPP-modern) é apenas uma opção.

## 2. Endpoints

### 2.1 Base path

Cliente concatena o `endpoint` configurado em `runtime.toml` com os paths abaixo:

```
GET  {base}/health
GET  {base}/tables
GET  {base}/dump?tables={CSV}
GET  {base}/table/{nome}
```

Exemplo: se `endpoint = "https://protheus.cliente.com/rest/coletadb"`, então `GET https://protheus.cliente.com/rest/coletadb/health`.

### 2.2 `GET /health`

**Propósito**: probe de existência + descoberta de versão + lista de tabelas expostas.

**Request**:
```http
GET {base}/health
Authorization: Bearer <token>  # ou Basic, conforme config
```

**Response 200**:
```json
{
  "version": "1.0.0",
  "protheus_build": "7.00.240223P",
  "protheus_environment": "P2510",
  "exposed_tables": ["SX1", "SX2", "SX3", "SX5", "SX6", "SX7", "SX9", "SXA", "SXB", "SXG", "SIX"],
  "extras": []
}
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `version` | string | sim | Versão do servidor COLETADB (semver) |
| `protheus_build` | string | sim | Build do Protheus (do AppServer onde roda) |
| `protheus_environment` | string | sim | Environment ativo (P2510, P2520, etc.) |
| `exposed_tables` | string[] | sim | Tabelas SX expostas neste servidor |
| `extras` | string[] | não | Tabelas custom (`Z*`, `X*`) expostas, se houver |

### 2.3 `GET /tables`

**Propósito**: listar tabelas disponíveis com metadata (row count, last update).

**Request**:
```http
GET {base}/tables
Authorization: Bearer <token>
```

**Response 200**:
```json
{
  "tables": [
    {"name": "SX1", "row_count": 59498, "last_modified": "2026-05-20T15:30:00Z"},
    {"name": "SX2", "row_count": 234, "last_modified": "2026-05-15T10:00:00Z"},
    {"name": "SX3", "row_count": 187633, "last_modified": "2026-05-20T15:30:00Z"}
  ]
}
```

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `tables[].name` | string | sim | Nome da tabela (SX1, SX2, etc.) |
| `tables[].row_count` | integer | sim | Linhas atuais na tabela |
| `tables[].last_modified` | ISO-8601 string | não | Última modificação detectável (best-effort) |

### 2.4 `GET /dump?tables={CSV}`

**Propósito**: download bulk de uma ou mais tabelas em JSON.

**Request**:
```http
GET {base}/dump?tables=SX3,SX7
Authorization: Bearer <token>
```

**Query params**:

| Param | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `tables` | CSV string | sim | Lista de tabelas. Ex: `SX1` ou `SX1,SX3,SX7` |
| `offset` | integer | não | Offset para paginação. Default: 0 |
| `limit` | integer | não | Linhas por response. Default: server-defined |

**Response 200 (sem paginação)**:
```json
{
  "tables": {
    "SX3": {
      "row_count": 187633,
      "rows": [
        {
          "X3_ARQUIVO": "SA1",
          "X3_CAMPO": "A1_COD",
          "X3_TIPO": "C",
          "X3_TAMANHO": 6,
          "X3_DECIMAL": 0,
          "X3_TITULO": "Codigo",
          "X3_DESCRIC": "Codigo do Cliente"
        }
      ]
    },
    "SX7": {
      "row_count": 18051,
      "rows": [...]
    }
  }
}
```

**Response 200 (com paginação)**:
```json
{
  "tables": {
    "SX3": {
      "row_count": 187633,
      "offset": 0,
      "limit": 10000,
      "has_more": true,
      "next_offset": 10000,
      "rows": [...]
    }
  }
}
```

Cliente faz loop até `has_more=false`.

### 2.5 `GET /table/{nome}`

**Propósito**: download de uma tabela específica (atalho de `/dump?tables=X` quando só uma é necessária).

Comportamento idêntico ao `/dump` mas com response simplificado:

```json
{
  "table": "SX3",
  "row_count": 187633,
  "rows": [...]
}
```

## 3. Schema de campos por tabela

Os campos retornados em `rows[]` seguem **nomes físicos do Protheus** (`X1_*`, `X2_*`, `X3_*`, ...). O plugin mapeia internamente pro schema SQLite via `ingest_sx._insert_*`.

Tabelas suportadas no MVP:

| Tabela | Conteúdo | Schema |
|---|---|---|
| SX1 | Perguntas (parâmetros de tela) | `X1_GRUPO`, `X1_ORDEM`, `X1_PERGUNT`, ... |
| SX2 | Tabelas físicas | `X2_CHAVE`, `X2_NOME`, `X2_PATH`, ... |
| SX3 | Campos | `X3_ARQUIVO`, `X3_CAMPO`, `X3_TIPO`, `X3_TAMANHO`, ... |
| SX5 | Tabelas genéricas | `X5_TABELA`, `X5_CHAVE`, `X5_DESCRI`, ... |
| SX6 | Parâmetros `MV_*` | `X6_VAR`, `X6_CONTEUD`, `X6_DESCRIC`, ... |
| SX7 | Gatilhos | `X7_CAMPO`, `X7_SEQUENC`, `X7_CDOMIN`, `X7_REGRA`, ... |
| SX9 | Relacionamentos | `X9_DBF`, `X9_IDENT`, `X9_EXPDE`, `X9_EXPPARA`, ... |
| SXA | Pastas (folders) | `XA_ALIAS`, `XA_ORDEM`, `XA_DESCRIC`, ... |
| SXB | Consultas F3 | `XB_ALIAS`, `XB_TIPO`, `XB_DESCRIC`, ... |
| SXG | Grupos de campo | `XG_GRUPO`, `XG_DESCRI`, `XG_SIZE`, ... |
| SIX | Índices | `INDICE`, `ORDEM`, `CHAVE`, `DESCRICAO`, ... |

Schema detalhado dos campos: ver `cli/plugadvpl/parsing/sx_csv.py` (que já parseia o equivalente CSV).

## 4. Autenticação

Servidor **DEVE** suportar pelo menos um dos:

### 4.1 Bearer token

```http
Authorization: Bearer <token>
```

Token opaco, formato definido pelo servidor. Cliente trata como string opaca.

### 4.2 HTTP Basic

```http
Authorization: Basic base64(user:password)
```

Apenas pra cenários dev/qa. **NÃO** recomendado pra produção (token bearer é preferível).

### 4.3 Custom headers (opcional)

Servidores podem exigir headers adicionais:

```http
X-Tenant-Id: <tenant>
X-Build: <build>
```

Cliente lê esses headers da config `runtime.toml`:

```toml
[coletadb.headers]
"X-Tenant-Id" = "${TENANT_ID}"  # interpolado de env var
```

## 5. Códigos de erro

| Status | Significado | Body esperado |
|---|---|---|
| 200 | Sucesso | Conforme seção 2 |
| 400 | Request inválido (params errados, tabela inválida) | `{"error": "msg", "code": "BAD_REQUEST"}` |
| 401 | Auth ausente ou inválida | `{"error": "msg", "code": "UNAUTHORIZED"}` |
| 403 | Auth ok mas sem permissão pra recurso | `{"error": "msg", "code": "FORBIDDEN"}` |
| 404 | Endpoint não existe (COLETADB não instalado, ou tabela não suportada) | `{"error": "msg", "code": "NOT_FOUND"}` |
| 429 | Rate limit excedido | `{"error": "msg", "code": "RATE_LIMITED", "retry_after_s": 30}` |
| 5xx | Erro do servidor | `{"error": "msg", "code": "SERVER_ERROR"}` |

Cliente trata:
- **401/403**: para imediatamente, pede credencial nova
- **404**: oferece auto-install (Fase 4c) ou pede ao TI compilar
- **429**: respeita `retry_after_s` (ou 30s default)
- **5xx**: retry exponencial 3×, depois aborta

## 6. Tipos JSON

Servidor **DEVE** respeitar:

| Campo SX | Tipo JSON |
|---|---|
| Strings | `string` (UTF-8) |
| Numéricos | `integer` ou `number` |
| Datas | ISO-8601 string (`"2026-05-21"`) |
| Booleanos | `boolean` (true/false) |
| Bitmaps (X3_USADO, X3_OBRIGAT) | `string` (mantém formato bitmap original) |

**Encoding**: response JSON SEMPRE em UTF-8 (RFC 8259). Servidor é responsável por converter CP1252 → UTF-8 nas strings que pega do banco.

## 7. Performance e limites

| Item | Valor recomendado |
|---|---|
| Timeout default do cliente | 30s |
| Retry count | 3 com backoff exponencial (2s, 4s, 8s) |
| Paginação obrigatória se row_count > | 50_000 |
| Limit default por página | 10_000 |
| Max concurrent requests | 1 (sequencial) — servidor pode bloquear concorrentes |

## 8. Versionamento e compatibilidade

- `/health.version` segue **semver**
- Cliente avisa se major do servidor for diferente do esperado (potencial breaking change)
- Cliente é **backward-compatible** com servidores de minor/patch anterior
- Cliente **falha rápido** se major diverge — atualizar plugin ou servidor

## 9. O que NÃO está no contrato

- ❌ Escrita (`POST`/`PUT`/`DELETE` em tabelas SX)
- ❌ Queries SQL ad-hoc
- ❌ Triggers em tempo real (websocket, SSE)
- ❌ Compressão (gzip/zstd) — pode ser adicionado em v1.1
- ❌ Streaming (chunked transfer) — pode ser adicionado em v1.1

## 10. Implementações conhecidas

| Impl | Linguagem | Licença | Source |
|---|---|---|---|
| `COLETADB.tlpp` | TLPP | TBD (aguarda autor) | TBD |

Outras implementações são bem-vindas — desde que conformes a este doc.

## 11. Validação de conformidade

Servidor é considerado conforme se passa o conjunto de testes em [`cli/tests/integration/test_coletadb_contract.py`](../cli/tests/integration/test_coletadb_contract.py) usando-se como endpoint real.

Para validar localmente:

```bash
COLETADB_REAL_ENDPOINT=http://localhost:8181/rest/coletadb \
COLETADB_TOKEN=<token> \
pytest cli/tests/smoke/test_coletadb_real.py -v
```

## 12. Roadmap do contrato

- **v1.0** (atual) — read-only dump SX, auth bearer/basic, paginação
- **v1.1** (futuro) — compressão gzip, streaming chunked, `/dump?since={ts}` (delta)
- **v2.0** (longo prazo) — extras tables (`Z*`/`X*`), webhook de drift
