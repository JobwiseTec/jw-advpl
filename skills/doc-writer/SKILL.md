---
description: Gera bloco Protheus.doc canônico TOTVS para função ADVPL/TLPP a partir de flags estruturadas — inverso de /plugadvpl:docs (v0.17.0+)
disable-model-invocation: true
arguments: [funcao + flags]
allowed-tools: [Bash]
---

# `/plugadvpl:doc-writer`

**Inverso de `/plugadvpl:docs`** (v0.4.2 lê blocos Protheus.doc; v0.17.0 **gera**). Recebe metadata estruturada via flags CLI e devolve o bloco `/*/{Protheus.doc} ... /*/` no formato canônico TOTVS, pronto pra colar antes da declaração da função no fonte ADVPL/TLPP.

**Padrão oficial seguido:** https://github.com/totvs/tds-vscode/blob/master/docs/protheus-doc.md

Roundtrip-compatible: `plugadvpl docs --show <funcao>` recupera as tags geradas via `doc-writer` sem perda.

## Quando usar

- LLM acaba de **escrever** ou **refatorar** uma função ADVPL/TLPP e precisa adicionar header documentado.
- Função existente sem `/*/{Protheus.doc} ... /*/` (cobertura ruim em `/plugadvpl:cobertura-doc` ou aparece em `/plugadvpl:docs --orphans`).
- Padronizar headers num módulo inteiro (combinar com `/plugadvpl:find --semDoc` + loop).
- Migrar comentários soltos pra `@param/@return/@deprecated` canônicos.

**Não use** se a função já tem header — primeiro rodar `/plugadvpl:docs --show <funcao>` pra verificar.

## Uso

```
/plugadvpl:doc-writer <funcao>
    [--type function|user_function|method|class|property]
    [--summary "descrição curta"]
    [--author "<nome>"] [--since YYYY-MM] [--version X.Y.Z]
    [--deprecated "motivo"]
    [--param "nome,tipo,desc"] (repetível; [nome] = opcional)
    [--return "tipo,desc"]
    [--example "snippet"] (repetível)
```

**Output:** bloco no stdout, pronto pra colar.

## Exemplos

### Mínimo (só nome)

```bash
plugadvpl doc-writer MinhaFunc
```

Saída:

```
/*/{Protheus.doc} MinhaFunc
    @type function
/*/
```

### Completo (caso típico de User Function)

```bash
plugadvpl doc-writer CalcICMS --type user_function \
    --author "Joao Silva" --since 2026-05 --version 1.0 \
    --summary "Calcula ICMS conforme TES informada." \
    -p "cTES,character,codigo TES" \
    -p "[nValor],numeric,valor base opcional" \
    --return "numeric,valor do ICMS calculado" \
    --example "nIcms := U_CalcICMS('501', 1000)"
```

Saída:

```
/*/{Protheus.doc} CalcICMS
    Calcula ICMS conforme TES informada.

    @type user_function
    @author Joao Silva
    @since 2026-05
    @version 1.0
    @param cTES, character, codigo TES
    @param [nValor], numeric, valor base opcional
    @return numeric, valor do ICMS calculado
    @example
        nIcms := U_CalcICMS('501', 1000)
/*/
```

### Marcar função deprecated

```bash
plugadvpl doc-writer OldFunc --deprecated "Use NovaFunc no lugar"
```

### Pegar metadata em JSON (pra processar em scripts)

```bash
plugadvpl --format json doc-writer CalcICMS --author Joao -p "n,numeric,x"
```

## Execução

```bash
uvx plugadvpl@0.20.0 doc-writer $ARGUMENTS
```

## Convenções importantes

- **Param opcional:** envolva o nome em colchetes — `'[nIdx],numeric,indice'` → emite `@param [nIdx], numeric, indice`.
- **Tipos canônicos ADVPL:** `character`, `numeric`, `logical`, `date`, `array`, `block`, `object`, `nil`, `mixed`. LLM deve usar esses (não `string`/`int`/`bool`).
- **@type:** `function`, `user_function`, `method`, `class`, `property` (lowercase). Default `function`.
- **Multi-linha em --example:** use `\n` literal na shell ou aspas em volta de string já com newline. Cada linha será indentada 8 espaços dentro do bloco.

## Workflow recomendado

1. Identifique funções sem doc: `plugadvpl docs --orphans --modulo SIGAFAT`
2. Pra cada uma, leia signature do fonte: `plugadvpl arch <arquivo>` (mostra params/return)
3. Gera o bloco: `plugadvpl doc-writer <funcao> --type <X> --author "..." -p "..."`
4. Cole antes da declaração da função no fonte
5. Pra `.prw` (cp1252): use `plugadvpl edit-prw stage <arquivo>` antes de editar (evita corromper acentos)
6. Valida: `plugadvpl docs --show <funcao>` (lê o que acabou de gerar)
7. Suba cobertura: `plugadvpl cobertura-doc` (deve ter melhorado o pct)

## Links

- `/plugadvpl:docs` — lê Protheus.doc agregado (lado oposto)
- `/plugadvpl:arch` — extrai signature da função (params/return/tipo)
- `/plugadvpl:cobertura-doc` — pct de funções com header por módulo
- `/plugadvpl:edit-prw` — manipulação segura de `.prw` cp1252
- [Padrão Protheus.doc TOTVS oficial](https://github.com/totvs/tds-vscode/blob/master/docs/protheus-doc.md)
