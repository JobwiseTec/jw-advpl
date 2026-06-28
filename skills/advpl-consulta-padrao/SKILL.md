---
description: Use ao criar um F3/consulta padrão CUSTOM num campo Protheus (ADVPL/TLPP) — sobretudo a "consulta específica" (SXB que CHAMA UMA FUNÇÃO, em vez de browsear tabela por índice) e o padrão de F3 GENÉRICO reusável: uma SXB única + dispatcher que usa ReadVar() pra descobrir o campo em foco e rotear pro picker certo (ex. FWMBrowse sobre query/temp). Acione sempre que o usuário quer um lookup que abre um diálogo/grid próprio, precisa que o F3 chame uma rotina/User Function, tem vários campos com o mesmo tipo de F3, ou pergunta sobre os registros XB_TIPO (1 cabeçalho / 2 função / 5 retorno), o contrato da função (retorna LÓGICO e grava o valor via memvar ou static de retorno), amarração via X3_F3, criação idempotente do dicionário, ou ConPad1() pra abrir a SXB por código. Acione também ao DIAGNOSTICAR: "F3 não abre", "o valor do F3 não volta pro campo", "Alterar abre o lookup" (anti-padrão MVC_VIEW_LOOKUP), ou confusão entre F3 e MODEL_FIELD_VALID (que só dispara on-change, não abre picker). Gatilhos típicos: "F3 custom", "consulta específica", "lookup que chama função", "F3 genérico pra vários campos", "abrir picker no campo". Para o schema cru da SXB (colunas XB_*) ou um F3 SIMPLES de browse por índice, use advpl-dicionario-sx.
---

# advpl-consulta-padrao — Consulta padrão (F3 / SXB) que chama função, e o F3 genérico

Consulta padrão é o **F3** (lupa) de um campo. O campo aponta pra um `XB_ALIAS` da
**SXB** via `X3_F3`. Há dois sabores:

- **Pesquisa** (browse): a SXB navega uma tabela por índice e devolve uma coluna.
- **Específica** (função): a SXB **executa uma função ADVPL/TLPP**, que abre o que quiser
  (um `FWMBrowse` sobre query, um diálogo, qualquer UI) e devolve o valor pro campo.

A **específica** é o que você quer quando o dado **não é browseável por índice** — ex.: o
código vem de `SUBSTR(RCC_CONTEU,1,3)` de uma tabela genérica, ou de um `UNION` de várias
queries. Browse por índice não resolve; função resolve. Veja o schema completo da SXB em
`[[advpl-dicionario-sx]]`.

## Estrutura da SXB específica — registros por `XB_TIPO`

Uma consulta específica é **mais de um registro** na SXB, mesmo `XB_ALIAS`, distintos por
`XB_TIPO`:

| `XB_TIPO` | Papel | `XB_CONTEM` |
|-----------|-------|-------------|
| `"1"` | Cabeçalho/descrição da consulta | alias base (ex. `"RCC"`) |
| `"2"` | **Função** que executa a consulta (retorna **lógico**) | `"U_MinhaF3Get()"` |
| `"5"` | **Retorno** — expressão/variável com o valor selecionado | `"U_MinhaF3Set()"` ou `"M->CAMPO"` |
| `"6"` | Extras (legendas etc.), opcional | — |

> ⚠️ Criar **só** o registro `XB_TIPO="1"` com a função em `XB_CONTEM` **não funciona** — a
> função precisa estar no `XB_TIPO="2"`, e o valor volta pelo `XB_TIPO="5"`.

> ⚠️ Nomes de coluna variam por release: clássico é `XB_DESCRI`; builds novas têm
> `XB_DESCR`/`XB_DESCRSPA`/`XB_DESCRENG` (3 idiomas). Rode e ajuste se acusar campo inexistente.

## Contrato da função (a parte que mais confunde)

A função do `XB_TIPO="2"` **deve retornar lógico** (`.T.`=confirmou / `.F.`=cancelou) — **não**
o valor. O valor chega ao campo de uma destas formas:

1. **Variável de retorno** (`XB_TIPO="5"`): a função guarda o selecionado numa `Static` do
   fonte; o registro tipo 5 chama uma função que devolve essa static. Padrão **Get/Set**.
2. **Atribuição direta** ao memvar do campo dentro da função: `&(ReadVar()) := cValor`.

O padrão **Get/Set** é o mais limpo e o que melhor casa com o F3 genérico:

```advpl
Static xRetVal := ""

// XB_TIPO="2": abre o picker, guarda o valor, retorna LÓGICO
User Function MinhaF3Get()
    Local lOk := .F.
    // ... abre picker, se confirmou: xRetVal := <codigo>, lOk := .T. ...
Return lOk

// XB_TIPO="5": devolve o valor guardado pro campo
User Function MinhaF3Set()
Return xRetVal
```

## F3 GENÉRICO — uma SXB pra muitos campos (o padrão reusável)

Em vez de uma SXB por campo, faça **uma SXB única** (`"RHF3GEN"`) cujo `XB_TIPO="2"` chama um
**dispatcher genérico**. O dispatcher descobre **qual campo** disparou o F3 via `ReadVar()` e
roteia pro picker certo. Campo novo = **+1 `Case`**, sem tocar na SXB nem no dicionário (além
de setar o `X3_F3` do campo novo).

```advpl
Static xRetVal := ""

// XB_TIPO="2": dispatcher. ReadVar() = campo em foco ("M->PAU_FORPER").
User Function U_F3Get()
    Local cVar   := AllTrim(ReadVar())
    Local cCampo := IIf("->" $ cVar, SubStr(cVar, At("->", cVar) + 2), cVar)
    Local lOk    := .F.
    Local oRet

    Do Case
    Case cCampo == "PAU_FORPER"
        oRet := custom.rh.planosaude.u_F3ForPerm()   // picker no fonte DONO do campo
    // Case cCampo == "OUTRO_CAMPO" -> outra função picker
    EndCase

    If ValType(oRet) == "J" .And. oRet["lRetorno"]
        xRetVal := oRet["xRetorno"]
        lOk     := .T.
    EndIf
Return lOk

// XB_TIPO="5": entrega o valor selecionado ao campo
User Function U_F3Set()
Return xRetVal
```

**Por que `ReadVar()`:** numa consulta padrão, `ReadVar()` devolve o nome da variável do GET
em foco (ex. `"M->PAU_FORPER"`), tanto no clássico quanto no MVC. É o que permite o dispatcher
ser genérico — ele não precisa saber de antemão o campo.

**Onde mora cada coisa:** o **dispatcher** (`U_F3Get`/`U_F3Set`) fica num util compartilhado;
cada **picker** (`u_F3ForPerm`) fica no **fonte dono do campo**, monta sua query e abre a UI.
Assim o util não acopla com tabelas de cada tela.

### Picker reusável — FWMBrowse sobre query/temp

O picker em si costuma ser um `FWMBrowse` modal sobre uma tabela temporária montada de uma
query (filtro + `SetSeek`). Esse browse-sobre-temp tem regras próprias (índice por campo,
`SetFieldFilter`, `nOrder = FieldPos`) — veja `[[advpl-mvc-tlpp]]` (seção "Browse sobre tabela
temporária") e `[[advpl-ui-patterns]]`. O picker devolve o código escolhido; o dispatcher
guarda na static; o tipo 5 entrega ao campo.

## Amarração no campo — `X3_F3`

`X3_F3 = "RHF3GEN"` no SX3 do campo. `X3_F3` **não é bitmap** (diferente de `X3_USADO`/
`X3_OBRIGAT`) → escrita direta via `RecLock` é aceitável; depois `X3CleanCache(cCampo)` pra
invalidar o cache. Criação **idempotente** (rode 1×/ambiente, fica versionada no fonte):

```advpl
// SXB: cria os registros (tipo 1 + 2 + 5) se faltarem
DbSelectArea("SXB")
SXB->(DbSetOrder(1))                                  // XB_FILIAL+XB_ALIAS+XB_TIPO+XB_SEQ+XB_COLUNA
If ! SXB->(DbSeek(xFilial("SXB") + "RHF3GEN"))
    // ... RecLock + grava 3 registros, variando XB_TIPO "1"/"2"/"5" ...
EndIf

// X3_F3 do campo (não-bitmap: direto OK)
DbSelectArea("SX3")
SX3->(DbSetOrder(2))                                  // X3_CAMPO
If SX3->(DbSeek("PAU_FORPER")) .And. AllTrim(SX3->X3_F3) != "RHF3GEN"
    RecLock("SX3", .F.)
    SX3->X3_F3 := "RHF3GEN"
    SX3->(MsUnlock())
EndIf
X3CleanCache("PAU_FORPER")
```

Prefira gerar isso como **script de atualização de dicionário** (`/advpl-specialist:sxgen` ou
`PutSx3`/`RecLock`), nunca dentro da rotina do cadastro — dicionário cria **uma vez** e
persiste; não recria a cada execução. Veja `[[advpl-dicionario-sx]]`.

## Abrir a SXB por código — `ConPad1()`

Dá pra disparar a consulta sem F3 (de um botão, VALID, etc.):

```advpl
// ConPad1(cAliasSXB, , lVisual, , , , aRetCampos) -> resultado confirmado em aCpoRet
ConPad1("RHF3GEN", , .F.)
// valores selecionados ficam em aCpoRet (Private criado pela ConPad1)
```

## Pegadinhas (todas observadas em runtime)

- **NÃO use `MVC_VIEW_LOOKUP` pra abrir um diálogo F3 custom.** Ele registra um `SetKey`/
  `FWLOOKUP` que **sequestra a ação do browse** — sintoma clássico: o botão **Alterar** abre o
  lookup em vez da tela de edição. F3 custom é via `X3_F3`/SXB (este skill).
- **`MODEL_FIELD_VALID` só dispara quando o valor MUDA** (digitou e saiu). Ele **não** abre
  picker ao clicar/entrar no campo — serve pra **validar** o código (digitado ou devolvido pelo
  F3) e preencher campos companheiros (ex. o nome). O picker é o F3/SXB.
- **Função tipo 2 retornando o valor em vez de lógico** → a consulta não fecha/retorna direito.
  Retorne `.T./.F.`; entregue o valor pelo tipo 5 (ou `&(ReadVar())`).
- **SXB só com tipo 1** → não executa a função. Precisa do tipo 2 (função) + tipo 5 (retorno).
- **Criar a SXB dentro da rotina** (RecLock a cada run) → é dado de dicionário; crie 1× via
  script idempotente.

## Fluxo completo (resumo)

```
F3 no campo  ->  X3_F3="RHF3GEN"  ->  SXB tipo2: U_F3Get()
   U_F3Get: ReadVar() -> Do Case -> picker do fonte (FWMBrowse/query) -> static xRetVal, return .T.
SXB tipo5: U_F3Set() -> xRetVal -> cai no campo
   (opcional) MODEL_FIELD_VALID do campo valida o código e preenche o nome companheiro
```

## Exemplos práticos (fontes reais)

Em [`exemplos/`](exemplos/) — uma tela MVC TLPP de produção (cadastro PAU) que usa o F3
genérico ponta-a-ponta. Os nomes reais do projeto usam o sufixo `RH` no dispatcher
(`U_F3RHGet`/`U_F3RHSet`) — mapeie pros papéis SXB:

**`exemplos/RhUtil.tlpp`** — o util compartilhado (namespace `custom.rh.beneficio.util`):
- `U_F3RHGet()` (registro **`XB_TIPO="2"`**): o dispatcher. `ReadVar()` → `Do Case` no campo →
  chama o picker do fonte dono (`custom.rh.planosaude.u_F3ForPerm(@xRetVal)`); guarda o
  selecionado na `Static xRetVal`; **retorna lógico**.
- `U_F3RHSet()` (registro **`XB_TIPO="5"`**): `Return xRetVal` — entrega o valor ao campo.
- `U_F3Custom()` + `fMontaTela`/`fLoadDados`/`fCriaCols`/`fGravaRet`: o **picker reusável** —
  `FWDialogModal` + `FWMBrowse` sobre temp (query→`DbStruct`→temp, 1 índice por campo,
  `SetFieldFilter`/`SetSeek`). Devolve `JsonObject` com os campos pedidos.

**`exemplos/CadPlanoSaudeOdonto.tlpp`** — a tela MVC dona do campo (`custom.rh.planosaude`):
- `U_F3ForPerm()`: o **picker específico** do `PAU_FORPER` — monta a query (RCC S018), chama
  `U_F3Custom`, devolve `{lRetorno, xRetorno}` pro dispatcher.
- `U_ModelDef`: `SetProperty("PAU_FORPER", MODEL_FIELD_VALID, {|oMdl| ...u_xConsForPerm(oMdl)})`
  — o VALID **valida** o código (vindo do F3 ou digitado) e preenche o nome companheiro
  `PAU_XNMFPE`; **não** abre picker. O virtual `PAU_XNMFPE` é semeado por `STRUCT_FEATURE_INIPAD`.
- `U_xConsForPerm`: a validação on-change (query por código → `LoadValue` do nome).
- `fSeekFiltro`/`fCriaTempPlanos`/`U_CadPlanoSaude`: o **browse principal** também é sobre temp,
  com o mesmo filtro+`SetSeek` (índice por campo, `nOrder = FieldPos`).

> Falta nos exemplos o script de dicionário (SXB `RHF3GEN` tipo 1/2/5 + `X3_F3='RHF3GEN'` no
> `PAU_FORPER`): gere via `/advpl-specialist:sxgen` e rode 1×/ambiente (ver seção "Amarração").
> Obs.: os `.tlpp` do exemplo estão em latin-1 (cp1252), como é comum em projetos legados.

## Cross-references

- `[[advpl-dicionario-sx]]` — schema da SXB (XB_*), X3_F3, X3CleanCache, PutSx3.
- `[[advpl-mvc-tlpp]]` — campo MVC: `MODEL_FIELD_VALID` vs `MVC_VIEW_LOOKUP` (anti-padrão),
  browse sobre temp (filtro/`SetSeek`), `oModel:GetModel("COMPONENTE")`.
- `[[advpl-ui-patterns]]` — `FWMBrowse`/`FWDialogModal` do picker.
- `[[advpl-fundamentals]]` — `ReadVar`, `Static`, naming `U_`.

## Comandos plugadvpl relacionados

- `/advpl-specialist:sxgen` (ou `PutSx3`) — gera o script de dicionário (SXB + X3_F3).
- `/plugadvpl:find function ConPad1` — exemplos de abertura de consulta padrão.
- `/plugadvpl:impacto <campo>` — cruza X3_F3 ↔ SXB ↔ fontes.

## Sources

- [BlackTDN — Consulta específica usando o dicionário SXB](https://www.blacktdn.com.br/2011/10/protheus-advpl-dicas-do-robson-como.html) (retorno lógico + atribui ao campo na rotina)
- [Terminal de Informação — Função para criar consulta (F3 - SXB) via AdvPL](https://terminaldeinformacao.com/2018/08/07/funcao-para-criar-uma-consulta-f3-sxb-advpl/) (registros XB_TIPO 1/2/5)
- [Terminal de Informação — Abrindo consulta padrão SXB com ConPad1 (Maratona 089)](https://terminaldeinformacao.com/2023/11/05/abrindo-uma-consulta-padrao-da-sxb-usando-a-funcao-conpad1-maratona-advpl-e-tl-089/)
- [ProtheusAdvpl — Chamar tela de consulta padrão (SXB) com ConPad1](https://protheusadvpl.com.br/como-chamar-uma-tela-de-consulta-padraosxb-com-a-funcao-conpad1/)
