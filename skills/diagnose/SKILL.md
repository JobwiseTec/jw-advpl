---
description: Avalia os pontos de decisao de um fonte contra um registro (desfecho exato + relativizacao - numero sensivel vira razao)
disable-model-invocation: true
arguments: [arquivo]
allowed-tools: [Bash]
---

# `/plugadvpl:diagnose`

Avalia os **pontos de decisao** (`If`/`ElseIf`/`While`) de um fonte ADVPL contra um **registro**
(valores reais de campos/variaveis) e devolve, para cada comparacao:

- o **desfecho EXATO** (`VERDADEIRO`/`FALSO`) — aritmetica deterministica sobre os valores reais;
- uma **explicacao relativizada** — numeros sensiveis viram **razao** (`saldo ~103% de limite`) em vez
  do R$ real; status/flags/parametros sao mostrados (decidem e nao sao sensiveis).

Serve para **debugar bug dependente de dado** (ex.: "por que esse cliente bloqueou por limite?") sem
vazar o valor real: a IA ve o desfecho e a relacao, nunca o numero.

## Uso

```
/plugadvpl:diagnose <arquivo> --record-file <registro.json>
```

O registro e um JSON `{campo: valor}` (via `--record '{"A1_LC": 50000}'` ou `--record-file x.json`).
`--fields-file` (opcional) injeta os campos financeiros do SX3 para classificacao exata.

## Execucao

```bash
uvx plugadvpl@0.44.0 --format md diagnose $arquivo --record-file registro.json
```

> A flag `--format` vem **antes** do subcomando (e global no callback). Use `--format md` (ou `json`).

## Exemplo

Registro: `{"A1_MSBLQL": "2", "nSaldo": 21500, "nValPed": 30000, "A1_LC": 50000, "MV_X_LIBLIM": "N"}`

```
| linha | explicacao |
| 4     | A1_MSBLQL=2 == 1 -> FALSO |
| 8     | ( nSaldo + nValPed ) ~103% de A1_LC -> VERDADEIRO |
| 9     | SuperGetMV("MV_X_LIBLIM")=N == N -> VERDADEIRO |
```

> A IA conclui "bloqueou na linha 8 + 9" sem ver o R$ real (50000/51500).

## Garantias

- **Determinismo:** mesmo (fonte, registro) -> mesma saida.
- **Exatidao:** o desfecho e exato sobre os valores reais; so a exibicao do numero vira razao.
- **Nao chuta:** operando nao-resolvivel -> `(nao avaliavel)`.

## Proximos passos sugeridos

- `/plugadvpl:arch <arquivo>` — visao geral do fonte
- gerar `campos_financeiros.json` do SX3 (ver `docs/seguranca.md`) para `--fields-file`
