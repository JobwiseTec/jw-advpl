---
description: Verifica simbolos ADVPL afirmados (funcoes, tabelas, campos SX3, MV_, chamadas, gatilhos) contra o indice plugadvpl — sound verifier deterministico, anti-alucinacao. Use para checar se um simbolo existe antes de afirma-lo, ou no fluxo grounded (hook Stop). NAO use para gerar codigo (use advpl-code-generator) nem para impacto de mudanca (use impacto).
disable-model-invocation: true
arguments: [kind, symbol]
allowed-tools: [Bash]
---

# `/plugadvpl:verify-claims`

Verificador **deterministico** (set-membership contra o indice SQLite): recebe os
simbolos que uma resposta afirmou e devolve, por claim, se ele **existe /
nao-encontrado / a relacao vale**, com um bloco honesto de cobertura. E o *sound
external verifier* do roadmap-ia (ver `docs/roadmap-ia/01-verify-claims.md`).

> `not_found` e **mundo aberto** — NAO significa "alucinado". Pode ser lacuna de
> cobertura ou simbolo padrao TOTVS nao indexado. Interprete pelo bloco
> `coverage` + `confidence` (so `not_found` de alta confianca em corpus completo
> e acionavel).

## Uso

Lote via stdin (forma canonica, usada pelo hook `Stop`):

```
echo '{"claims":[{"id":"c1","kind":"function","symbol":"FWFormStruct"},
                 {"id":"c2","kind":"field","symbol":"ZX1_STATUS"}]}' \
  | plugadvpl --format json verify-claims --stdin
```

Forma curta (1 claim):

```
plugadvpl --format json verify-claims --kind function --symbol FWFormStruct
```

## Kinds aceitos

| `kind` | Verifica contra | `symbol` / campos |
|---|---|---|
| `function` | `fonte_chunks` + nativas + restritas | nome da funcao (prefixo `U_` normalizado) |
| `table` | SX2 (`tabelas`) | codigo (ex: `ZX1`) |
| `field` | SX3 (`campos`) | nome do campo (ex: `ZX1_STATUS`) |
| `param` | SX6 (`parametros`) | `MV_*` |
| `call_edge` | `chamadas_funcao` | `caller` + `callee` |
| `trigger` | SX7 (`gatilhos`) | `field` |

## Status do verdict

`exists` · `not_found` · `relation_holds` · `relation_absent` · `unsupported_kind`.
`confidence` cai em **miss**, nao em hit; SX2/SX3/SX6 sao completos para
**customizacoes do cliente** (padrao TOTVS nao e indexado por design).

## Fluxo grounded (anti-alucinacao)

Liste os simbolos afirmados no fim da resposta num bloco; o hook `Stop`
(`hooks/stop-verify.mjs`) roda esta verificacao e pede correcao so do que falhou:

```
<plugadvpl-claims>
{"claims":[{"id":"c1","kind":"function","symbol":"FWFormStruct"}]}
</plugadvpl-claims>
```

Ver `docs/roadmap-ia/03-grounding-flow.md`. Cross-ref: [[plugadvpl-index-usage]].
