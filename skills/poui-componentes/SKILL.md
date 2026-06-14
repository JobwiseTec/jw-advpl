---
description: Referência verificada PO UI (po-angular) — bindings p- por componente E propriedades das interfaces de config (PoTableColumn, PoDynamicFormField...); consulte antes de escrever Angular para não inventar atributo/chave/valor
disable-model-invocation: true
arguments: [alvo]
allowed-tools: [Bash]
---

# `/plugadvpl:poui-componentes`

Referência verificada extraída do repositório oficial `po-angular`. Cobre duas
camadas onde a IA mais alucina ao gerar PO UI:

1. **Bindings `p-*`** (catálogo `poui_componentes`): o atributo HTML
   (`p-columns`) → propriedade TypeScript (`columns`) → componente (`po-table`).
2. **Interfaces de config** (catálogo `poui_interfaces`): o **objeto** que vai
   dentro do binding — ex.: o `PoTableColumn[]` do `p-columns`, ou o
   `PoDynamicFormField[]` do `p-fields`. Lista cada propriedade, se é opcional,
   e os **valores válidos** quando enumerados (ex.: `PoTableColumn.type` ∈ 14
   valores; escrever `type: 'money'` em vez de `'currency'` é erro comum).

Consulte **antes** de escrever template `<po-*>` OU o objeto de config no `.ts`,
para não inventar binding/chave/valor — alucinação comum porque PO UI segue
convenção própria.

## Uso

```
/plugadvpl:poui-componentes [alvo]
```

- Sem argumento → lista todos os componentes.
- Argumento iniciando com minúscula (`po-table`) → bindings `p-*` do componente.
- Argumento iniciando com maiúscula (`PoTableColumn`) → propriedades da interface
  de config (com valores válidos quando enumerados).
- `schematics` → generators oficiais (`ng generate @po-ui/...`) por caso-de-uso.
  **Antes de montar uma tela inteira à mão** (CRUD, login, agendador), prefira o
  schematic — ele gera o esqueleto correto; depois ajuste o config com o catálogo.
- **2º argumento = filtro por substring** da propriedade/binding:
  `poui-componentes PoDynamicFormField maxLength` ou `poui-componentes po-table columns`.

> **Catálogo grande:** o `table`/`md` trunca em 20 linhas. Use **`--format md`** já
> pega o essencial; para a lista **completa** (ex.: as 128 props de
> `PoDynamicFormField`) use **`--format json`** (nunca trunca) ou **`--limit 0`
> ANTES do subcomando** (`plugadvpl --limit 0 poui-componentes ...`) — `--limit` é
> flag global, não vai depois do subcomando.

## Execução

```bash
uvx plugadvpl@0.39.0 --format md poui-componentes $ARGUMENTS
```

## Exemplos

```
$ uvx plugadvpl poui-componentes po-table
componente  kind    binding            propriedade
po-table    input   p-columns          columns
po-table    output  p-action-right     actionRight
...

$ uvx plugadvpl poui-componentes PoTableColumn
interface       propriedade  tipo     opcional  valores
PoTableColumn   property     string   sim
PoTableColumn   type         string   sim       boolean, currency, date, dateTime, ...
PoTableColumn   width        string   sim
...
```

A coluna **`pacote`** mostra de qual npm o componente vem
(`@po-ui/ng-components` ou `@po-ui/ng-templates`) — use para importar do pacote
certo (os `po-page-dynamic-*`, `po-page-login` etc. são de `ng-templates`).

> **Para agente IA:** consulte ANTES de gerar `<po-*>` (bindings) **e** ANTES de
> montar o objeto de config tipado `Po*[]` no `.ts` (chaves/valores). Os catálogos
> são gerados do código-fonte do po-angular e não inventam nada. Se um binding,
> propriedade ou valor de `type` não aparece aqui, ele não existe nesta versão.

## Relacionado

- Skill `ingest-poui` — detecta projetos PO UI e versão `@po-ui/*`.
- Skill `poui-bridge` — cruza chamadas Angular (front) com rotas REST (back).
