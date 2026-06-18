---
description: Lint PO UI — bindings p-* (POUI-PROP), interface .ts (POUI-IFACE), import de pacote (POUI-IMPORT) e divergencia de versao (POUI-VERSION)
disable-model-invocation: true
arguments: []
allowed-tools: [Bash]
---

# `/plugadvpl:poui-lint`

Detecta erros comuns de geracao de codigo PO UI, cruzando o uso real com os
catalogos verificados extraidos do `po-angular`:

- **POUI-PROP** — binding `p-*` em template `<po-*>` que **nao existe** no
  catalogo `poui_componentes` (ex.: `<po-table [p-fake]>`).
- **POUI-IFACE** — em objeto `.ts` tipado por interface `Po*` (ex.:
  `cols: PoTableColumn[] = [...]`): **chave** que nao existe na interface
  (`field` em vez de `property`) ou **valor** fora do enum
  (`type: 'money'` em vez de `'currency'`). Cruza com `poui_interfaces`.
- **POUI-IMPORT** — componente usado cujo **pacote** npm nao e importado no
  projeto (ex.: `<po-page-dynamic-table>` e de `@po-ui/ng-templates`, mas o
  projeto so importa `@po-ui/ng-components`). Escopo por projeto.
- **POUI-VERSION** *(aviso)* — projeto num **major** PO UI diferente do catalogo
  embarcado (snapshot do po-angular). Como bindings/props mudam entre majors, os
  findings acima podem divergir; serve de alerta de contexto.

So flagra interface/componente **conhecido** no catalogo (zero falso-positivo
em tipo custom). Um achado indica alucinacao da IA ou erro de digitacao.

## Pre-requisito

```bash
plugadvpl ingest-poui <dir-frontend>
```

Popula `poui_componentes_uso` (dos `.html`), `poui_iface_uso` e `poui_imports`
(dos `.ts`).

## Execucao

```bash
uvx plugadvpl@0.44.0 poui-lint
```

## Colunas de saida

| Coluna | Descricao |
|---|---|
| `arquivo` | Arquivo `.html` (POUI-PROP) ou `.ts` (POUI-IFACE) |
| `linha` | Linha do uso suspeito |
| `regra` | `POUI-PROP` ou `POUI-IFACE` |
| `alvo` | `componente.binding` ou `Interface.propriedade` |
| `mensagem` | Descricao do problema (com os valores validos, no caso de enum) |

## Exemplo

```bash
uvx plugadvpl@0.44.0 --format md poui-lint
```

## Relacionado

- Skill `poui-componentes` — consulta o catalogo de bindings verificados.
- Skill `ingest-poui` — ingere projetos PO UI e extrai templates.
- Skill `poui-bridge` — cruza datasources REST front-back.
