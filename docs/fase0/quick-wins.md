# Fase 0 — Quick Wins (Runtime/Encoding/Webservice)

**Status:** spec aprovado · **Release alvo:** v0.7.0 · **Estimativa:** ~10h (~1.5 dias)

Fase introdutória do roadmap de runtime ADVPL. Sete itens autocontidos sem dependência externa (sem Docker, sem TDS-LS, sem RPO). Pavimenta o terreno para Fases 1+ (compile/exec/deploy).

## Princípios

1. **Sem IP TOTVS** — nada de listing/snippet copiado de fonte oficial. Padrões reproduzidos por descrição funcional.
2. **Opt-in** — regras novas seguem o pipeline atual de lint single-file/cross-file. Comando `edit-prw` é manual.
3. **Sem assumir runtime** — nada chama TDS-LS, REST do Protheus ou hot-swap. Tudo lê arquivo + DB local.
4. **Saída estruturada** — segue padrão atual (`render()` human + `--format json`).
5. **Pasta de cliente nunca citada** — fixtures inline ou sintéticas.

## Pesquisa prévia

Consolidado em ~600 palavras de research (TDN TOTVS, terminaldeinformacao.com, blogs, GitHub):

- **WSMETHOD** aceita `WSSERVICE`/`WSRESTFUL`/`WSREST` como aliases. Subname (`cId`) opcional, mas se ausente e existirem 2 métodos do mesmo verbo no mesmo serviço, último vence — bug silencioso.
- **DecodeUtf8/EncodeUtf8** são canônicos quando body/response JSON contém acentos. `FwJsonDeserialize` está **descontinuada** pela TOTVS — usar `JsonObject:FromJson()` direto.
- **xFilial()** retorna `""` para tabelas exclusivas (`x2_modo='E'`) quando `cFilAnt` não foi setado. Job/REST iniciado sem `RpcSetEnv`/`PREPARE ENVIRONMENT` cai nesse caso. `MsSeek(xFilial("SA1") + ...)` localiza o primeiro registro de qualquer filial — crítico.
- **CP1252 vs UTF-8** em `.prw`: compilador appserver legado lê byte-a-byte como CP1252. `.tlpp` é UTF-8 nativo. `chardet` (já dep) cobre detecção; estratégia BOM → UTF-8 strict → CP1252 fallback é robusta.
- **U_EXEC** não tem nome canônico TOTVS — folclore comunitário. Implementações reais usam WSRESTFUL específico por função (boa prática de segurança). Reference impl MIT do plugin deve ser explícito como dev-only.

## Auditoria interna (estado atual v0.6.1)

- **lint.py** tem 31 regras single+cross. `_check_<id>()` por regra. Catalog em `lookups/lint_rules.json`.
- **WSMETHOD já parseado** em `parsing/parser.py` com `_WSMETHOD_RE` (extrai verbo + nome). Vai pra `fonte_chunks.tipo_simbolo='wsmethod'`.
- **chardet já é dep** — `parser.py` usa para auto-detect no ingest.
- **xFilial / x2_modo já cobertos parcialmente** em `SX-008` (cross-file: tabela compartilhada usa xFilial em X3_VALID). Falta caso oposto (exclusiva em REST/JOB sem cFilAnt).
- **Não existe** comando `edit-prw` nem ENC-001 nem WS-001..003 nem XF-001 nem U_EXEC reference.

## Itens

### 1. WS-001 — WSMETHOD sem WSSERVICE

**Tipo:** lint single-file regex · **Severidade:** `error` (sem service) / `warning` (colisão)

**Detecta:**
1. `WSMETHOD <verb> <nome>` sem `WSSERVICE|WSRESTFUL|WSREST <ServiceName>` na mesma declaração (compila mas não registra rota — método órfão).
2. Dois `WSMETHOD <verb>` (mesmo verbo) sem `cId` distinto no mesmo `WSRESTFUL` (last-wins silencioso).

**Saída:**
```
[WS-001/error] foo.prw:42 WSMETHOD GET listar sem WSSERVICE — método não será registrado
[WS-001/warning] foo.prw:48 WSMETHOD POST sem subname colide com linha 42 (mesmo verbo, mesmo serviço)
```

**Implementação:**
- Função `_check_ws001_wsmethod_orphan(arquivo, parsed, content)` em `lint.py`.
- Regex já existe parcialmente (`_WSMETHOD_RE`); criar variantes:
  - `_WS001_WSMETHOD_NO_SERVICE_RE` — captura WSMETHOD sem trailing WSSERVICE/WSRESTFUL/WSREST.
  - Detecção de colisão: agrupar por (classe_pai, verbo, subname) e flag duplicados.
- Sem dependência cross-file (basta ler o próprio source).

**Teste TDD (red→green):**
- Fixture com 3 cenários: WSMETHOD com WSSERVICE (clean), sem WSSERVICE (error), duas POST sem subname (warning).

---

### 2. WS-002 — WSRESTFUL recebe JSON sem DecodeUtf8

**Tipo:** lint single-file regex · **Severidade:** `warning` (falso-positivo possível se cliente sempre manda header correto)

**Detecta:**
- Dentro de classe `WSRESTFUL`, padrão `<var> := ::GetContent()` (ou `self:GetContent()`) seguido em ≤10 linhas de `<var>:FromJson(...)` **sem** `DecodeUtf8(<var>)` interposto.

**Por que importa:** quando cliente não envia header `Content-Type: application/json; charset=utf-8`, body chega CP1252 cru. `oJson:FromJson` armazena bytes UTF-8 (0xC3 0xBA = "ú") como string CP1252 — corrompe gravação SXX downstream.

**Saída:**
```
[WS-002/warning] foo.prw:67 GetContent + FromJson sem DecodeUtf8 — payload UTF-8 cru pode corromper acentos
```

**Implementação:**
- `_check_ws002_getcontent_no_decode(arquivo, parsed, content)`.
- Regex: encontrar todos `GetContent()` assignment, buscar lookahead 10 linhas por `FromJson`, verificar ausência de `DecodeUtf8`.
- Anti-recomendação no `fix_guidance`: NÃO sugerir `FwJsonDeserialize` (descontinuado pela TOTVS).

---

### 3. WS-003 — WSRESTFUL retorno sem EncodeUtf8

**Tipo:** lint single-file regex · **Severidade:** `warning`

**Detecta:**
- Dentro de classe `WSRESTFUL`, chamadas `::SetResponse(<expr>)` (ou `self:SetResponse`) onde `<expr>` **não** contém `EncodeUtf8` envolvendo.

**Saída:**
```
[WS-003/warning] foo.prw:88 SetResponse sem EncodeUtf8 — clients UTF-8 verão mojibake em acentos
```

**Fix guidance:** `::SetResponse( EncodeUtf8( FwJsonSerialize(oResp, .F., .F., .T.) ) )` — padrão idiomático.

**Implementação:**
- `_check_ws003_setresponse_no_encode(arquivo, parsed, content)`.
- Regex captura `SetResponse(...)`, verifica presença/ausência de `EncodeUtf8` no argumento.
- Escopo restrito: só dispara dentro de bloco `CLASS ... FROM WSRESTFUL ... ENDCLASS` (reusa `_WSRESTFUL_CLASS_RE` + `_END_CLASS_RE` existentes).

---

### 4. XF-001 — xFilial em x2_modo='E' sem cFilAnt em REST/JOB

**Tipo:** lint **cross-file** (precisa SX2) · **Severidade:** `error` em REST/JOB, `warning` fora

**Detecta:**
- Padrão `MsSeek(xFilial("<TAB>") + ...)` ou `DbSeek(xFilial("<TAB>") + ...)` onde:
  - `<TAB>` existe em SX2 com `x2_modo='E'` (exclusiva).
  - Função pai é `WSMETHOD` (REST) ou registrada como job — heurística: arquivo contém `WSRESTFUL` OU referenciado em `StartJob`/`THREAD WAIT`.
  - Sem `RpcSetEnv(` ou `PREPARE ENVIRONMENT` precedente no mesmo escopo.

**Saída:**
```
[XF-001/error] foo.prw:33 MsSeek(xFilial("SA1")) em REST sem RpcSetEnv — xFilial retorna "" (SA1 é x2_modo=E)
```

**Implementação:**
- `_check_xf001_xfilial_exclusiva_rest(conn)` em `lint.py` (cross-file orchestrator).
- Query SX2 por modo='E'. Para cada fonte, parsear xFilial(...) com tabela em SX2/E e checar contexto.
- Reusa parsing de `_RPCSETENV_RE` e `_WSRESTFUL_CLASS_RE`.

**Teste TDD:**
- Fixture SX2 com SA1 exclusiva + SE1 compartilhada + fixture .prw com WSRESTFUL chamando ambas — só SA1 dispara.

---

### 5. ENC-001 — .prw com bytes UTF-8 não-ASCII

**Tipo:** lint single-file (no ingest) · **Severidade:** `error`

**Detecta:**
- Arquivo com extensão `.prw` (não `.tlpp`), sem BOM UTF-8 (`EF BB BF`), contém ao menos uma sequência UTF-8 válida multi-byte:
  - `[\xC2-\xDF][\x80-\xBF]` (2-byte: á, ç, etc.)
  - `[\xE0-\xEF][\x80-\xBF]{2}` (3-byte)
- Verifica que a sequência **decodifica** como UTF-8 strict (descarta falsos-positivos onde 2 bytes CP1252 coincidem com padrão UTF-8 mas não formam char válido).

**Saída:**
```
[ENC-001/error] foo.prw .prw com bytes UTF-8 — compilador appserver legado quebra acentos. Use `plugadvpl edit-prw save foo.prw` para converter.
```

**Implementação:**
- `_check_enc001_prw_utf8_bytes(arquivo, raw_bytes)` em `lint.py`.
- Roda no ingest sobre os bytes crus (antes do decode). Precisa de novo hook: passar raw bytes ao lint, não só string decodificada.
- Ignora `.tlpp`, `.tlpp.ch`, `.ch` (somente `.prw`/`.prx`).

---

### 6. Comando `edit-prw` (open/save/check)

**Tipo:** novo subcomando CLI · **Severidade:** N/A (utilitário)

**Sub-comandos:**
- `plugadvpl edit-prw check <file>` — reporta encoding detectado e divergências com extensão. Exit 0 = ok, 1 = mismatch.
- `plugadvpl edit-prw open <file>` — imprime conteúdo em UTF-8 puro (para editar com qualquer editor moderno).
- `plugadvpl edit-prw save <file> [--from utf-8] [--to cp1252]` — converte e grava. Default infere `--from` por `chardet`, `--to` pela extensão (`.prw`→cp1252, `.tlpp`→utf-8).

**Saída JSON (`check`):**
```json
{
  "file": "foo.prw",
  "extension": ".prw",
  "expected_encoding": "cp1252",
  "detected_encoding": "utf-8",
  "has_bom": false,
  "match": false,
  "non_ascii_bytes": 17,
  "sample_lines": [{"line": 42, "preview": "u00e1lerta", "issue": "utf-8 sequence in .prw"}]
}
```

**Implementação:**
- Novo módulo `cli/plugadvpl/edit_prw.py` com 3 funções: `check_encoding`, `read_as_utf8`, `convert_and_save`.
- Subcomando em `cli.py` registra subparser `edit-prw` com subsubparser `check|open|save`.
- Usa `chardet` (já dep). Estratégia: BOM → strict UTF-8 decode (se tem bytes ≥ 0x80) → fallback CP1252.

**Segurança:** `save` cria backup `<file>.bak` antes de gravar (a menos que `--no-backup`).

---

### 7. Contract doc G2 + reference uexec.prw MIT

**Tipo:** docs + reference implementation · **Sem código no plugin Python**

**Entregáveis:**
- `docs/exec-contract.md` (~300 palavras) — define contrato `POST /rest/uexec`:
  - Body: `{"function": "<name>", "args": [<json values>]}`
  - Response: `{"ok": true|false, "function": "<name>", "result": <json>, "type": "<advpl_type>", "error": "<msg>"}`
  - Disclaimer **forte**: anti-pattern em produção, só DEV/CI.
- `docs/examples/uexec.prw` (~150 linhas) — reference impl ADVPL MIT-licensed:
  - WSRESTFUL `U_EXEC` que recebe JSON, valida que `function` começa com `U_`, chama via `ExecBlock`, devolve.
  - Header MIT explícito no topo.
- Header `LICENSE: MIT` + sem referência a cliente algum.

**Testes:** smoke test que apenas valida que docs/exec-contract.md e docs/examples/uexec.prw existem e header MIT está presente (não roda ADVPL).

---

## Ordem de implementação (TDD red→green, commit atômico por item)

1. WS-001 (parser regex já existe, escopo curto) — `~45min`
2. WS-002 (regex new, escopo médio) — `~45min`
3. WS-003 (regex new, escopo médio) — `~45min`
4. ENC-001 (precisa hook de raw bytes no ingest) — `~1h`
5. Comando `edit-prw` (módulo novo + 3 subcomandos + testes) — `~2h`
6. XF-001 (cross-file, depende SX2) — `~2h`
7. Contract doc G2 + uexec.prw reference — `~1h30`
8. Release v0.7.0: CHANGELOG + plugin.json + marketplace.json + ROADMAP + commit + tag — `~30min`

**Total estimado:** ~9h. Margem: ~1h para imprevistos.

## Out of scope (fica para Fases 1+)

- Compilar / deploy / hot-swap RPO.
- Wrapper TDS-LS.
- Cliente HTTP que chama `/rest/uexec` (será Fase 2).
- Hooks Claude Code que rodam lint pré-write.
- Sub-agent orquestrador.

## Critérios de aceitação

- Todas as 5 novas regras de lint (WS-001/002/003, XF-001, ENC-001) com entrada em `lookups/lint_rules.json` + função `_check_*` + testes unitários (positivo + negativo).
- Comando `edit-prw` com 3 subcomandos funcionando + testes integration.
- `docs/exec-contract.md` e `docs/examples/uexec.prw` no repo com header MIT.
- 100% dos testes existentes continuam passando (565 atuais).
- `plugadvpl lint` no corpus interno detecta zero falso-positivo gritante (sample manual em 5 arquivos).
- CHANGELOG, plugin.json (0.6.1→0.7.0), marketplace.json e ROADMAP sincronizados.
