---
description: Cruza chamadas REST do frontend Angular (HttpClient) com as rotas TLPP do Protheus (@Get/@Post) — rastreabilidade ponta-a-ponta front↔back
disable-model-invocation: true
arguments: []
allowed-tools: [Bash]
---

# `/plugadvpl:poui-bridge`

Lista os matches entre as chamadas HttpClient do Angular e as rotas REST do
Protheus (anotações `@Get`/`@Post` TLPP indexadas em `rest_endpoints`).

## Pré-requisito

1. `plugadvpl ingest-poui <dir-frontend>` — ingere projetos @po-ui/* e extrai
   datasources REST dos `.ts`.
2. `plugadvpl ingest` — indexa os fontes TLPP com as rotas `@Get`/`@Post`.

## Execução

```bash
uvx plugadvpl@0.27.0 --format md poui-bridge
```

## Colunas de saída

| Coluna | Descrição |
|---|---|
| `verbo` | Verbo HTTP (GET, POST, …) |
| `path` | Path REST casado (ex: `/pedidos`) |
| `front` | Arquivo TypeScript + linha da chamada |
| `back` | Fonte TLPP + função que implementa a rota |

## Relacionado

- Skill `ingest-poui` — ingere projetos PO UI e extrai datasources.
- Skill `ingest` — indexa fontes ADVPL/TLPP (inclui rotas REST).
