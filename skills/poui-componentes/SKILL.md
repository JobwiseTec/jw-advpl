---
description: Referência verificada dos bindings p- (inputs/outputs) por componente PO UI — consulte antes de escrever templates Angular para não inventar atributos inexistentes
disable-model-invocation: true
arguments: [componente]
allowed-tools: [Bash]
---

# `/plugadvpl:poui-componentes`

O catálogo `poui_componentes` contém **948 bindings `p-*`** (inputs e outputs)
extraídos do repositório oficial `po-angular`. Cada entrada mapeia o atributo
HTML (`p-columns`) para a propriedade TypeScript (`columns`) e o componente-pai
(`po-table`).

Use este comando **antes** de escrever templates Angular com componentes `po-*`
para evitar inventar inputs/outputs que não existem — alucinação comum porque
os nomes dos atributos PO UI seguem convenção própria e nem sempre são
inferíveis pelo nome do componente.

## Uso

```
/plugadvpl:poui-componentes [componente]
```

Sem argumento, lista todos os componentes. Com argumento, filtra por nome de
componente (case-insensitive).

## Execução

```bash
uvx plugadvpl@0.26.0 --format md poui-componentes $ARGUMENTS
```

## Exemplo

```
$ uvx plugadvpl poui-componentes po-table
componente  kind    binding            propriedade
po-table    input   p-actions          actions
po-table    input   p-columns          columns
po-table    input   p-items            items
po-table    output  p-action-right     actionRight
...
```

> **Para agente IA:** consulte ANTES de gerar template `<po-table>` ou qualquer
> componente `po-*`. O catálogo é gerado do código-fonte do po-angular e não
> inventa atributos. Se um binding não aparece aqui, ele não existe nesta versão.

## Relacionado

- Skill `ingest-poui` — detecta projetos PO UI e versão `@po-ui/*`.
- Skill `poui-bridge` — cruza chamadas Angular (front) com rotas REST (back).
