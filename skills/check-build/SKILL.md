---
description: Verifica uso de método FW*/Ms* ausente numa build Protheus alvo (catálogo apis_por_build), antes de compilar
disable-model-invocation: true
arguments: [arquivo]
allowed-tools: [Bash]
---

# `/plugadvpl:check-build`

Sinaliza chamadas a métodos `FW*`/`MsDialog`/`FWBrowse` que **não existem** na build
Protheus alvo — pegando antes do `Cannot find method ...` em runtime. Resolve
`oVar := Classe():New()` por função e só reporta `oVar:Metodo(` quando a classe é
confirmada no catálogo `apis_por_build` e o build alvo cai fora da janela de
disponibilidade. **Zero falso-positivo** (var não-rastreável → silêncio).

Não precisa de índice ingerido — lê o catálogo embarcado + o fonte direto.

## Uso

```
/plugadvpl:check-build <arquivo> --target-build <build>
```

## Opções

- `--target-build <build>` / `-b` — build Protheus alvo (ex: `24.3.0.5`). **Obrigatório.**

## Execução

```bash
uvx plugadvpl@0.36.0 --format md check-build $ARGUMENTS
```

> **Para agente IA:** rode ANTES de compilar/smoke-test quando o cliente roda uma
> build específica. Catálogo é **denylist**: método não-catalogado = assume que
> existe (não flaga). O catálogo cresce via PR com dados verificados de TDN.

## Exemplo

```
$ uvx plugadvpl check-build PAINEL01.prw --target-build 24.3.0.5
arquivo      linha  destino                    classe         ausente_em  nota
PAINEL01.prw 573    oBrowse:SetBlkBackColor    FWMarkBrowse   24.3.0.5    use AddLegend/SetColorFn...
```

## Relacionado

- Skill `advpl-ui-patterns` — patterns visuais + alternativas por build.
