# U_EXEC — contrato de execução headless

> **Status:** especificação de referência · **Licença do reference impl:** MIT  
> **Versão:** v0.7.0 (Fase 0 #7) · **Audiência:** times de DevTooling/CI ADVPL

Este documento define um contrato HTTP/JSON para executar funções ADVPL em ambiente
headless — sem TDS, sem RPC binário, sem dependência de cliente proprietário.
A intenção é viabilizar smoke tests, CI e debug remoto via curl/HTTPie.

> ⚠️ **Aviso de produção.** Endpoint que executa função arbitrária expõe o RPO
> inteiro a qualquer caller autenticado. **Uso recomendado apenas em
> DEV/HML/CI** — atrás de firewall interno, com basic auth dedicada, e sem o
> RPO de produção carregado. Não há equivalente seguro para produção: para
> rotas REST de produção, escreva um WSRESTFUL específico por função (whitelist
> de fato).

---

## Endpoint

```
POST /rest/uexec
Content-Type: application/json; charset=utf-8
```

### Body

```json
{
  "function": "U_<NOME>",
  "args": [<valores JSON>]
}
```

| Campo      | Tipo         | Obrigatório | Descrição                                                |
|------------|--------------|-------------|----------------------------------------------------------|
| `function` | string       | sim         | Nome **com prefixo `U_`**. Reference impl rejeita sem prefixo (escudo simples contra função TOTVS arbitrária). |
| `args`     | array<json>  | não         | Argumentos passados na ordem ao `ExecBlock`. Default `[]`. Tipos JSON são mapeados: `string`/`number`/`boolean`/`null`/`array`/`object`. |

### Response (200)

```json
{
  "ok": true,
  "function": "U_<NOME>",
  "type": "<C|N|L|D|A|O|U>",
  "result": <valor JSON>
}
```

| Campo      | Tipo    | Descrição                                                          |
|------------|---------|--------------------------------------------------------------------|
| `ok`       | bool    | `true` se executou sem exceção; `false` caso contrário.            |
| `function` | string  | Echo do nome chamado.                                              |
| `type`     | string  | Tipo ADVPL do retorno: `C` string, `N` numérico, `L` lógico, `D` data, `A` array, `O` objeto, `U` undefined/Nil. |
| `result`   | mixed   | Valor serializado em JSON (`A`/`O` viram array/object; `D` vira string `YYYY-MM-DD`). Ausente se `ok=false`. |
| `error`    | string  | Mensagem de erro humana. Presente se `ok=false`.                   |
| `stack`    | string  | Pilha textual opcional (DEV only). Presente se `ok=false`.         |

### Status codes

| Código | Quando                                                            |
|--------|-------------------------------------------------------------------|
| 200    | `ok=true` no body — função executou sem exceção.                   |
| 400    | `function` ausente, formato inválido, ou nome sem `U_`.            |
| 401    | Sem autenticação (basic auth obrigatória no impl de referência).   |
| 500    | Exceção durante `ExecBlock`. `ok=false` + `error` no body.         |

---

## Exemplo (curl)

```bash
curl -s -u admin:totvs \
  -H 'Content-Type: application/json; charset=utf-8' \
  -X POST http://app:8080/rest/uexec \
  -d '{"function":"U_CALCFAT","args":["010001",1.5]}' \
| jq .
```

Resposta:

```json
{
  "ok": true,
  "function": "U_CALCFAT",
  "type": "N",
  "result": 1234.56
}
```

---

## Encoding

- Body **entra** em UTF-8 (header `charset=utf-8`). Reference impl chama
  `DecodeUtf8(::GetContent())` antes de `FromJson`.
- Body **sai** em UTF-8. Reference impl envolve resposta com
  `EncodeUtf8(FwJsonSerialize(...))`.

Isso é o padrão recomendado pelas regras [WS-002] e [WS-003] do plugin.

---

## Mapeamento de tipos JSON ↔ ADVPL

| JSON                | ADVPL                            | type devolvido |
|---------------------|----------------------------------|----------------|
| `"texto"`           | string                           | `C`            |
| `42`, `3.14`        | numeric                          | `N`            |
| `true` / `false`    | `.T.` / `.F.`                    | `L`            |
| `null`              | `Nil`                            | `U`            |
| `[a, b]`            | array `{a, b}`                   | `A`            |
| `{"k": v}`          | `JsonObject:New()` + `:Set('k', v)` | `O`         |
| `"2026-05-18"`      | data `CToD("18/05/2026")` (BR)   | `D`            |

> Datas em `args` são detectadas pelo formato ISO `YYYY-MM-DD`. Strings que
> não casarem com o pattern ficam como `C`.

---

## Reference implementation

Veja [examples/uexec.prw](examples/uexec.prw) — implementação MIT-licensed em
ADVPL (~150 linhas). Pontos relevantes:

- WSRESTFUL `UEXEC` (rota `/rest/uexec`).
- POST mapeado via `WSMETHOD POST exec WSSERVICE UEXEC`.
- Valida prefixo `U_` antes de chamar `ExecBlock`.
- Captura exceções via `ErrorBlock` + `Try/Recover` (Code Analysis-safe).
- Retorna `type` mapeado de `ValType()`.
- Resposta sempre passa por `EncodeUtf8(FwJsonSerialize(...))`.

### Anti-patterns que o reference NÃO faz

- ❌ Aceitar chamada de `Static Function` ou função sem prefixo `U_`.
- ❌ Logar `args` completos sem máscara (PII risk).
- ❌ Devolver stack trace por padrão (ativa só com `?debug=1`).
- ❌ Reutilizar mesma instância de `oJson` entre chamadas (estado vaza).

---

## Limitações conhecidas

- **Funções com parâmetros por referência** (`@param`) não são suportadas —
  JSON não tem semântica de referência. Use return value composto.
- **Funções que dependem de tela** (`Aviso`, `MsgYesNo`, `Pergunte` com
  `.T.`) **travam** o thread. O reference impl define `__GetStr()` como
  no-op para tentar mitigar, mas não há garantia.
- **Transações implícitas**: cada chamada **não** abre transação. Se sua
  função espera estar dentro de `BEGIN TRANSACTION`, abra dentro dela.

---

## Roadmap relacionado

- **Fase 2 — `plugadvpl exec`**: cliente HTTP nativo do plugin para chamar
  `/rest/uexec` direto da CLI (`plugadvpl exec U_CALCFAT '["010001"]'`).
- **Fase 4 — `plugadvpl smoke`**: bateria de smoke tests CI usando `/rest/uexec`.

---

## Licença

Este documento é **CC-BY-4.0**. O reference impl `examples/uexec.prw` é **MIT**
(ver header do arquivo). Ambos podem ser copiados/modificados livremente.
