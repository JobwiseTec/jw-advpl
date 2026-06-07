---
description: Integração ponta-a-ponta PO UI (Angular) ↔ Protheus REST (TLPP/ADVPL). Use ao construir tela PO UI que consome API Protheus, ligar po-page-dynamic-* a um @Get/@Post, configurar proxy do ng serve, debugar 401/CORS/Origin do front, ou mapear dicionário SX → PoDynamicFormField. Cobre o contrato REST que os componentes dynamic esperam, FWCallApp/protheus-lib-core, e as pegadinhas de thread REST.
---

# protheus-poui — Integração PO UI ↔ Protheus REST

Como o frontend **Angular + PO UI** conversa com o backend **TLPP/ADVPL REST** do
Protheus. Foca no que quebra na prática (validado em ambiente real, RPO 2510).

> Skills irmãs: [[advpl-webservice]] (como expor o REST no Protheus — `@Get/@Post`,
> `oRest`, WSRESTFUL, auth, multi-tenant), `poui-componentes` (catálogo de bindings
> `p-*` + interfaces de config), `poui-bridge` (cruza chamadas do front com as rotas
> do back), `poui-lint` (POUI-PROP/IFACE/IMPORT/VERSION).

## O modelo mental

No SmartClient clássico, o menu chama **um fonte** (ex.: `MATA030`) que **desenha
a tela + lê o dado + aplica a regra**. No PO UI, o menu chama o **app Angular**
(via `FWCallApp`) — a **tela é o Angular**; o seu fonte vira uma **API REST**
(`@Get/@Post`) chamada **só para servir dado**. O ADVPL continua o cérebro
(MVC/ExecAuto/SX); muda quem desenha a tela e como ela pede dados.

## 1. O contrato que o `po-page-dynamic-*` espera

O CRUD PO UI quase nunca escreve `HttpClient` à mão: usa os **templates dinâmicos**
com o binding `[p-service-api]="'/rest/api/v1/clientes'"`. Esses componentes
assumem um **contrato REST fixo** — o backend precisa responder **exatamente** assim:

| Verbo | Rota | Resposta esperada |
|---|---|---|
| `GET` | `/recurso?page=&pageSize=` | `{ "items": [...], "hasNext": bool }` |
| `GET` | `/recurso/:id` | o objeto |
| `POST` | `/recurso` | `201` |
| `PUT` | `/recurso/:id` | `200` |
| `DELETE` | `/recurso/:id` | `204` |

> ⚠️ Se o `@Get` devolve `{"data":[...]}` em vez de `{"items":[...],"hasNext":...}`,
> a `po-page-dynamic-table` **não popula** — sem erro óbvio. O componente é "burro"
> quanto ao formato: ou o backend fala o dialeto dele, ou nada aparece.

## 2. Proxy no `ng serve` (dev) — a parte que mais custa tempo

No dev o navegador só fala com `localhost:4200`; o proxy encaminha `/rest` pro
AppServer, **injeta o Basic auth** e **remove o header `Origin`** (senão 401, ver §3).
Angular 17+/Vite usa o hook `configure` (**não** o antigo `onProxyReq`):

```js
// proxy.conf.js  (Angular 17+ / Vite)
module.exports = {
  '/rest': {
    target: 'http://localhost:8181', secure: false, changeOrigin: true,
    configure: (proxy) => proxy.on('proxyReq', (req) => {
      req.removeHeader('origin'); req.removeHeader('referer');   // evita 401 do Protheus
      const t = Buffer.from(`${process.env.PROTHEUS_USER}:${process.env.PROTHEUS_PWD}`).toString('base64');
      req.setHeader('Authorization', 'Basic ' + t);              // credencial NÃO vai pro front
    }),
  },
};
```

## 3. 🔴 A pegadinha #1: browser recebe 401, mas o `curl` recebe 200

Com **CORS desligado** no `appserver.ini`, o REST do Protheus **nega com 401
qualquer request que tenha o header `Origin`** — que **todo navegador manda** —,
mesmo com Basic/Bearer **válido**. O `curl` não manda `Origin` → passa.

```bash
curl -u user:pwd -H "Origin: http://x" .../rest/...   # -> 401
curl -u user:pwd                       .../rest/...   # -> 201
```

- **Dev:** o proxy remove o `Origin` (§2).
- **Prod:** `[HTTPURI] CORSEnable=1` + `AllowOrigin` controlado, restart do AppServer.

## 4. App embarcado no Protheus — `FWCallApp` + `protheus-lib-core`

Quando o app roda **dentro** do Protheus (não num navegador externo):

1. O menu chama `FWCallApp("meu-app", "/clientes")` — abre o app Angular num
   navegador embutido no SmartClient (motor **TWebEngine**).
2. Antes de mostrar, um bootstrap grava um **bearer token** em
   `sessionStorage['ERPTOKEN']`.
3. `@totvs/protheus-lib-core` instala **interceptors HTTP** que, em *toda* chamada,
   injetam: `Authorization: Bearer <ERPTOKEN>`, a **URL base** real (resolve `/rest`)
   e o **empresa/filial** (`tenantId`). Você não gerencia token/filial no componente.
4. A chave `api_baseUrl` define o REST; se for `"/"`, o `FWCallApp` reescreve pro
   endereço dinâmico do ambiente.

Resultado: o usuário **não loga de novo** e cada request já vai autenticado e com a
filial certa. Fora do Protheus (teste/integração), pegue o token você mesmo em
`POST /api/oauth2/v1/token` e mande `Authorization: Bearer ...`.

## 5. Mapear dicionário SX → `PoDynamicFormField`

Ao gerar um formulário dinâmico a partir de uma tabela (ex.: `ZH1`), derive os
campos do **SX3**:

| PO UI (`PoDynamicFormField`) | Vem de | Observação |
|---|---|---|
| `property` | nome do campo (`zh1_nome`) | minúsculo, sem prefixo de filial |
| `label` | `X3_TITULO` (DecodeUtf8) | título do dicionário |
| `type` | `X3_TIPO` | `C`→`string`, `N`→`number`, `D`→`date` |
| `maxLength` | `TamSX3('ZH1_NOME')[1]` | tamanho do dicionário |
| `mask` | `X3_PICTURE` | máscara quando houver |
| `required` | `X3_OBRIGAT == '1'` | obrigatoriedade |
| `options` | `X3_CBOX` / consulta | combo/select (≥3 → select; <3 → radio) |

> Confira os nomes/valores de `PoDynamicFormField` com `plugadvpl poui-componentes
> PoDynamicFormField` (128 props; `--format json` pra lista completa). `field`≠`property`,
> `type:'money'` não existe (é `'currency'`) — o `poui-lint` (POUI-IFACE) pega isso.

## 6. Pegadinhas de thread REST (backend)

A thread WSREST tem ambiente "magro" — alguns helpers do SmartClient falham:

| Sintoma | Causa | Fix |
|---|---|---|
| `xFilial()` retorna `''` | filial não resolvida na thread REST | pegue a filial do header/`tenantId`; não confie no `xFilial()` |
| `GetSqlName('SA1')` quebra | dicionário não carregado | use o nome **literal** da tabela física (`SA1010`) |
| `oRest` é `Nil` | testou a função fora de um request REST | `oRest` só existe via HTTP; isole a regra numa função pura |
| `Return .F.` → HTTP 500 | notation lê `.F.` como falha | `Return` + `oRest:setStatusCode(nnn)` (lint **WS-005**) |
| `oRest:setContentType`/`getUserName` → 500 | não existem no `oRest` (só no `::Self`) | `setKeyHeaderResponse`/`GetUserName()` global (lint **WS-004**) |

## Checklist de uma tela PO UI sobre Protheus

1. Backend: `@Get/@Post` (ou `FWRestModel`) respondendo o **contrato** (§1), com
   `EncodeUtf8`/`DecodeUtf8` na fronteira e `Return` (nunca `.F.`).
2. Front: `po-page-dynamic-table`/`-edit` com `[p-service-api]` apontando pra rota.
3. Dev: `proxy.conf.js` injeta Basic + remove `Origin` (§2/§3).
4. Versões casadas: `@angular/core` ⇄ `@po-ui/ng-components` ⇄ `@totvs/protheus-lib-core`
   (mesmo major). `plugadvpl ingest-poui` detecta; `poui-lint` avisa (POUI-VERSION).
5. Valide: `plugadvpl poui-bridge` (front ⇄ back casam?), `plugadvpl poui-lint`.

## Referências

- [TDN — Nova interface do Protheus com PO UI](https://tdn.totvs.com/display/public/framework/Nova+interface+do+Protheus+com+PO+UI)
- [TDN — FwCallApp](https://tdn.totvs.com/display/framework/FwCallApp+-+Abrindo+aplicativos+Web+no+Protheus)
- [npm — @totvs/protheus-lib-core](https://www.npmjs.com/package/@totvs/protheus-lib-core)
- [PO UI](https://po-ui.io/)
