---
description: Lint de templates PO UI — detecta bindings p-* nao catalogados (regra POUI-PROP, anti-alucinacao)
disable-model-invocation: true
arguments: []
allowed-tools: [Bash]
---

# `/plugadvpl:poui-lint`

Detecta bindings `p-*` usados em templates `<po-*>` que **nao existem no
catalogo verificado** `poui_componentes` (948 bindings extraidos do
codigo-fonte oficial do `po-angular`). Regra: **POUI-PROP**.

Um binding ausente do catalogo indica alucinacao da IA ou erro de digitacao —
o Protheus renderizara o atributo ignorado silenciosamente.

## Pre-requisito

```bash
plugadvpl ingest-poui <dir-frontend>
```

Popula `poui_componentes_uso` varrendo os `.html` do projeto.

## Execucao

```bash
uvx plugadvpl@0.25.1 poui-lint
```

## Colunas de saida

| Coluna | Descricao |
|---|---|
| `arquivo` | Template HTML com o binding suspeito |
| `linha` | Linha do componente no arquivo |
| `componente` | Componente Angular (`po-button`, `po-table`, ...) |
| `binding` | Binding `p-*` nao encontrado no catalogo |

## Exemplo

```bash
uvx plugadvpl@0.25.1 --format md poui-lint
```

## Relacionado

- Skill `poui-componentes` — consulta o catalogo de bindings verificados.
- Skill `ingest-poui` — ingere projetos PO UI e extrai templates.
- Skill `poui-bridge` — cruza datasources REST front-back.
