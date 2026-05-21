# Reference Implementations

Implementações de referência dos contratos REST consumidos pelo `plugadvpl`. Cada arquivo aqui é **uma** das possíveis implementações conformantes — não a única. Quem quiser servir o mesmo contrato em outra linguagem (Go, Python, Node) é bem-vindo.

| Arquivo | Contrato consumido por | License | Linguagem |
|---|---|---|---|
| [`coletadb.tlpp`](coletadb.tlpp) | `plugadvpl ingest-protheus` ([contract](../coletadb-contract.md)) | MIT | TLPP (Protheus 12.1.2410+) |

## `coletadb.tlpp`

Servidor REST que dumpa o dicionário SX do Protheus em **bundle pattern**: gera CSVs locais no `\temp\<timestamp>_<uuid>\` e expõe download em chunks de 4MB.

### Instalação

1. Copiar `coletadb.tlpp` pro RPO custom do AppServer
2. Compilar via TDS-VSCode ou `plugadvpl compile coletadb.tlpp`
3. Configurar `[HTTPV11]` + `[HTTPURI]` no `appserver.ini`:
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
4. Restart do AppServer

### Uso (via plugin)

```bash
plugadvpl ingest-protheus \
  --endpoint http://protheus:8181/rest \
  --user admin --password "$PASS"
```

### Entry points

- **UI**: User Function `U_COLETADB` — dialog SmartClient interativo (geração local sem REST)
- **REST**: `WSRESTFUL COLETADBAPI` com endpoints:
  - `POST /coletadb/run` — dispara coleta + retorna manifest JSON
  - `POST /coletadb/file` — baixa arquivo em chunks

### O que extrai

- **SX padrão**: SX1/SX2/SX3/SX5/SX6/SX7/SX9/SXA/SXB/SXG + SIX (11 tabelas)
- **SX adicional**: XXA/XAM/XAL (3 tabelas — não cobertas pelo MVP do plugadvpl)
- **MPMENU**: 6 tabelas (menus completos)
- **SCHEDULES**: agendamentos do scheduler interno
- **JOBS**: parse recursivo de `appserver*.ini`
- **RECORD_COUNTS**: inventário de rows físicas por tabela (via DBMS query)

MVP do plugadvpl consome só os 11 SX padrão. Os demais ficam pra Fase 4.

### Encoding

CSVs gerados em **CP1252** (encoding canonical Protheus). JSON envelope das responses em **UTF-8** (`DecodeUtf8`/`EncodeUtf8` no fonte). Source code em **ASCII puro** (sem acentos pra portabilidade entre encodings).

### License

MIT — ver bloco no topo do arquivo `coletadb.tlpp`. Reproduzido também em [`LICENSE`](../../LICENSE) da raiz do repo (que cobre o plugadvpl inteiro).

### Compatibilidade

Protheus 12.1.2410+ (uso de `@Post` annotation requer tlppCore moderno).
