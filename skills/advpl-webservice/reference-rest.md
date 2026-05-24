# reference-rest.md — REST no Protheus (notation + clássico)

Referência profunda complementar à [`SKILL.md`](SKILL.md). Foca 100% em REST moderno: CRUD ponta-a-ponta, REST-DOC/Swagger, JWT/OAuth2, FWAdapterBaseV2, paginação, upload binário, consumo de APIs externas.

Para SOAP/WSDL/UDDI, ver [`reference.md`](reference.md) (legado).

## Sumário

1. [CRUD completo em notation (`@Get/@Post/@Put/@Patch/@Delete`)](#1-crud-completo-em-notation)
2. [CRUD completo em clássico (`WSRESTFUL`/`WSMETHOD`)](#2-crud-completo-em-cl%C3%A1ssico)
3. [Catálogo `oRest:*` (notation)](#3-cat%C3%A1logo-orest-notation)
4. [Catálogo `::Self` (clássico)](#4-cat%C3%A1logo-self-cl%C3%A1ssico)
5. [Multi-tenancy: PrepareIn + tenantId](#5-multi-tenancy-preparein--tenantid)
6. [Autenticação: Basic, Bearer/JWT, OAuth2](#6-autentica%C3%A7%C3%A3o-basic-bearerjwt-oauth2)
7. [REST-DOC / Swagger / OpenAPI 3.0.3](#7-rest-doc--swagger--openapi-303)
8. [FWAdapterBaseV2 — CRUD MVC sobre tabelas SX](#8-fwadapterbasev2--crud-mvc-sobre-tabelas-sx)
9. [Endpoints aninhados + paginação + filtros](#9-endpoints-aninhados--pagina%C3%A7%C3%A3o--filtros)
10. [Upload/download binário + streaming](#10-uploaddownload-bin%C3%A1rio--streaming)
11. [CORS, content negotiation, headers](#11-cors-content-negotiation-headers)
12. [Encoding boundary cp1252 ↔ UTF-8](#12-encoding-boundary-cp1252--utf-8)
13. [Consumo de APIs externas (`FwRest`, `HttpPost`, OAuth2 client)](#13-consumo-de-apis-externas)
14. [Pegadinhas testadas (20+)](#14-pegadinhas-testadas)

---

## 1. CRUD completo em notation

Entidade exemplo: **Cliente** (`SA1`). Endpoint base `/v1/cliente`.

```advpl
#include "tlpp-core.th"
#include "tlpp-rest.th"

// ─── LIST ────────────────────────────────────────────────────────────────
@Get("/v1/cliente")
User Function ListCliente()
    Local jQry   := oRest:getQueryRequest()
    Local nLim   := IIf(jQry != Nil .And. jQry['limit']  != Nil, Val(jQry['limit']),  20)
    Local nOff   := IIf(jQry != Nil .And. jQry['offset'] != Nil, Val(jQry['offset']),  0)
    Local cFiltro := IIf(jQry != Nil .And. jQry['nome'] != Nil, AllTrim(jQry['nome']), '')
    Local jResp  := JsonObject():New()
    Local aItens := {}
    Local nCount := 0

    BeginSql Alias 'TRB'
        SELECT A1_COD, A1_LOJA, A1_NOME, A1_CGC, A1_EST
          FROM %table:SA1% SA1
         WHERE SA1.A1_FILIAL = %xfilial:SA1%
           AND SA1.D_E_L_E_T_ = ' '
           AND (%exp:cFiltro% = '' OR UPPER(SA1.A1_NOME) LIKE UPPER('%' || %exp:cFiltro% || '%'))
         ORDER BY A1_COD, A1_LOJA
    EndSql
    DbSelectArea('TRB')
    While !TRB->(EoF()) .And. nCount < nOff + nLim
        If nCount >= nOff
            AAdd(aItens, ;
                {'codigo' => AllTrim(TRB->A1_COD), ;
                 'loja'   => AllTrim(TRB->A1_LOJA), ;
                 'nome'   => AllTrim(DecodeUtf8(TRB->A1_NOME)), ;
                 'cnpj'   => AllTrim(TRB->A1_CGC), ;
                 'uf'     => TRB->A1_EST})
        EndIf
        nCount++
        TRB->(DbSkip())
    EndDo
    TRB->(DbCloseArea())

    jResp['itens']  := aItens
    jResp['count']  := Len(aItens)
    jResp['offset'] := nOff
    jResp['limit']  := nLim
    oRest:setContentType('application/json; charset=utf-8')
    oRest:setStatusCode(200)
    oRest:setResponse(EncodeUtf8(jResp:ToJson()))
Return

// ─── READ por id ─────────────────────────────────────────────────────────
@Get("/v1/cliente/:cod/:loja")
User Function GetCliente()
    Local jPath := oRest:getPathParamsRequest()
    Local cCod  := jPath['cod']
    Local cLoja := jPath['loja']
    Local jResp := JsonObject():New()

    DbSelectArea('SA1')
    SA1->(DbSetOrder(1))   // A1_FILIAL + A1_COD + A1_LOJA
    If !SA1->(DbSeek(xFilial('SA1') + cCod + cLoja))
        oRest:setStatusCode(404)
        jResp['error']   := 'Cliente nao encontrado'
        jResp['code']    := 'CLI_NOT_FOUND'
        jResp['details'] := {'codigo' => cCod, 'loja' => cLoja}
        oRest:setResponse(jResp:ToJson())
        Return
    EndIf
    jResp['codigo']  := AllTrim(SA1->A1_COD)
    jResp['loja']    := AllTrim(SA1->A1_LOJA)
    jResp['nome']    := AllTrim(DecodeUtf8(SA1->A1_NOME))
    jResp['cnpj']    := AllTrim(SA1->A1_CGC)
    jResp['limite']  := SA1->A1_LC
    oRest:setStatusCode(200)
    oRest:setContentType('application/json; charset=utf-8')
    oRest:setResponse(EncodeUtf8(jResp:ToJson()))
Return

// ─── CREATE ──────────────────────────────────────────────────────────────
@Post("/v1/cliente")
User Function CreateCliente()
    Local cBody  := DecodeUtf8(oRest:getBodyRequest())
    Local jReq   := JsonObject():New()
    Local cErr   := jReq:FromJson(cBody)
    Local jResp  := JsonObject():New()

    If !Empty(cErr)
        oRest:setStatusCode(400)
        jResp['error'] := 'JSON invalido: ' + cErr
        oRest:setResponse(jResp:ToJson())
        Return
    EndIf
    // Validação SX3-driven (delega tamanho/tipo pro dicionário)
    If Empty(jReq['codigo']) .Or. Len(AllTrim(jReq['codigo'])) > TamSX3('A1_COD')[1]
        oRest:setStatusCode(422)
        jResp['error'] := 'campo codigo invalido (verifique SX3)'
        oRest:setResponse(jResp:ToJson())
        Return
    EndIf

    DbSelectArea('SA1')
    SA1->(DbSetOrder(1))
    If SA1->(DbSeek(xFilial('SA1') + jReq['codigo'] + jReq['loja']))
        oRest:setStatusCode(409)
        jResp['error'] := 'Cliente ja existe'
        jResp['code']  := 'CLI_EXISTS'
        oRest:setResponse(jResp:ToJson())
        Return
    EndIf

    RecLock('SA1', .T.)
    SA1->A1_FILIAL := xFilial('SA1')
    SA1->A1_COD    := jReq['codigo']
    SA1->A1_LOJA   := jReq['loja']
    SA1->A1_NOME   := jReq['nome']
    SA1->A1_CGC    := jReq['cnpj']
    SA1->(MsUnLock())

    jResp['codigo'] := AllTrim(SA1->A1_COD)
    jResp['loja']   := AllTrim(SA1->A1_LOJA)
    oRest:setStatusCode(201)
    oRest:setHeaderResponse('Location', '/v1/cliente/' + AllTrim(SA1->A1_COD) + '/' + AllTrim(SA1->A1_LOJA))
    oRest:setResponse(EncodeUtf8(jResp:ToJson()))
Return

// ─── UPDATE (PUT — substituição completa) ────────────────────────────────
@Put("/v1/cliente/:cod/:loja")
User Function PutCliente()
    // PUT exige body com TODOS os campos relevantes — semântica de substituição
    Local jPath := oRest:getPathParamsRequest()
    Local cBody := DecodeUtf8(oRest:getBodyRequest())
    Local jReq  := JsonObject():New()
    jReq:FromJson(cBody)
    DbSelectArea('SA1')
    SA1->(DbSetOrder(1))
    If !SA1->(DbSeek(xFilial('SA1') + jPath['cod'] + jPath['loja']))
        oRest:setStatusCode(404)
        oRest:setResponse('{"error":"nao encontrado"}')
        Return
    EndIf
    RecLock('SA1', .F.)
    SA1->A1_NOME := jReq['nome']
    SA1->A1_CGC  := jReq['cnpj']
    SA1->A1_LC   := jReq['limite']
    // ... TODOS os campos editáveis. Se cliente omite, vira default.
    SA1->(MsUnLock())
    oRest:setStatusCode(200)
    oRest:setResponse('{"ok":true}')
Return

// ─── PATCH (atualização parcial — EXCLUSIVO NOTATION) ────────────────────
@Patch("/v1/cliente/:cod/:loja")
User Function PatchCliente()
    Local jPath := oRest:getPathParamsRequest()
    Local cBody := DecodeUtf8(oRest:getBodyRequest())
    Local jReq  := JsonObject():New()
    jReq:FromJson(cBody)
    DbSelectArea('SA1')
    SA1->(DbSetOrder(1))
    If !SA1->(DbSeek(xFilial('SA1') + jPath['cod'] + jPath['loja']))
        oRest:setStatusCode(404)
        oRest:setResponse('{"error":"nao encontrado"}')
        Return
    EndIf
    RecLock('SA1', .F.)
    // Só atualiza campos PRESENTES no body — semântica PATCH (RFC 5789)
    If jReq:HasProperty('nome')   ; SA1->A1_NOME := jReq['nome']     ; EndIf
    If jReq:HasProperty('cnpj')   ; SA1->A1_CGC  := jReq['cnpj']     ; EndIf
    If jReq:HasProperty('limite') ; SA1->A1_LC   := jReq['limite']   ; EndIf
    SA1->(MsUnLock())
    oRest:setStatusCode(200)
    oRest:setResponse('{"ok":true,"patched":true}')
Return

// ─── DELETE (lógico — convenção Protheus) ────────────────────────────────
@Delete("/v1/cliente/:cod/:loja")
User Function DeleteCliente()
    Local jPath := oRest:getPathParamsRequest()
    DbSelectArea('SA1')
    SA1->(DbSetOrder(1))
    If !SA1->(DbSeek(xFilial('SA1') + jPath['cod'] + jPath['loja']))
        oRest:setStatusCode(404)
        Return
    EndIf
    RecLock('SA1', .F.)
    SA1->(DbDelete())   // marca D_E_L_E_T_ = '*' (lógico)
    SA1->(MsUnLock())
    oRest:setStatusCode(204)   // No Content
Return

// ─── OPTIONS (CORS preflight) ────────────────────────────────────────────
@Options("/v1/cliente")
User Function OptionsCliente()
    oRest:setHeaderResponse('Access-Control-Allow-Origin',  '*')
    oRest:setHeaderResponse('Access-Control-Allow-Methods', 'GET,POST,PUT,PATCH,DELETE,OPTIONS')
    oRest:setHeaderResponse('Access-Control-Allow-Headers', 'Content-Type,Authorization,tenantId')
    oRest:setStatusCode(204)
Return
```

## 2. CRUD completo em clássico

Mesma entidade (Cliente SA1), abordagem WSRESTFUL. Note repetição de boilerplate.

```advpl
#INCLUDE 'totvs.ch'
#INCLUDE 'restful.ch'

WSRESTFUL ClienteApi DESCRIPTION "CRUD de Clientes" FORMAT "application/json"

    WSDATA cod    AS CHARACTER OPTIONAL
    WSDATA loja   AS CHARACTER OPTIONAL
    WSDATA nome   AS STRING    OPTIONAL
    WSDATA limit  AS NUMERIC   OPTIONAL
    WSDATA offset AS NUMERIC   OPTIONAL

    WSMETHOD GET    List    DESCRIPTION "Lista clientes"     PATH "/v1/cliente"             WSSYNTAX "/v1/cliente?nome=&limit=&offset="
    WSMETHOD GET    GetOne  DESCRIPTION "Busca por cod+loja" PATH "/v1/cliente/{cod}/{loja}"
    WSMETHOD POST   Create  DESCRIPTION "Cria cliente"       PATH "/v1/cliente"
    WSMETHOD PUT    Update  DESCRIPTION "Substitui cliente"  PATH "/v1/cliente/{cod}/{loja}"
    WSMETHOD DELETE Remove  DESCRIPTION "Remove cliente"     PATH "/v1/cliente/{cod}/{loja}"
    // NOTA: sem WSMETHOD PATCH — clássico não suporta

END WSRESTFUL

WSMETHOD GET List WSRECEIVE nome, limit, offset WSSERVICE ClienteApi
    Local cResp  := ""    // ACUMULA local — SetResponse é cumulativo!
    Local jResp  := JsonObject():New()
    // ... mesma query do exemplo notation
    ::SetContentType('application/json; charset=utf-8')
    ::SetStatus(200)
    cResp := EncodeUtf8(jResp:ToJson())
    ::SetResponse(cResp)
Return .T.

WSMETHOD GET GetOne WSSERVICE ClienteApi
    Local cCod  := ::aURLParms[1]   // POSICIONAL — frágil!
    Local cLoja := ::aURLParms[2]
    // ... mesma lógica do exemplo notation
Return .T.

WSMETHOD POST Create WSSERVICE ClienteApi
    Local cBody := DecodeUtf8(::GetContent())
    Local jReq  := JsonObject():New()
    jReq:FromJson(cBody)
    // ... validação + RecLock + insert
    ::SetStatus(201)
    ::SetKeyHeaderResponse('Location', '/v1/cliente/' + jReq['codigo'] + '/' + jReq['loja'])
    ::SetResponse('{"ok":true}')
Return .T.

WSMETHOD DELETE Remove WSSERVICE ClienteApi
    If Len(::aURLParms) < 2
        SetRestFault(400, "cod e loja obrigatorios na URL")
        Return .F.
    EndIf
    // ... DbSeek + DbDelete
    ::SetStatus(204)
Return .T.
```

Comparando: ~50% mais boilerplate, sem PATCH, path params posicionais, e `SetResponse` cumulativo é o erro #1 (acumular em variável local + 1 call no fim resolve).

## 3. Catálogo `oRest:*` (notation)

| Método | Tipo retorno | Uso |
|---|---|---|
| `oRest:getBodyRequest()` | `Character` | Body bruto (cp1252; passar por `DecodeUtf8` se cliente mandou UTF-8) |
| `oRest:getPathParamsRequest()` | `JsonObject` ou `Nil` | `:param` da URL. Sempre `if jPath != Nil` antes de indexar |
| `oRest:getQueryRequest()` | `JsonObject` ou `Nil` | Query string `?a=1&b=2` |
| `oRest:getHeaderRequest(c)` | `Character` | Valor do header (ex: `'Authorization'`, `'tenantId'`) |
| `oRest:getUserName()` | `Character` | Usuário Protheus autenticado |
| `oRest:setResponse(c)` | — | **Cumulativo.** Acumule local + 1 chamada no fim |
| `oRest:setStatusCode(n)` | — | 200/201/204/400/401/403/404/409/422/500 |
| `oRest:setFault(c)` | — | Mensagem de erro (junto com `setStatusCode`) |
| `oRest:setContentType(c)` | — | `'application/json; charset=utf-8'` padrão |
| `oRest:setKeyHeaderResponse(cK, cV)` | — | Header custom (CORS, Location, X-*). **Não confundir com `setHeaderResponse` (sem `Key`) que quebra em build 7.00.240223P+** |
| `oRest:setKeepAlive(.T.)` | — | Stream/Server-Sent Events |

## 4. Catálogo `::Self` (clássico)

| Membro | Tipo | Uso |
|---|---|---|
| `::GetContent()` | `Character` | Body bruto |
| `::aURLParms` | `Array` | Path params **posicionais** (`::aURLParms[1]`) |
| `::aQueryString` | `Array of {nome,valor}` | Query string |
| `::aHeadStr` | `Array of header lines` | Iterar para achar header específico |
| `::GetUserName()` | `Character` | Usuário Protheus |
| `::SetResponse(c)` | — | **Cumulativo** (igual ao notation) |
| `::SetStatus(n)` | — | Status HTTP |
| `::SetContentType(c)` | — | Content-Type |
| `::SetKeyHeaderResponse(cK, cV)` | — | Header custom. **Não confundir com `SetHeaderResponse` (sem `Key`) que quebra em build 7.00.240223P+** |
| `SetRestFault(n, c)` | função global! | Erro HTTP. Note: NÃO é método do Self |

## 5. Multi-tenancy: PrepareIn + tenantId

### appserver.ini

```ini
[HTTPV11]
ENABLE=1
PORT=8080

[HTTPURI]
URL=/rest
PrepareIn=99,01      ; carrega ambiente Empresa 99 Filial 01 (default) pra cada thread
Instances=2,10        ; min,max threads (cada thread vem com env carregado)
CORSEnable=1
Security=1            ; obriga autenticação (NUNCA desligue em produção)
```

`PrepareIn` pode aceitar várias combinações:
- `PrepareIn=ALL` → qualquer empresa via `tenantId`
- `PrepareIn=99,01;99,02;01,01` → 3 ambientes pré-carregados específicos

### Header tenantId no client

```http
POST /rest/v1/pedido HTTP/1.1
Host: protheus.cliente.com:8080
Authorization: Bearer eyJhbGciOi...
tenantId: 99,02              ← empresa,filial
Content-Type: application/json
```

### Acesso no endpoint

```advpl
@Post("/v1/pedido")
User Function CriaPedido()
    // cEmpAnt e cFilAnt JÁ vêm preenchidos pelo PrepareIn + tenantId
    // SEM RpcSetEnv (que seria SEC-001 crítico em REST)
    ConOut('Pedido criado em ' + cEmpAnt + '/' + cFilAnt)
Return
```

Se o cliente não mandar `tenantId`, AppServer usa o primeiro do `PrepareIn`.

Pra **forçar** empresa por URL (em vez de header), crie múltiplos `[HTTPURI]` no .ini:

```ini
[HTTPURI/99-01]
URL=/rest/empresa99
PrepareIn=99,01

[HTTPURI/01-01]
URL=/rest/empresa01
PrepareIn=01,01
```

## 6. Autenticação: Basic, Bearer/JWT, OAuth2

### Basic Auth (default Protheus)

```http
Authorization: Basic YWRtaW46dG90dnM=     ; base64("admin:totvs")
```

Validado contra usuários do Configurador (SIGACFG). Configuração `Security=1` no `[HTTPURI]` do .ini.

No clássico, `SECURITY MATA030` declara que só user com permissão em MATA030 acessa:

```advpl
WSRESTFUL ClienteApi SECURITY MATA030
    WSMETHOD GET List PATH "/v1/cliente"
END WSRESTFUL
```

No notation isso é manual:

```advpl
@Get("/v1/cliente")
User Function ListCli()
    If !UserHasAccess(oRest:getUserName(), 'MATA030', 1)
        oRest:setStatusCode(403)
        oRest:setResponse('{"error":"sem permissao"}')
        Return
    EndIf
Return
```

### Bearer JWT

Protheus tem endpoint built-in pra issuance:

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

Configurar JWT secret em `appserver.ini`:

```ini
[HTTPURI]
Security=1
JWTSecret=meu-segredo-MUITO-longo-do-cliente
```

Validar JWT custom no endpoint:

```advpl
@Get("/v1/protegido")
User Function ProtegidoGet()
    Local cAuth   := oRest:getHeaderRequest('Authorization')
    Local cToken  := ""
    Local jClaims := Nil

    If Empty(cAuth) .Or. !'Bearer ' $ cAuth
        oRest:setStatusCode(401)
        oRest:setResponse('{"error":"Authorization Bearer obrigatorio"}')
        Return
    EndIf
    cToken  := SubStr(cAuth, 8)
    jClaims := JwtToken():New('meu-secret'):Validate(cToken)   // built-in
    If jClaims == Nil
        oRest:setStatusCode(401)
        oRest:setResponse('{"error":"token invalido ou expirado"}')
        Return
    EndIf
    // jClaims contém: sub, exp, iat, iss, custom claims
    ConOut('User: ' + jClaims['sub'])
Return
```

### OAuth2 client credentials (pra integração machine-to-machine)

```http
POST /api/oauth2/v1/token HTTP/1.1
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&client_id=app123&client_secret=...
```

## 7. REST-DOC / Swagger / OpenAPI 3.0.3

**Requer tlppCore 01.04.02 + AppServer 20.3.1.10.**

### Componentes reutilizáveis

```advpl
#include "tlpp-core.th"
#include "tlpp-doc.th"

TLPP COMPONENT Cliente
    TLPP COMPONENT codigo  character "000001"
    TLPP COMPONENT loja    character "01"
    TLPP COMPONENT nome    character "Cliente Exemplo Ltda"
    TLPP COMPONENT cnpj    character "12345678000190"
    TLPP COMPONENT limite  numeric   50000.00
TLPP COMPONENT END

TLPP COMPONENT ErroPadrao
    TLPP COMPONENT error    character "Mensagem do erro"
    TLPP COMPONENT code     character "CLI_NOT_FOUND"
    TLPP COMPONENT details  object
TLPP COMPONENT END
```

### Annotation com referência a função de doc

```advpl
@Get(endpoint="/v1/cliente/:cod/:loja", description="[GetClienteDoc]")
User Function GetCliente()
    // ... implementação
Return

Function GetClienteDoc()
    Local jDoc := JsonObject():New()
    jDoc['summary']      := 'Busca cliente por código + loja'
    jDoc['description']  := 'Retorna cliente único. 404 se não existe.'
    jDoc['tags']         := {'Clientes'}
    jDoc['parameters']   := { ;
        {'name' => 'cod',  'in' => 'path', 'required' => .T., 'schema' => {'type' => 'string'}}, ;
        {'name' => 'loja', 'in' => 'path', 'required' => .T., 'schema' => {'type' => 'string'}} ;
    }
    jDoc['responses']    := JsonObject():New()
    jDoc['responses']['200'] := {'description' => 'OK', 'content' => {'application/json' => {'schema' => {'$ref' => '#/components/schemas/Cliente'}}}}
    jDoc['responses']['404'] := {'description' => 'Não encontrado', 'content' => {'application/json' => {'schema' => {'$ref' => '#/components/schemas/ErroPadrao'}}}}
Return jDoc:ToJson()
```

### Acessar

- `GET /api/swagger` → JSON OpenAPI 3.0.3 completo
- Cole em [editor.swagger.io](https://editor.swagger.io) ou expose Swagger UI ao lado
- Suporta i18n: usar `Localize()` no fonte + `translate:` na annotation

## 8. FWAdapterBaseV2 — CRUD MVC sobre tabelas SX

**Cenário onde o clássico ainda ganha.** Quando o backend é um cadastro MVC já existente (SX2/SX3 documentando a tabela), `FWAdapterBaseV2` gera CRUD inteiro com ~30 linhas:

```advpl
#INCLUDE 'totvs.ch'
#INCLUDE 'restful.ch'

WSRESTFUL SA1MVC DESCRIPTION "CRUD SA1 via FWAdapter" FORMAT "application/json"
    WSMETHOD GET    List   PATH "/v1/sa1"
    WSMETHOD GET    GetOne PATH "/v1/sa1/{key}"
    WSMETHOD POST   Create PATH "/v1/sa1"
    WSMETHOD PUT    Update PATH "/v1/sa1/{key}"
    WSMETHOD DELETE Remove PATH "/v1/sa1/{key}"
END WSRESTFUL

WSMETHOD GET List WSSERVICE SA1MVC
    Local oAdapter := FWAdapterBaseV2():New('SA1010', 'SA1')
    oAdapter:SetRestMethod('GET')
    oAdapter:Execute()
    ::SetResponse(oAdapter:GetJsonResponse())
Return .T.

WSMETHOD POST Create WSSERVICE SA1MVC
    Local oAdapter := FWAdapterBaseV2():New('SA1010', 'SA1')
    oAdapter:SetRestMethod('POST')
    oAdapter:SetBody(::GetContent())   // delega validação SX3, RecLock, MVC hooks
    oAdapter:Execute()
    ::SetResponse(oAdapter:GetJsonResponse())
Return .T.
```

Validação SX3, hooks MVC (`Pre/Post Validate`, `Pre/Post Commit`), conversão de tipos — tudo gratuito. No notation você refaria isso à mão.

## 9. Endpoints aninhados + paginação + filtros

### Multi-level path

```advpl
@Get("/v1/cliente/:cod/:loja/pedido/:num")
User Function GetPedidoCli()
    Local jPath := oRest:getPathParamsRequest()
    // jPath['cod'], jPath['loja'], jPath['num']
Return

@Get("/v1/cliente/:cod/:loja/pedido/:num/item/:seq")
User Function GetItemPedido()
    Local jPath := oRest:getPathParamsRequest()
    // jPath tem 4 chaves
Return
```

### Paginação cursor-based (recomendada > offset pra tabelas grandes)

```advpl
@Get("/v1/cliente")
User Function ListClienteCursor()
    Local jQry    := oRest:getQueryRequest()
    Local cCursor := IIf(jQry != Nil .And. jQry['cursor'] != Nil, jQry['cursor'], '')
    Local nLim    := IIf(jQry != Nil .And. jQry['limit']  != Nil, Val(jQry['limit']),  20)
    Local jResp   := JsonObject():New()
    Local aItens  := {}
    Local cLastKey := ''

    DbSelectArea('SA1')
    SA1->(DbSetOrder(1))
    If !Empty(cCursor)
        // cursor = base64(A1_FILIAL+A1_COD+A1_LOJA) do último item
        SA1->(DbSeek(xFilial('SA1') + B64Decode(cCursor)))
        SA1->(DbSkip())   // pula o último item da página anterior
    Else
        SA1->(DbSeek(xFilial('SA1')))
    EndIf
    While !SA1->(EoF()) .And. SA1->A1_FILIAL == xFilial('SA1') .And. Len(aItens) < nLim
        AAdd(aItens, {'codigo' => SA1->A1_COD, 'loja' => SA1->A1_LOJA, 'nome' => DecodeUtf8(SA1->A1_NOME)})
        cLastKey := SA1->A1_COD + SA1->A1_LOJA
        SA1->(DbSkip())
    EndDo

    jResp['itens']       := aItens
    jResp['nextCursor']  := IIf(Len(aItens) == nLim, B64Encode(cLastKey), '')   // vazio = fim
    jResp['hasMore']     := Len(aItens) == nLim
    oRest:setResponse(EncodeUtf8(jResp:ToJson()))
Return
```

## 10. Upload/download binário + streaming

### Upload (cliente envia binário)

```advpl
@Post("/v1/anexo/:tipo")
User Function UploadAnexo()
    Local jPath := oRest:getPathParamsRequest()
    Local cBin  := oRest:getBodyRequest()   // bytes brutos, SEM DecodeUtf8
    Local cExt  := jPath['tipo']
    Local cFile := '\system\anexos\' + cValToChar(Time()) + '.' + cExt
    Local nH    := FCreate(cFile)
    If nH == -1
        oRest:setStatusCode(500)
        Return
    EndIf
    FWrite(nH, cBin)
    FClose(nH)
    oRest:setStatusCode(201)
    oRest:setResponse('{"path":"' + cFile + '"}')
Return
```

Limite default: 8MB por request. Pra arquivos maiores, ajustar `MaxStringSize` no .ini ou usar multipart chunked.

### Download (servidor entrega binário)

```advpl
@Get("/v1/anexo/:id")
User Function DownloadAnexo()
    Local jPath := oRest:getPathParamsRequest()
    Local cFile := AchaArquivo(jPath['id'])
    Local nH    := FOpen(cFile, 0)
    Local cBin  := ""
    If nH == -1
        oRest:setStatusCode(404)
        Return
    EndIf
    cBin := FRead(nH, FSeek(nH, 0, 2))
    FSeek(nH, 0)
    cBin := FRead(nH, FSeek(nH, 0, 2))
    FClose(nH)

    oRest:setContentType('application/octet-stream')
    oRest:setHeaderResponse('Content-Disposition', 'attachment; filename="' + cFileName(cFile) + '"')
    oRest:setHeaderResponse('Content-Length', cValToChar(Len(cBin)))
    oRest:setResponse(cBin)
Return
```

## 11. CORS, content negotiation, headers

### CORS no .ini (recomendado)

```ini
[HTTPURI]
CORSEnable=1
AllowOrigin=https://meu-frontend.com    ; específico em prod
; AllowOrigin=*                          ; * só em dev/staging
```

Aplica globalmente em todos os endpoints. Override per-endpoint se precisar de policy diferente.

### CORS manual no endpoint

```advpl
oRest:setHeaderResponse('Access-Control-Allow-Origin',  'https://app.cliente.com')
oRest:setHeaderResponse('Access-Control-Allow-Methods', 'GET,POST,PUT,PATCH,DELETE,OPTIONS')
oRest:setHeaderResponse('Access-Control-Allow-Headers', 'Content-Type,Authorization,tenantId,X-Request-Id')
oRest:setHeaderResponse('Access-Control-Max-Age', '3600')
```

Sempre implementar `@Options(...)` separado pro preflight.

### Content negotiation

```advpl
Local cAccept := oRest:getHeaderRequest('Accept')
If 'application/xml' $ cAccept
    oRest:setContentType('application/xml')
    oRest:setResponse(JsonToXml(jResp))
Else
    oRest:setContentType('application/json; charset=utf-8')
    oRest:setResponse(EncodeUtf8(jResp:ToJson()))
EndIf
```

## 12. Encoding boundary cp1252 ↔ UTF-8

Regra de ouro: **input passa por `DecodeUtf8`, output passa por `EncodeUtf8`**.

```advpl
// Body chega em UTF-8 (cliente moderno), fonte ADVPL é cp1252
Local cBody := DecodeUtf8(oRest:getBodyRequest())
Local jReq  := JsonObject():New()
jReq:FromJson(cBody)
// Agora jReq['nome'] = 'João' em bytes cp1252 corretos

// Pra responder
Local jResp := JsonObject():New()
jResp['nome'] := AllTrim(SA1->A1_NOME)   // já em cp1252 (vem do banco)
oRest:setResponse(EncodeUtf8(jResp:ToJson()))   // converte cp1252 → UTF-8 pro cliente
oRest:setContentType('application/json; charset=utf-8')
```

Sintomas de erro:
- Cliente recebe `JoÃ£o` em vez de `João` → faltou `EncodeUtf8` na resposta
- Server crash em `jReq:FromJson` quando body tem acento → faltou `DecodeUtf8` no input
- Resposta corta no meio em acentos → encoding misturado (alguns campos UTF-8, outros cp1252)

**Try/fallback** pra cobrir cliente legado que manda cp1252 puro:

```advpl
Local cBody := oRest:getBodyRequest()
Local cTry  := ''
Try
    cTry := DecodeUtf8(cBody)
Catch
    cTry := cBody   // não era UTF-8, assume cp1252
EndCatch
```

Veja [`advpl-encoding`](../advpl-encoding/SKILL.md) skill pra detalhes do boundary.

## 13. Consumo de APIs externas

### REST: `FwRest` (recomendado)

```advpl
Local oRestCli := FWRest():New('https://api.externa.com')
oRestCli:SetPath('/v1/clientes/12345')
oRestCli:SetTimeOut(30)
oRestCli:SetHeaderRequest({'Authorization: Bearer ' + cToken, ;
                            'Accept: application/json'})

If oRestCli:Get()   // ou :Post(cBody), :Put(cBody), :Delete()
    Local cResp := oRestCli:GetResult()
    Local jResp := JsonObject():New()
    jResp:FromJson(cResp)
    ConOut('Nome: ' + jResp['nome'])
Else
    ConOut('Erro HTTP: ' + cValToChar(oRestCli:GetHttpCode()))
    ConOut('Erro msg: ' + oRestCli:GetLastError())
EndIf
```

### REST low-level: `HttpPost`/`HttpGet` (legado)

```advpl
Local cResp := HttpPost('https://api.externa.com/v1/clientes', '', cBody, 30, ;
                        {'Authorization: Bearer ' + cToken, ;
                         'Content-Type: application/json'})
```

### SOAP: `TWsdlManager`

```advpl
Local oWsdl := TWsdlManager():New()
oWsdl:ParseURL('https://servico.com/ws?wsdl')
oWsdl:SetOperation('BuscaCliente')
oWsdl:SetParam('codigo', '000001')
If oWsdl:SendSoapMsg()
    ConOut(oWsdl:GetSoapResponse())
EndIf
```

### OAuth2 client credentials (pegar token de IdP externo)

```advpl
Local cBodyTok := 'grant_type=client_credentials&client_id=' + cId + '&client_secret=' + cSecret
Local cRespTok := HttpPost('https://idp.com/oauth2/token', '', cBodyTok, 30, ;
                            {'Content-Type: application/x-www-form-urlencoded'})
Local jTok := JsonObject():New()
jTok:FromJson(cRespTok)
Local cBearer := jTok['access_token']
// Cachear em variável estática + invalidar próximo expires_in
```

## 14. Pegadinhas testadas

### Notation
1. **`oRest` é `Nil` fora de contexto REST** — chamar `User Function` decorada via `U_FUNC` no SmartClient crasha. Decorator só ativa via HTTP.
2. **Path com `:param` aceita **um nível** entre slashes** — `/a/:x/b/:y` ok; `/a/:x:y` não.
3. **Decorator deve ficar IMEDIATAMENTE acima** da função — comentário no meio invalida.
4. **`oRest:getPathParamsRequest()` retorna `Nil`** quando endpoint não tem `:param` — sempre testar.
5. **Endpoints duplicados em fontes diferentes** geram colisão silenciosa — último compilado ganha.
6. **`@Patch` em build muito antigo** é ignorado sem erro.
7. **`User Function` decorada SEM prefixo de cliente** vira regra geral em REST (`SEC-002` catálogo) — exceção justificada.
8. **`setResponse` cumulativo** — mesmo bug do clássico, idem fix.
9. **`oRest:setStatusCode(204)` + body não-vazio** — alguns clientes rejeitam.
10. **Header case-insensitive ao ler, case-sensitive ao gravar** — `getHeaderRequest('Authorization')` pega `authorization:` mas `setHeaderResponse('Content-Type'...)` precisa exato.

### Clássico
11. **`::SetResponse` cumulativo** — bug #1, acumule local.
12. **`WSMETHOD GET` repetido sem sub-nome** — 404 silencioso no 2º.
13. **`WSDATA` sem `WSRECEIVE` no WSMETHOD** — `::var` sempre `Nil`.
14. **Esquecer `DEFAULT ::var := ""`** em OPTIONAL — concat com `Nil` quebra.
15. **`::aURLParms` é posicional** — refatorar URL quebra silenciosamente.
16. **`SetRestFault` é função global, não `::SetFault`** — confundir dá erro de compilação obscuro.
17. **WSRESTFUL sem `PATH`** explícito — URL deriva do nome da classe, vira `/api/<NomeClasse>`, surpreendente.

### Comum aos dois
18. **CORS preflight (OPTIONS) sem implementação** — POST/PUT/DELETE de browser quebra com erro CORS, mesmo com `CORSEnable=1` no .ini se faltar `@Options`/`WSMETHOD OPTIONS`.
19. **JSON malformado no body** — `JsonObject():FromJson()` retorna mensagem de erro, mas se você ignora o retorno o `jReq[key]` vira `Nil` e quebra adiante.
20. **`tenantId` errado** → request cai no ambiente errado, lê/grava dados de outra empresa SEM erro. Sempre logar `cEmpAnt/cFilAnt` no boot do endpoint.
21. **`RpcSetEnv` em REST** — SEC-001 crítico, use `PrepareIn` + `tenantId`.
22. **Esquecer `EncodeUtf8`/`DecodeUtf8`** — acentos viram `Ã§`/`Ã£` no cliente.
