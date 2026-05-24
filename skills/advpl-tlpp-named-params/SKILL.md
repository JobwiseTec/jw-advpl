---
description: TLPP suporta named arguments na chamada via operador `=` (igualdade). Permite ordem livre, omissão de opcionais e código autodocumentado. Liberado em AppServer 20.3.2.0+ (funções/métodos) e 24.3.1.0+ (classes via New()). Use ao escrever ou refatorar chamadas TLPP com 3+ parâmetros, parâmetros opcionais, ou ao modernizar Static Functions legadas.
---

# advpl-tlpp-named-params — Parâmetros Nomeados em TLPP

Recurso da linguagem TLPP (não disponível em ADVPL clássico) que permite passar argumentos pelo nome formal usando o operador **`=`** (igualdade). Elimina placeholders `,,,nil,`, libera ordem livre e torna chamadas autodocumentadas.

Skill complementar à [[advpl-tlpp]] (base TLPP: namespaces, classes, annotations, tipagem opcional). Esta skill foca no operador `=` no call site.

## Operador correto — `=` (igualdade)

```tlpp
// CERTO: operador é '=' (igualdade)
xParams(p2=b, p1=a, p6=f)

// ERRADO: ':=' é atribuição, não funciona como named arg
xParams(p2:=b)          // compile error

// ERRADO: ':' é send-message a objeto, não named arg
xParams(p2:b)           // compile error / interpretado como mensagem
```

Confusão comum porque outras linguagens usam `:=` ou `:` para named args. Em TLPP é literalmente `=`.

## Quando usar

- Funções com 3 ou mais parâmetros.
- Funções com parâmetros opcionais (omitir os irrelevantes).
- Refactor de `Static Function` legada com assinatura longa.
- Sempre que clareza > brevidade no call site.
- Funções de validação/configuração que aceitam várias chaves opcionais.

## Quando NÃO usar

- Função com 1-2 parâmetros triviais (overhead sintático sem ganho).
- Hot path com micro-otimização (overhead não medido, mas presumível).
- Build do AppServer abaixo dos mínimos (ver tabela abaixo) — operador `=` não é reconhecido.

## Pré-requisitos

| Requisito | Por quê |
|-----------|---------|
| `#include "tlpp-core.th"` | Sem ele, modificadores e sintaxe TLPP moderna não ligam |
| `namespace <nome>` no topo | Habilita engine TLPP moderna |
| **Caller** em arquivo `.tlpp` | ADVPL clássico (`.prw`) não suporta named args na chamada |
| **Callee** pode ser `.tlpp` OU `.prw` | Sem restrição de fronteira: TLPP → ADVPL funciona |
| AppServer **20.3.2.0+** | Mínimo para funções/métodos com named args |
| AppServer **24.3.1.0+** | Mínimo para `Classe():New()` com named args |

Faltar caller `.tlpp` ou build antiga → erro críptico de sintaxe.

## Sintaxe

### Definição (assinatura inalterada)

A assinatura é **idêntica** a uma definição posicional. Não há marcação especial:

```tlpp
#include "tlpp-core.th"
namespace exemplo

function xParams(p1, p2, p3, p4, p5, p6, p7, p8)
return .T.
```

### Chamada nomeada

Operador `=` na invocação:

```tlpp
// Ordem livre — p2 vem antes de p1, p6 sem os intermediários
xParams(p2=b, p1=a, p6=f)
```

### Mistura posicional + nomeada (permitida)

**Posicionais primeiro, nomeados depois**:

```tlpp
xParams(a, b, p7=g, p8=h)
//      ^^^ posicionais (p1, p2 implícitos)
//            ^^^^^^^^^^^ nomeados
```

Inverter a ordem (nomeado antes de posicional) é erro de sintaxe:

```tlpp
xParams(p1=a, b, c)   // ERRADO — posicional não pode vir depois de nomeado
```

### Omissão seletiva

Params não passados ficam `Nil` (ou default da assinatura, se houver):

```tlpp
function processOrder(cNumero, nValor := 0.00, lEmite := .T., dEmissao)
return

processOrder(cNumero="001", lEmite=.F.)
// nValor fica 0.00 (default da assinatura)
// dEmissao fica Nil
```

## Regra de ouro

**Chave usada na chamada deve casar exatamente com o nome formal da assinatura.** O compilador valida o nome do parâmetro formal — typo ou case errado causa erro de compilação (mesma rigidez da checagem de tipo).

Manter paridade nome local da chamada = nome formal da função sempre que possível:

```tlpp
// Bom: paridade
Local cNumero := "001"
processOrder(cNumero=cNumero)

// Funciona mas ofusca a intenção
Local cMeuPedido := "001"
processOrder(cNumero=cMeuPedido)
```

## Exemplo prático — função de validação

Função única substitui várias validadoras especializadas. Caller paga só pelos params que precisa.

### Definição

```tlpp
#include "tlpp-core.th"
namespace custom.api.validacao

Function U_ValidaParams(dataInicial, dataFinal, dataRef)
    Local oJRet := JsonObject():New()
    // ... valida só os params não-vazios
    // ... cross-check de range quando ambos Ini+Fim presentes
Return oJRet
```

### Caller 1 — intervalo

```tlpp
oJVal := U_ValidaParams(dataInicial=cIni, dataFinal=cFim)
```

### Caller 2 — data única

```tlpp
oJVal := U_ValidaParams(dataRef=cCorte)
```

### Caller 3 — mistura

```tlpp
oJVal := U_ValidaParams(dataInicial=cIni, dataRef=cCorte)
```

Adicionar `cMoeda` à assinatura no futuro **não quebra** nenhum dos callers acima — eles continuam funcionando ignorando o novo param.

## Classe `New()` com named args (AppServer 24.3.1.0+)

```tlpp
namespace custom.mvc.customer

class Customer
    public data cCodigo  as Character
    public data cNome    as Character
    public data lAtivo   as Logical
    method New(cCodigo, cNome, lAtivo) constructor
endclass

method New(cCodigo, cNome, lAtivo) class Customer
    self:cCodigo := cCodigo
    self:cNome   := cNome
    self:lAtivo  := lAtivo
endmethod

// Caller — exige AppServer 24.3.1.0+
local oCli := Customer():New(cCodigo="000001", cNome="ACME", lAtivo=.T.)
```

Em build anterior, named args em `New()` não compila — use posicional.

## Comparativo: Posicional vs Nomeado

| Característica | Posicional (legacy) | Nomeado (TLPP) |
|----------------|---------------------|----------------|
| Rigor de ordem | Obrigatório seguir assinatura | Livre (ou misto) |
| Params opcionais | `,,nil,` placeholders | Omissão direta |
| Legibilidade | Baixa (ruído sintático) | Alta (autodocumentado) |
| Refactor (add param opcional) | Quebra ordem de callers se inserido no meio | Imune se inserido no final |
| Detecção de typo | Posição errada compila e roda | Nome errado falha cedo |

## Caso clássico — adicionar param sem quebrar callers

### Antes

```tlpp
function gerarRelatorio(cCliente, dInicio, dFim)
    // ...
return

// 30 callers espalhados
gerarRelatorio("ACME", dIni, dFim)
gerarRelatorio("CONTOSO", dIni, dFim)
```

### Adicionar `cMoeda` opcional

```tlpp
function gerarRelatorio(cCliente, dInicio, dFim, cMoeda := "01")
    // ...
return
```

Chamadas posicionais antigas: ainda funcionam (`cMoeda` fica Nil → default "01"). OK.

Novas chamadas com named args ficam explícitas:

```tlpp
gerarRelatorio(cCliente="ACME", dInicio=dIni, dFim=dFim, cMoeda="02")
```

## Gotchas

- **Operador errado**: `:=` (atribuição) e `:` (send-message) não funcionam — usar `=`.
- **Caller em `.prw`**: ADVPL clássico não suporta. Caller TEM que estar em `.tlpp`.
- **Build antiga**: AppServer < 20.3.2.0 não reconhece. Sintoma: erro "expected expression" ou compile fail silencioso. Para classes, exige < 24.3.1.0.
- **Mistura inversa**: nomeado seguido de posicional é erro de sintaxe. Sempre posicional → nomeado.
- **Nome errado do param**: compilador valida nome formal — typo causa erro de compilação igual a um tipo errado.
- **`User Function` vs `Function`**: ambos suportam named args na chamada quando definidos em `.tlpp`. Endpoints REST (`@Get`/`@Post`) seguem mesma regra.
- **Tipagem checada**: se a assinatura tem `as Numeric`, o named arg é validado contra o tipo na build (não bypassa tipagem).

## Anti-padrões a evitar

```tlpp
// RUIM — placeholders posicionais em código TLPP novo
processOrder("001", , "ACME", , .T.)

// BOM — named
processOrder(cNumero="001", cCliente="ACME", lEmite=.T.)

// RUIM — operador errado
processOrder(cNumero:="001")          // erro
processOrder(cNumero:"001")           // erro

// BOM
processOrder(cNumero="001")

// RUIM — nome local divergente sem razão
Local cFoo := "001"
processOrder(cNumero=cFoo)

// BOM — paridade
Local cNumero := "001"
processOrder(cNumero=cNumero)
```

## Integração com REST tlppCore

Endpoints `@Get`/`@Post` podem chamar funções com named args:

```tlpp
@Get(endpoint="/foo")
User Function FooEndpoint()
    Local oJVal := U_ValidaParams( ;
        dataInicial = oRest:getQueryRequest()['datainicial'], ;
        dataFinal   = oRest:getQueryRequest()['datafinal']    ;
    )
    // ...
Return .T.
```

Nota sobre continuação de linha: usar `;` no final de cada linha quando quebrar uma chamada longa em múltiplas linhas — vale para named args igual a posicional.

## Diretrizes para refactor

1. **Prioridade**: ao converter `Static Function` legada para TLPP moderno, migre chamadas posicionais → nomeadas como passo mandatório.
2. **Validar assinatura**: antes de cada chamada, conferir nome exato dos params formais (typo silencioso = bug em runtime).
3. **Manter paridade**: nome da var local = nome do param formal sempre que possível.
4. **Proibir placeholders**: code review deve rejeitar `,,nil,` em fontes TLPP novos.
5. **Funções de validação/config**: sempre projetar com params opcionais nomeados (1 função substitui N especializadas).
6. **Validar build do cliente**: confirmar AppServer 20.3.2.0+ antes de adotar amplamente; 24.3.1.0+ se for usar em `New()`.

## Cross-references

- [[advpl-tlpp]] — skill base TLPP (namespaces, classes, annotations, tipagem opcional na assinatura).
- [[advpl-fundamentals]] — limite de 10 chars em ADVPL clássico (fronteira de chamada).
- [[advpl-webservice]] — REST tlppCore (`@Get`/`@Post`) consumindo funções com named args.
- [[advpl-refactoring]] — refactor `Static Function` legada → TLPP moderno.

## Comandos plugadvpl relacionados

- `/plugadvpl:grep "[a-zA-Z_]+=[^=]" --type tlpp` — heurística pra localizar chamadas com named args.
- `/plugadvpl:lint <arq.tlpp>` — sinaliza `,,nil,` placeholders em código TLPP novo.
- `/plugadvpl:find function <nome>` — confere assinatura formal antes de chamar com `=`.

## Sources

- **Fonte oficial primária** — [Parâmetros Nomeados em TLPP — Hugo Guilherme Gomes / TOTVS Developers (Medium)](https://medium.com/totvsdevelopers/par%C3%A2metros-nomeados-em-tlpp-ec2211bfe346) — operador `=`, versões 20.3.2.0 / 24.3.1.0, regras de mistura confirmadas aqui.
- [TLPP - Recursos de Linguagem — TDN TOTVS](https://tdn.totvs.com/display/tec/TLPP+-+Recursos+de+Linguagem)
- [Suporte a TLPP no Protheus — TDN TOTVS](https://tdn.totvs.com/display/public/framework/Suporte+a+TLPP+no+Protheus)
- [Linguagem TLPP ou TL++ — TOTVS Central](https://centraldeatendimento.totvs.com/hc/pt-br/articles/28424631692055)
