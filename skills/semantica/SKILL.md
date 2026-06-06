---
description: Mostra a semântica contextual de um campo SX cujo significado muda conforme um discriminador (TIPO/PODER3/STATUS), não óbvia pelo nome nem pelo X3_DESCRIC
disable-model-invocation: true
arguments: [campo]
allowed-tools: [Bash]
---

# `/plugadvpl:semantica`

Alguns campos do dicionário SX têm significado **não-óbvio** que muda conforme
outro campo (discriminador). Isso não está no nome nem no `X3_DESCRIC` e queima
horas de debug quando se assume a semântica errada. Este comando consulta o
catálogo `campos_semantica` (só semântica **padrão Protheus**, sem termo de
cliente) e lista os significados por discriminador. Não precisa de índice.

## Uso

```
/plugadvpl:semantica <campo>
```

## Execução

```bash
uvx plugadvpl@0.28.0 --format md semantica $ARGUMENTS
```

## Exemplo

```
$ uvx plugadvpl semantica D2_NFORI
campo     tabela  discriminador  semantica
D2_NFORI  SD2     D2_TIPO=D      Em devolução/retorno, aponta para a Remessa original
D2_NFORI  SD2     D2_TIPO=N      Em saída normal, aponta para o documento de origem (semântica OPOSTA)
```

> **Para agente IA:** consulte ANTES de montar query/JOIN com campos de
> `SB6` (poder de terceiros) ou `SD2` (origem/retorno) — a mesma coluna pode ter
> semântica oposta conforme o tipo. O catálogo cresce via PR com dados TDN.

## Relacionado

- Skill `advpl-dicionario-sx` — dicionário SX completo (SX1/SX2/SX3/...).
