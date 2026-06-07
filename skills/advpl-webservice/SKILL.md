---
description: Use ao criar/editar API REST ou SOAP no Protheus, escolher entre WSRESTFUL (clássico) e @Get/@Post (notation tlppCore — ~3x mais rápido, suporta @Patch + Swagger), migrar de uma pra outra, configurar PrepareIn + TenantId, validar JWT/OAuth2, ou revisar SEC-001 (RpcSetEnv em REST). Inclui pegadinhas como ::SetResponse cumulativo, WSMETHOD sub-nome, requisitos de versão (notation precisa AppServer 20+).
---

# advpl-webservice — REST e SOAP no Protheus

ADVPL/TLPP suporta três famílias de Web Service:

| Família           | Sintaxe                                    | Quando usar                                    |
|-------------------|--------------------------------------------|------------------------------------------------|
| **REST clássico** | `WSRESTFUL` + `WSMETHOD GET/POST`           | Mantida pra compat; ainda OK em código existente |
| **REST tlppCore** | `@Get(endpoint=...)` em `User Function`     | **Padrão moderno para novas APIs** (TLPP/AppServer 20+) |
| **SOAP**          | `WSSERVICE` + `WSDATA` + `WSMETHOD`         | Legado; integração com sistema que exige WSDL  |

REST tlppCore **não é evolução do REST ADVPL** — é recurso novo, sem compat automática com autenticação user-based clássica nem pré-carga de banco. Cada cenário tem trade-offs.

O AppServer Protheus expõe ambos via porta HTTP configurada em `appserver.ini` (`[HTTPV11]` para REST 2.0).

### Por que TOTVS recomenda notation pra projetos novos

A TOTVS reescreveu a camada de accept REST em C++ no binário Lobo-Guará. O notation usa essa camada nova; o WSRESTFUL clássico continua na camada ADVPL antiga. Resultado documentado pela comunidade:

| Métrica | WSRESTFUL clássico | Notation (`@Get/@Post/...`) |
|---|---|---|
| **Throughput** | linha-base | **~3× mais rápido** ([Every System](https://everysys.com.br/blog/tl-rest/), [gworks](https://www.gworks.com.br/post/totvs-rest)) |
| **Verbos** | GET, POST, PUT, DELETE | **+ `@Patch`, `@Options`** (clássico não tem PATCH) |
| **Path params** | `::aURLParms[1]` posicional | `oRest:getPathParamsRequest()['id']` **nomeado** |
| **Múltiplos endpoints/arquivo** | precisa `WSMETHOD GET Main`/`Detalhe` sub-nome | basta colar outro `@Get(...)` em cima de outra função |
| **Swagger/OpenAPI** | ❌ não nativo | ✅ via **REST-DOC** (tlppCore 01.04.02+) |
| **Pré-requisito** | qualquer Protheus 12.x | binário com tlppCore ativo + **AppServer 20.x+** (Lobo-Guará) |

Repositório oficial [github.com/totvs/tlpp-sample-rest](https://github.com/totvs/tlpp-sample-rest) trata WSRESTFUL como API "legada" — diretório `server/migrate-FWrest-2-tlpp/` é literalmente o roteiro de migração.

## Quando usar

- Criar API REST/SOAP no Protheus.
- Edit em fontes com `WSRESTFUL`, `WSSERVICE`, `WSMETHOD`, `WSDATA`, `WSSTRUCT`, `@Get`, `@Post`.
- Integração de Protheus com aplicação externa (mobile, e-commerce, ERP terceiro).
- Revisão de segurança em endpoint exposto — `SEC-001` (impl: `RpcSetEnv` em REST).
- Consumir API externa do dentro do Protheus (`FwRest`, `HttpPost`).

## REST tlppCore (TLPP moderno, recomendado)

Estrutura **function-based** com annotations. Mais limpo, sem precisar de classe:

```advpl
#include "tlpp-core.th"
#include "tlpp-rest.th"

@Get(endpoint="/v1/cliente/:codigo", description="Busca cliente por codigo")
User Function GetCliente()
    Local oResp  := JsonObject():New()
    Local jPath  := oRest:GetPathParamsRequest()
    Local cCod   := If(jPath != Nil, jPath["codigo"], "")

    If Empty(cCod)
        oRest:SetStatusCode(400)
        oResp["error"] := "Codigo obrigatorio"
        oRest:SetResponse(oResp:ToJson())
        Return   // NUNCA `Return .F.` no notation: vira HTTP 500 e descarta o 400
    EndIf

    DbSelectArea("SA1")
    SA1->(DbSetOrder(1))
    If SA1->(DbSeek(xFilial("SA1") + cCod))
        oResp["codigo"] := SA1->A1_COD
        oResp["nome"]   := AllTrim(SA1->A1_NOME)
        oResp["cnpj"]   := SA1->A1_CGC
        oRest:SetStatusCode(200)
    Else
        oRest:SetStatusCode(404)
        oResp["error"] := "Cliente nao encontrado"
    EndIf

    oRest:SetResponse(oResp:ToJson())
Return .T.
```

### Path params nomeados (notation) vs posicionais (clássico)

```advpl
// NOTATION — nomeado, refactor-safe
@Get("/cliente/:cod/pedido/:num")
User Function GetPedidoCli()
    Local jPath := oRest:getPathParamsRequest()      // JSON nomeado
    Local cCod  := jPath['cod']                       // por NOME
    Local cNum  := jPath['num']
    // se você inverter pra /cliente/:num/pedido/:cod, código aqui NÃO quebra
Return

// CLÁSSICO — posicional, frágil em refactor
WSMETHOD GET WSSERVICE XYZPedido
    Local cCod := ::aURLParms[1]                      // por POSIÇÃO
    Local cNum := ::aURLParms[2]
    // se você inverter a URL, valores trocam silenciosamente — bug clássico
Return .T.
```

`oRest:getPathParamsRequest()` retorna **`Nil` se o endpoint não declara `:param`** — sempre testar `if jPath != Nil` antes de indexar.

### `@Patch` — exclusivo do notation

```advpl
@Patch("/cliente/:cod")
User Function PatchCliente()
    Local jBody := JsonObject():New()
    jBody:FromJson(oRest:getBodyRequest())
    // só atualiza os campos presentes no body (semântica PATCH RFC 5789)
    // PUT seria substituição completa; PATCH é parcial
Return
```

WSRESTFUL clássico **não suporta PATCH** — confirmado no README de [tlpp-sample-rest/migrate-FWrest-2-tlpp](https://github.com/totvs/tlpp-sample-rest/tree/master/server/migrate-FWrest-2-tlpp). Projetos que precisam de PATCH têm que migrar (ou faker via POST com `X-HTTP-Method-Override`, gambiarra que não recomendo).

## REST clássico (WSRESTFUL)

```advpl
WSRESTFUL XYZCli DESCRIPTION "API de Clientes"

    WSMETHOD GET   DESCRIPTION "Lista clientes"   WSSYNTAX "/api/cli"
    WSMETHOD GET   DESCRIPTION "Busca por codigo" WSSYNTAX "/api/cli/{codigo}"
    WSMETHOD POST  DESCRIPTION "Cria cliente"     WSSYNTAX "/api/cli"

END WSRESTFUL

WSMETHOD GET WSSERVICE XYZCli
    Local cBody := ""
    // ... logica
    ::SetContentType("application/json")
    ::SetResponse(cBody)
Return .T.

WSMETHOD POST WSSERVICE XYZCli
    Local cInput := DecodeUTF8(::GetContent())   // converte UTF-8 -> cp1252
    // ... validacao + logica
Return .T.
```

### `WSMETHOD <verb> <subnome>` — múltiplos paths por verbo

WSRESTFUL clássico só permite **1 WSMETHOD por verbo** por padrão. Pra ter `GET /sample` E `GET /sample/{id}` na mesma classe, use sub-nome:

```advpl
WSRESTFUL Sample
    WSMETHOD GET Main     DESCRIPTION "Lista"   PATH "/sample"
    WSMETHOD GET Detalhe  DESCRIPTION "Detalhe" PATH "/sample/{id}"
END WSRESTFUL

WSMETHOD GET Main    WSSERVICE Sample  // ... Return .T.
WSMETHOD GET Detalhe WSSERVICE Sample  // ... Return .T.
```

Esquecer o sub-nome (`WSMETHOD GET WSSERVICE Sample` sozinho repetido) **compila silenciosamente mas dá 404** — o segundo handler nunca registra. Pegadinha #2 do clássico, depois do `SetResponse` cumulativo.

### `SECURITY <rotina>` — controle de acesso via permissão da rotina

Exclusivo do clássico. Reaproveita o esquema de permissão do Configurador (SIGACFG):

```advpl
WSRESTFUL MATA030Api SECURITY MATA030      // só quem tem permissão na MATA030 acessa
    WSMETHOD GET DESCRIPTION "Lista clientes" PATH "/v1/cliente"
END WSRESTFUL
```

Quem chama precisa estar logado como user com permissão na rotina `MATA030`. No notation isso é **manual** — você lê `Authorization`, chama `MsLogin()`, e checa permissão você mesmo.

### Pegadinha #1 do clássico: `::SetResponse` é **cumulativo**

```advpl
// ❌ ERRADO — concatena, não substitui
::SetResponse('{"primeira":"chamada"}')
::SetResponse('{"segunda":"chamada"}')
// Cliente recebe: '{"primeira":"chamada"}{"segunda":"chamada"}'  ← JSON malformado!

// ✓ CERTO — acumula em variável, uma chamada única no fim
Local cResp := ""
cResp += '{"primeira":"valor"}'
// ... mais lógica
::SetResponse(cResp)
```

No notation `oRest:setResponse()` tem o **mesmo bug histórico** — convenção é igual: acumular local e chamar 1 vez. Cuidado especial em loops + paginação.

## SOAP com WSSERVICE

```advpl
WSSERVICE XYZSrv DESCRIPTION "Servico XYZ"
    WSDATA cCodCliente AS STRING
    WSDATA oCliente    AS XYZCliRet

    WSMETHOD BuscaCliente DESCRIPTION "Busca cliente por codigo"
END WSSERVICE

WSSTRUCT XYZCliRet
    WSDATA cCodigo AS STRING
    WSDATA cNome   AS STRING
    WSDATA nLimite AS NUMERIC
END WSSTRUCT

WSMETHOD BuscaCliente WSRECEIVE cCodCliente WSSEND oCliente WSSERVICE XYZSrv
    ::oCliente := WSClassNew("XYZCliRet")
    ::oCliente:cCodigo := cCodCliente
    ::oCliente:cNome   := "Cliente Teste"
    ::oCliente:nLimite := 5000
Return .T.
```

## Multi-tenancy: `PrepareIn` + `TenantId`

Para REST suportar múltiplas empresas/filiais sem `RpcSetEnv`:

**1.** No `appserver.ini`, declare `PrepareIn` por sócket REST:

```ini
[HTTPV11]
ENABLE=1
PORT=8080

[HTTPURI]
URL=/rest
PrepareIn=99,01     ; carrega ambiente Empresa 99 Filial 01 pra cada request
Instances=1,5       ; min,max threads (cada thread já vem com env carregado)
CORSEnable=1
Security=1          ; obriga autenticacao (sempre ative em producao!)
```

**2.** Cliente passa empresa/filial no header `TenantId`:

```http
POST /rest/v1/pedido HTTP/1.1
Host: protheus.cliente.com:8080
Authorization: Bearer eyJhbGciOi...
TenantId: 99,01            ; empresa,filial
Content-Type: application/json
```

**3.** No endpoint, `cEmpAnt` / `cFilAnt` já estão preenchidos:

```advpl
@Post(endpoint="/v1/pedido")
User Function CriaPedido()
    // cEmpAnt e cFilAnt JA vem do PrepareIn + TenantId — sem RpcSetEnv
    ConOut("Pedido criado em " + cEmpAnt + "/" + cFilAnt)
    // ...
Return .T.
```

## Quando escolher cada abordagem

| Cenário | Escolha | Por quê |
|---|---|---|
| API nova, build moderno (AppServer 20+) | **Notation** | Performance, sintaxe, Swagger, suporte continuado |
| Build antigo de 2020 sem tlppCore ativo | Clássico | Notation **não retroporta** — `@Get` vira comentário em build velho, endpoint nunca sobe |
| Precisa de `@Patch` | **Notation** | Clássico não suporta |
| Precisa de Swagger/OpenAPI nativo | **Notation** | REST-DOC só na notation |
| Endpoint sobre cadastro padrão SX (CRUD MVC) | **Clássico** | `FWAdapterBaseV2` gera CRUD inteiro a partir do dicionário |
| Precisa de `SECURITY <rotina>` (controle via menu) | **Clássico** | Notation exige validação manual |
| Performance crítica (alto throughput) | **Notation** | ~3× speedup (C++ accept layer) |
| Múltiplos endpoints/path por arquivo | **Notation** | Sem precisar `WSMETHOD GET Main`/`Detalhe` sub-nome |
| Equipe só sabe ADVPL puro (sem TL++) | Clássico | Curva mais conhecida |

## Migration path WSRESTFUL → Notation (10 passos)

1. **Trocar includes**: `totvs.ch` + `restful.ch` → `tlpp-core.th` + `tlpp-rest.th`
2. **Remover bloco** `WSRESTFUL ... END WSRESTFUL` inteiro
3. **Cada `WSMETHOD VERB ... WSSERVICE x`** vira **`User Function`** isolada com `@Verb(endpoint)` em cima
4. **`WSDATA id` + `::id`** → `oRest:getQueryRequest()['id']`
5. **`::aURLParms[1]`** → declarar `:id` no endpoint e usar `oRest:getPathParamsRequest()['id']`
6. **`::GetContent()`** → `oRest:getBodyRequest()`
7. **`::SetResponse(c)`** (cumulativo) → **acumular em variável local** e fazer **uma chamada única** `oRest:setResponse(cAcumulado)` no fim
8. **`SetRestFault(404, msg)`** → `oRest:setStatusCode(404)` + `oRest:setFault(msg)`
9. **Tirar `Return .F.`** — em notation, `Return .F.` é lido como falha e **vira HTTP 500**, descartando o `setStatusCode`. Use sempre `Return` (ou `Return .T.`); o status vem do `oRest:setStatusCode`. _(pegadinha #2 da referência)_
10. **Re-testar `tenantId`** — mesmo comportamento, mas convém validar

Referência oficial: [TDN - Migração WsRESTful para REST tlppCore](https://tdn.totvs.com/pages/viewpage.action?pageId=553337101).

## Requisitos mínimos de versão

| Feature | Mínimo |
|---|---|
| WSRESTFUL clássico | Qualquer Protheus 12.x com FWREST presente |
| Notation `@Get/@Post/...` | Binário **com tlppCore ativo** (TL++ habilitado) + **AppServer ~20.x** (Lobo-Guará) |
| `@Patch` | tlppCore 01.04+ |
| REST-DOC (Swagger automático) | **tlppCore 01.04.02** + **AppServer 20.3.1.10** |
| `TLPP COMPONENT` (componentes Swagger reutilizáveis) | tlppCore 01.04.02+ |

Em build sem tlppCore, `@Get` compila como **comentário silencioso** — fonte sobe sem erro, endpoint nunca registra, debugar quebra a cabeça. Sempre checar via `/api/swagger` (se REST-DOC ativo) ou `/rest` (lista nativa) se o endpoint aparece.

> ⚠️ **Gotcha de build 7.00.240223P+ — annotation só com `User Function`**
>
> `@Get`/`@Post` decorando **`Static Function`** ou **`Method` de classe** registra
> o endpoint mas o injetor de `oRest` falha — `oRest` chega `Nil` no corpo, primeira
> chamada a `oRest:GetBodyRequest()` (ou qualquer método) retorna **HTTP 500 sem
> stack trace** na resposta e sem nada útil no `console.log`. Só funciona com
> **`User Function`**.
>
> ```tlpp
> // QUEBRA — 500 silencioso
> @Post(endpoint="/x")
> Static Function StaticEndpoint()
>     Local cBody := oRest:GetBodyRequest()   // oRest é Nil aqui
> Return .T.
>
> // QUEBRA — 404 (annotation não registra em Method de classe)
> Class Foo
>     @Post(endpoint="/y")
>     Method Bar() Class Foo
> EndClass
>
> // FUNCIONA — pattern oficial pra build 7.00.240223P+
> @Post(endpoint="/z")
> User Function PostEndpoint()
>     Local cBody := oRest:GetBodyRequest()
> Return .T.
> ```
>
> Workaround quando precisar de `Static Function` (encapsulamento, namespace): expor
> uma `User Function` thin wrapper decorada com a annotation e delegar pra Static.
> Ou refatorar pra WSRESTFUL clássico que aceita `WSMETHOD` sem essa restrição.

## Autenticação JWT (Bearer Token)

REST 2.0 do Protheus tem endpoint built-in pra issuance de token:

```http
POST /api/oauth2/v1/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

grant_type=password&username=admin&password=totvs
```

Retorno:

```json
{
  "access_token": "eyJhbGciOi...",
  "expires_in": 3600,
  "token_type": "bearer",
  "refresh_token": "..."
}
```

Cliente usa em todas as requests subsequentes:

```http
GET /rest/v1/cliente/000001
Authorization: Bearer eyJhbGciOi...
```

Configurar JWT em `appserver.ini`:

```ini
[HTTPURI]
Security=1
JWTSecret=meu-segredo-super-longo-do-cliente
```

## REST-DOC — Swagger/OpenAPI automático (exclusivo notation)

A partir de **tlppCore 01.04.02 + AppServer 20.3.1.10**, anotações alimentam um gerador OpenAPI 3.0.3 nativo. Sintaxe:

```advpl
#include "tlpp-core.th"
#include "tlpp-rest.th"
#include "tlpp-doc.th"

// Componente reutilizável (vai pra `components.schemas` do OpenAPI)
TLPP COMPONENT Pessoa
    TLPP COMPONENT nome     character "José da Silva"
    TLPP COMPONENT idade    numeric   42
    TLPP COMPONENT ativo    logical   .T.
TLPP COMPONENT END

@Get(endpoint="/v1/pessoa/:id", description="[GetPessoaDoc]")
User Function GetPessoa()
    Local jPath := oRest:getPathParamsRequest()
    // ... lógica
Return

// Função que devolve o JSON OpenAPI dessa operação
Function GetPessoaDoc()
    Local jDoc := JsonObject():New()
    jDoc['summary']     := 'Busca pessoa por id'
    jDoc['parameters']  := {{'name' => 'id', 'in' => 'path', 'required' => .T.}}
    jDoc['responses']   := {'200' => {'$ref' => '#/components/schemas/Pessoa'}}
Return jDoc:ToJson()
```

Acessar:
- `GET /api/swagger` → JSON OpenAPI completo (cole em [editor.swagger.io](https://editor.swagger.io) pra ver o Swagger UI)
- Suporta i18n via `Localize()` no fonte + `translate:` na annotation

Sem REST-DOC, a documentação fica em README à parte (deriva fácil). Com, vira **source of truth** sincronizada com o código.

## Regra crítica: NUNCA `RpcSetEnv` em REST (`SEC-001` impl)

`RpcSetEnv` é usado para abrir ambiente Protheus em **JOB/RPC** (veja `[[advpl-jobs-rpc]]`). **Em REST, o framework já entrega o ambiente** via `PrepareIn` + `TenantId`.

```advpl
// ERRADO — SEC-001 critical (impl real: RpcSetEnv em WSRESTFUL)
@Post(endpoint="/v1/pedido")
User Function CriaPedido()
    RpcSetEnv("01", "0101", "admin", "totvs")   // BLOQUEAR! Lint SEC-001 dispara
    // ...
Return .T.

// CORRETO — ambiente ja vem da requisicao autenticada via TenantId
@Post(endpoint="/v1/pedido")
User Function CriaPedido()
    Local cEmp := cEmpAnt     // ja preenchido pelo PrepareIn
    Local cFil := cFilAnt
    // ... logica
Return .T.
```

Razão: `RpcSetEnv` hardcoded vaza credenciais, bypassa o login do usuário REST, e mata auditoria — não há rastro de quem realmente fez a operação.

## Validação de input (boa prática + `SEC-002` catalog)

> **Nota:** `SEC-002` na **implementação atual** detecta "User Function sem prefixo" (não validação de input). A regra "GetContent sem validação" está **catalogada mas não detectada**. De qualquer forma, validar input é mandatório.

```advpl
@Post(endpoint="/v1/cliente")
User Function CriaCli()
    Local cBody := DecodeUTF8(oRest:GetBodyRequest())   // converte UTF-8 -> cp1252
    Local oReq  := JsonObject():New()
    Local cErr  := oReq:FromJson(cBody)

    If !Empty(cErr)
        oRest:SetStatusCode(400)
        oRest:SetResponse('{"error":"JSON invalido: ' + cErr + '"}')
        Return            // .F. aqui viraria HTTP 500 (ver migration passo 9)
    EndIf

    // Valida campos obrigatorios + tipos
    If Empty(oReq["codigo"]) .Or. ValType(oReq["codigo"]) != "C"
        oRest:SetStatusCode(422)
        oRest:SetResponse('{"error":"campo codigo obrigatorio"}')
        Return            // .F. aqui viraria HTTP 500 (ver migration passo 9)
    EndIf

    // Valida tamanho/range usando o proprio SX3 como verdade
    If Len(AllTrim(oReq["codigo"])) > TamSX3("A1_COD")[1]
        oRest:SetStatusCode(422)
        oRest:SetResponse('{"error":"codigo excede tamanho do SX3"}')
        Return            // .F. aqui viraria HTTP 500 (ver migration passo 9)
    EndIf

    // ... agora usa oReq["codigo"] com seguranca
    // CUIDADO: ao usar em SQL, sempre %exp:cVar% — veja [[advpl-embedded-sql]]
Return .T.
```

## Content-Type e CORS

```advpl
oRest:SetKeyHeaderResponse("Content-Type", "application/json; charset=utf-8")
oRest:SetKeyHeaderResponse("Access-Control-Allow-Origin",  "*")          // ajuste conforme politica
oRest:SetKeyHeaderResponse("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
oRest:SetKeyHeaderResponse("Access-Control-Allow-Headers", "Content-Type,Authorization,TenantId")
```

> ⚠️ **Gotcha de build**: em AppServer 7.00.240223P (e similares pós-2024), `oRest:SetHeaderResponse(k,v)` retorna erro críptico "expected J->C" sem stack trace e devolve HTTP 500 sem corpo. Use **`SetKeyHeaderResponse`** (com `Key` no meio) que funciona em builds novas e antigas. Vale para o método global `::SetHeaderResponse` também (WSRESTFUL clássico → `::SetKeyHeaderResponse`).

Endpoints com upload binário usam `application/octet-stream`. JSON é o default.

> CORS é declarado uma vez no `appserver.ini` (`CORSEnable=1`, `AllowOrigin=*`) e propagado automaticamente. Override no method só se precisar de policy específica.

> 🔴 **Gotcha que mais custa tempo na integração com SPA/PO UI:** com **CORS desligado** no `.ini`, o REST do Protheus **nega com 401 qualquer request que tenha o header `Origin`** — que **todo navegador manda** —, mesmo com Basic/Bearer válido. Sintoma clássico: o `curl` (sem `Origin`) dá 200/201, mas o navegador dá 401. **Diagnóstico:** repita o `curl` com `-H "Origin: http://x"` e veja o 401 reproduzir. **Fix dev:** o proxy do `ng serve` remove o `Origin` (`proxyReq.removeHeader('origin')`). **Fix prod:** `CORSEnable=1` + `AllowOrigin` controlado. _(Detalhe na referência, pegadinha #19.)_

## Retorno de erro padronizado

Convenção: sempre devolva JSON com `error` + `code`:

```json
{
  "error": "Cliente nao encontrado",
  "code": "CLI_NOT_FOUND",
  "details": {"codigo": "999999"}
}
```

Mapeie status HTTP:

| Status | Quando                                                |
|--------|-------------------------------------------------------|
| 200    | OK                                                    |
| 201    | Criado (POST com sucesso)                             |
| 204    | OK sem body (DELETE)                                  |
| 400    | Body malformado (JSON invalido)                       |
| 401    | Não autenticado                                       |
| 403    | Autenticado mas sem permissão                         |
| 404    | Recurso não encontrado                                |
| 409    | Conflito (registro já existe)                         |
| 422    | Validação de negócio falhou                           |
| 500    | Erro interno (logge stack, NUNCA exponha em resposta) |

## Encoding em REST — `EncodeUTF8`/`DecodeUTF8`

REST é UTF-8 nativo; fontes ADVPL clássicos (`.prw`) são cp1252. Conversão é mandatória nos boundaries:

```advpl
// Lendo body REST (entra UTF-8, fonte é cp1252)
Local cBody := DecodeUTF8(oRest:GetBodyRequest())

// Escrevendo response (saída UTF-8, fonte é cp1252)
oRest:SetResponse(EncodeUTF8('{"nome":"' + AllTrim(SA1->A1_NOME) + '"}'))
```

Sem isso, acentos viram `Ã§`/`Ã£` no consumidor. Veja `[[advpl-encoding]]`.

## Anti-padrões

**Comuns aos dois (cláusico e notation):**
- **`RpcSetEnv` em REST** → `SEC-001` crítico (impl real). Use `PrepareIn` + `TenantId`.
- **`GetContent()`/`getBodyRequest()` direto em SQL** sem validação ou bind (`%exp:`) → SQL injection (catálogo `SEC-001` legacy).
- **Devolver stack trace na response** (`Errorblock` que vaza interno) → expõe estrutura.
- **Endpoint sem `Begin Sequence`/`Recover`** em operações críticas → 500 sem log estruturado.
- **Hardcode de credenciais no fonte** (basic auth, token, conn string) → SEC-004 (catálogo).
- **Log de body cru com PII** em `ConOut` → SEC-003 (catálogo).
- **Falta de `setStatusCode`** → cliente recebe 200 com erro no body (confunde monitoring).
- **Esquecer `EncodeUTF8`/`DecodeUTF8`** nos boundaries cp1252 ↔ UTF-8 → acentos quebram.
- **`PrepareIn` em produção apontando empresa de teste** → request multi-tenant cai no ambiente errado.
- **`Security=0` em produção** → endpoint público sem auth.
- **CORS `*` em endpoint que escreve** sem validação de origin → CSRF.

**Específicos do clássico:**
- **`::SetResponse` chamado 2× no mesmo handler** → concatena em vez de substituir → JSON malformado. Acumule em variável local + 1 chamada no fim.
- **`WSMETHOD GET` repetido sem `Main`/`Detalhe` sub-nome** → 2º handler nunca registra (404 silencioso).
- **`WSDATA` sem `WSRECEIVE` no WSMETHOD** → `::var` sempre `Nil`.
- **Esquecer `DEFAULT ::var := ""`** em param OPTIONAL → concat com `Nil` quebra.

**Específicos do notation:**
- **Endpoint duplicado em fontes diferentes** → colisão silenciosa, último compilado ganha. Padronize prefixos por módulo.
- **`@Get` em build sem tlppCore** → vira comentário, endpoint nunca sobe. Checar `/api/swagger` ou `/rest`.
- **Decorator NÃO imediatamente acima da função** (comentário entre) → invalida o decorator.
- **`oRest:getPathParamsRequest()` quando endpoint não tem `:param`** → retorna `Nil`, indexação quebra. Sempre `if jPath != Nil`.
- **Chamar `User Function` decorada via `U_FUNC` no SmartClient** → `oRest` não existe nesse contexto, crasha com "variable does not exist".

## Referência rápida

| Funcionalidade           | Notation (`oRest`)                                  | Clássico (`::Self`)                          |
|--------------------------|------------------------------------------------------|----------------------------------------------|
| GET                      | `@Get("/path")`                                      | `WSMETHOD GET`                               |
| POST                     | `@Post("/path")`                                     | `WSMETHOD POST`                              |
| PUT                      | `@Put("/path")`                                      | `WSMETHOD PUT`                               |
| **PATCH** (parcial)      | `@Patch("/path")`                                    | ❌ não suportado                              |
| DELETE                   | `@Delete("/path")`                                   | `WSMETHOD DELETE`                            |
| OPTIONS (CORS preflight) | `@Options("/path")`                                  | `WSMETHOD OPTIONS`                           |
| Path param **nomeado**   | `oRest:getPathParamsRequest()['id']`                 | `::aURLParms[1]` (posicional)                |
| Query string             | `oRest:getQueryRequest()['campo']`                   | `::aQueryString` + `WSRECEIVE id` + `::id`   |
| Body                     | `oRest:getBodyRequest()`                             | `::GetContent()`                             |
| Header read              | `oRest:getHeaderRequest("Auth")`                     | iterar `::aHeadStr`                          |
| Header write             | `oRest:setKeyHeaderResponse("X-Foo","bar")` ⚠️       | `::SetKeyHeaderResponse("X-Foo","bar")` ⚠️   |
| Status                   | `oRest:setStatusCode(404)`                           | `::SetStatus(404)`                           |
| Response body            | `oRest:setResponse(c)` *(cuidado: cumulativo!)*      | `::SetResponse(c)` *(cuidado: cumulativo!)*  |
| Erro/fault               | `oRest:setFault(cMsg)` + `setStatusCode`             | `SetRestFault(404, cMsg)` *(função global)*  |
| Content-Type             | `oRest:setKeyHeaderResponse("Content-Type","application/json")` | `::SetContentType("application/json")`       |
| User logado              | `GetUserName()` (global) ou var `cUserName`/`__cUserID` | `::GetUserName()`                            |
| JSON parse               | `JsonObject():New()` + `oJ:FromJson(cBody)`          | idem                                         |
| JSON build               | `oJ["chave"] := val` + `oJ:ToJson()`                 | idem                                         |
| Doc Swagger              | `description="[funcDoc]"` + `TLPP COMPONENT`         | ❌ não nativo                                 |

## Cross-references com outras skills

- `[[advpl-tlpp]]` — namespace e classes pra REST tlppCore.
- `[[advpl-encoding]]` — `EncodeUTF8`/`DecodeUTF8` obrigatórios em REST cp1252.
- `[[advpl-code-review]]` — `SEC-001` (RpcSetEnv em REST), `SEC-002`/`SEC-003`/`SEC-004` (catalog).
- `[[advpl-embedded-sql]]` — SQL injection prevention; nunca concat input REST em query.
- `[[advpl-jobs-rpc]]` — `RpcSetEnv` correto pra jobs (vs REST).
- `[[advpl-fundamentals]]` — `User Function` sem prefixo cliente em endpoint (exceção justificada se padrão WSRESTFUL).
- `[[advpl-mvc]]` — `FWMVCRotAuto` chamado de dentro de REST (PE pattern).
- `[[advpl-dicionario-sx]]` — `TamSX3()` pra validar tamanho de input via SX3.
- `[[advpl-debugging]]` — REST 500 / response vazio / encoding bagunçado.
- `[[plugadvpl-index-usage]]` — tabela `rest_endpoints` lista todos WSRESTFUL/WSMETHOD do projeto.

## Comandos plugadvpl relacionados

- `/plugadvpl:find function <WS>` — localiza WSRESTFUL/WSSERVICE.
- `/plugadvpl:grep "WSRESTFUL\|@Get\|@Post"` — encontra endpoints novos.
- `/plugadvpl:grep "RpcSetEnv"` — auditoria SEC-001 (não deve aparecer dentro de REST).
- Tabela `rest_endpoints` (não "ws_services") do índice cataloga endpoints.
- Tabela `http_calls` cataloga consumo de APIs externas (`FwRest`, `HttpPost`).
- `/plugadvpl:lint <arq>` — verifica SEC-001 (RpcSetEnv em REST) impl real.

## Referência profunda

Dois arquivos ao lado, focos diferentes:

- **[`reference-rest.md`](reference-rest.md)** — REST moderno (notation + clássico):
  - CRUD completo em ambas as abordagens (Cliente como exemplo end-to-end).
  - `oRest:*` catálogo completo (path/query/body/header/status/response).
  - JWT/OAuth2 fluxo + endpoint `/api/oauth2/v1/token` + validação custom.
  - REST-DOC / Swagger / OpenAPI 3.0.3 + `TLPP COMPONENT` reutilizáveis.
  - `FWAdapterBaseV2` (CRUD MVC sobre tabelas SX com pouco código).
  - Multi-tenancy detalhado (PrepareIn + tenantId + RPCSetEnv auto).
  - Endpoints aninhados (`/cliente/:cod/pedido/:num`).
  - Paginação, upload/download binário, streaming.
  - CORS detalhado, content negotiation.
  - Consumo de APIs externas (`FwRest`, `HttpPost`, OAuth2 client-side).
  - 20+ pegadinhas testadas.

- **[`reference.md`](reference.md)** — SOAP/WSDL/UDDI (~1.5k linhas):
  - Anatomia completa de `WSSERVICE`/`WSDATA`/`WSSTRUCT` SOAP.
  - WSDL, TWsdlManager pra consumir SOAP externo.
  - Configuração HTTP/WEBEX legada.
  - Histórico/contexto pré-REST.

## Sources

- [Migração WsRESTful para REST tlppCore - TDN](https://tdn.totvs.com/pages/viewpage.action?pageId=553337101) (oficial)
- [GitHub totvs/tlpp-sample-rest](https://github.com/totvs/tlpp-sample-rest) (oficial — exemplos CRUD + migrate)
- [GitHub totvs/tlpp-sample-rest-documentation](https://github.com/totvs/tlpp-sample-rest-documentation/wiki) (oficial — REST-DOC/Swagger)
- [Entendendo as novidades do REST - TDN](https://tdn.totvs.com/display/public/framework/Entendendo+as+novidades+do+REST)
- [TL++ REST - Every System](https://everysys.com.br/blog/tl-rest/) (benchmark ~3× speedup)
- [TOTVS REST - gworks](https://www.gworks.com.br/post/totvs-rest)
- [Diferença REST clássico vs Annotation - Terminal de Informação](https://terminaldeinformacao.com/2023/07/12/qual-diferenca-do-rest-classico-com-o-annotation/)
- [Action GET REST ADVPL vs TLPP - Universo do Desenvolvedor](https://udesenv.com.br/post/advpl-action-get-rest-advpl-vs-action-get-rest-tlpp)
- [Como Definir Empresa e Filial em REST - Terminal de Informação](https://terminaldeinformacao.com/2025/08/25/como-definir-empresa-e-filial-numa-requisicao-em-rest/)
- [Requisição para Token JWT REST - TOTVS Central](https://centraldeatendimento.totvs.com/hc/pt-br/articles/360044883213)
- [REST com segurança - TOTVS Central](https://centraldeatendimento.totvs.com/hc/pt-br/articles/8919254403735)
- [PrepareIn / TenantId - TOTVS Central](https://centraldeatendimento.totvs.com/hc/pt-br/articles/4410465974167)
- [Maratona AdvPL TL++ 535 - WSRESTFUL](https://terminaldeinformacao.com/2024/07/13/criando-um-webservice-rest-com-wsrestful-maratona-advpl-e-tl-535/)
- [Consumindo APIs externas REST - Terminal de Informação](https://terminaldeinformacao.com/2025/06/28/consumindo-apis-externas-em-rest-com-e-sem-token-no-protheus-via-advpl-tlpp-ti-especial-0005/)
