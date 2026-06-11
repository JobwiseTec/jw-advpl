---
description: Use ao criar/editar rotina MVC (browse, ModelDef/ViewDef/MenuDef, cadastro com inclusão) em fonte .tlpp com namespace, migrar MVC de .prw pra .tlpp, ou diagnosticar "browse abre mas Incluir/Visualizar não respondem" / "menu sem opções" em TLPP. Cobre a resolução por namespace (FWLoadModel/ACTION/SetMenuDef recebem namespace.funçãoPrincipal), regras do U_, pré-requisito release 12.1.2410 + LIB 20240520, FWLoadBrw/BrowseDef e FWMVCRotAuto sem StaticCall. Para MVC em .prw clássico use advpl-mvc.
---

# advpl-mvc-tlpp — MVC do Protheus em TLPP (namespace)

Em `.tlpp` o framework MVC **muda o mecanismo de resolução**: o MVC clássico localiza `MenuDef`/`ModelDef`/`ViewDef` como `Static Function` pelo **nome do fonte** via `StaticCall` — e a `StaticCall` é **inibida em TLPP**. No TLPP, essas funções viram **funções globais** dentro do `namespace`, declaradas como **`Function U_Nome()`** (convenção desta casa — `U_` explícito no nome; `User Function Nome()` também resolve, é o mesmo símbolo), e tudo que o framework recebe passa a ser **`namespace.funçãoPrincipal`** (a função do browse), nunca o nome do arquivo.

> **Convenção da casa:** a tríade e a função de entrada usam `Function U_Nome()` (com `U_` literal). É equivalente a `User Function Nome()` — escolha foi padronizar o `U_` explícito. **Não misture as duas grafias** no mesmo projeto.

> O miolo do MVC (MPFormModel, AddFields/AddGrid, SetRelation, FWModelEvent, FWFormView) **não muda** — veja `[[advpl-mvc]]`. O que muda é a **casca de resolução**: declaração das *Def e as strings passadas ao framework.

## Pré-requisitos (cheque ANTES de escrever)

| Requisito | Mínimo | Se não atender |
|---|---|---|
| Release Protheus | **12.1.2410** (parcial na LIB 20240520) | MVC em `.tlpp` **não funciona** — orientação oficial TOTVS: mantenha o fonte em `.prw` |
| LIB (framework) | **20240520**+ | idem |
| Includes | FWMVCDEF.CH / tlpp-core.th **atualizados** da LIB nova | erros de compilação/resolução |
| Encoding do fonte | `.tlpp` = **UTF-8** | mojibake em acentos (veja `[[advpl-encoding]]`) |

Sintoma clássico de ambiente antigo (documentado pela TOTVS): **browse abre, mas o menu fica sem opções / Incluir não responde** — e o mesmo fonte renomeado pra `.prw` funciona.

## O que muda de .prw pra .tlpp

| Aspecto | `.prw` clássico | `.tlpp` com namespace |
|---|---|---|
| `MenuDef`/`ModelDef`/`ViewDef` | `Static Function` | **`Function U_Nome()`** dentro do `namespace` (convenção da casa; `User Function` também resolve) |
| `FWLoadModel(...)` | `"NOMEFONTE"` | `"namespace.funçãoPrincipal"` |
| ACTION do aRotina | `"VIEWDEF.NOMEFONTE"` | `"ViewDef.namespace.funçãoPrincipal"` |
| `oBrowse:SetMenuDef(...)` | `"NOMEFONTE"` | `"namespace.funçãoPrincipal"` (validado em produção; sem doc oficial) |
| Gerar aRotina | `FWMVCMenu("FONTE")` | **manual com `ADD OPTION`** (FWMVCMenu não tem suporte documentado com namespace) |
| Reuso entre fontes | `StaticCall(FONTE, ModelDef)` | `namespace.u_ModelDef()` direto (StaticCall é inibida) |
| PE via ExecBlock | `ExistBlock("U_MEUPE")` | `ExistBlock("namespace.meupe")` — **sem** `U_` |

## Esqueleto canônico — cadastro com inclusão

```advpl
#include "TOTVS.CH"
#include "FWMVCDef.CH"
#include "tlpp-core.th"

namespace custom.exemplo.zx1

/*/{Protheus.doc} U_zx1Cad
Cadastro ZX1 — browse + CRUD completo em TLPP.
/*/
Function U_zx1Cad()
    Local oBrowse := FWMBrowse():New()

    oBrowse:SetAlias("ZX1")
    oBrowse:SetDescription("Cadastro ZX1")
    // namespace + função PRINCIPAL (esta função), SEM o U_ — NÃO o nome do arquivo
    oBrowse:SetMenuDef("custom.exemplo.zx1.zx1Cad")
    oBrowse:Activate()
Return Nil

Function U_MenuDef() as array
    Local aRotina := {} as array
    // FWMVCMenu("FONTE") não tem suporte documentado com namespace — monte manual:
    ADD OPTION aRotina TITLE "Visualizar" ACTION "ViewDef.custom.exemplo.zx1.zx1Cad" OPERATION MODEL_OPERATION_VIEW   ACCESS 0
    ADD OPTION aRotina TITLE "Incluir"    ACTION "ViewDef.custom.exemplo.zx1.zx1Cad" OPERATION MODEL_OPERATION_INSERT ACCESS 0
    ADD OPTION aRotina TITLE "Alterar"    ACTION "ViewDef.custom.exemplo.zx1.zx1Cad" OPERATION MODEL_OPERATION_UPDATE ACCESS 0
    ADD OPTION aRotina TITLE "Excluir"    ACTION "ViewDef.custom.exemplo.zx1.zx1Cad" OPERATION MODEL_OPERATION_DELETE ACCESS 0
Return aRotina

Function U_ModelDef()
    Local oModel  := MPFormModel():New("ZX1CADMD")
    Local oStrZX1 := FWFormStruct(1, "ZX1")

    oModel:AddFields("ZX1MASTER", /*cOwner*/, oStrZX1)
    oModel:SetPrimaryKey({"ZX1_FILIAL", "ZX1_COD"})   // NUNCA {} em cadastro com inclusão
    oModel:SetDescription("Cadastro ZX1")
Return oModel

Function U_ViewDef()
    Local oModel  := FWLoadModel("custom.exemplo.zx1.zx1Cad")  // namespace + função principal (sem U_)
    Local oView   := FWFormView():New()
    Local oStrZX1 := FWFormStruct(2, "ZX1")

    oView:SetModel(oModel)
    oView:AddField("VIEW_ZX1", oStrZX1, "ZX1MASTER")
    oView:CreateHorizontalBox("PRINCIPAL", 100)
    oView:SetOwnerView("VIEW_ZX1", "PRINCIPAL")
Return oView
```

> **Importante:** o nome é declarado com `U_` (`Function U_zx1Cad`), mas as **strings do framework** (`SetMenuDef`/`FWLoadModel`/`ACTION`) usam o nome **SEM `U_`** (`...zx1Cad`). O resolver casa `zx1Cad` com a função `U_zx1Cad`.

Master-detail (cabeçalho + grid), campo virtual, `SetUniqueLine`, validação de linha etc.: **idêntico ao ADVPL** — copie o miolo de `[[advpl-mvc]]` e troque só a casca acima. Exemplo completo em [`exemplos/custom.exemplo.zx1cad.tlpp`](exemplos/custom.exemplo.zx1cad.tlpp).

## Regras do `U_` (a parte que mais confunde)

Declare tudo como **`Function U_Nome()`** (convenção da casa). Aí valem 4 regras de chamada:

| Quem chama | Forma | Exemplo |
|---|---|---|
| **Framework** (*Def, ACTION ViewDef, FWLoadModel, SetMenuDef) | namespace + nome **sem** `U_` | `FWLoadModel("custom.x.zx1Cad")` |
| **Seu código, mesmo fonte** | nome direto, sem prefixo | `aRotina := U_MenuDef()` |
| **Seu código, outro fonte** (ou ACTION de opção custom) | namespace + **`u_`** + nome + `()` | `ACTION "custom.x.u_aprovar()"` |
| **PE via ExistBlock/ExecBlock** | namespace + nome **sem** `U_` | `ExistBlock("custom.x.meupe")` |

> A casa padroniza **`Function U_Nome()`** — deixa o `U_` explícito no nome. `User Function Nome()` é equivalente (o compilador gera o mesmo `U_NOME`) e é a forma da doc oficial TOTVS; ambas resolvem. O que **não** pode é misturar as duas grafias no mesmo projeto.

## Variantes que funcionam (validadas em produção/tutoriais)

**1. Bootstrap explícito do aRotina** — útil como cinto de segurança em LIBs mais antigas que o suporte pleno (os tutoriais funcionais da comunidade usam; em ambientes 12.1.2410+ o `SetMenuDef` com namespace dispensa):

```advpl
Function U_zx1Cad()
    Local oBrowse
    Private aRotina := custom.exemplo.zx1.u_MenuDef()  // explícito, com u_
    SetFunName("zx1Cad")
    oBrowse := FWMBrowse():New()
    ...
```

**2. `FWLoadBrw` + `BrowseDef`** — padrão mais novo; o framework monta o browse e resolve tudo sozinho:

```advpl
Function U_zx1Cad()
Return FWLoadBrw("custom.exemplo.zx1.zx1Cad")

Function U_BrowseDef() as object
    Local oBrowse := FWMBrowse():New() as object
    oBrowse:SetAlias("ZX1")
    oBrowse:SetDescription("Cadastro ZX1")
Return oBrowse
```

## FWMVCRotAuto / reuso headless (sem StaticCall)

```advpl
// .prw clássico (NÃO funciona em .tlpp):
//   Private aRotina := StaticCall(XYZCAD, MenuDef)
// .tlpp:
Private aRotina     := custom.exemplo.zx1.u_MenuDef()
Private lMsErroAuto := .F.
Local   oModel      := custom.exemplo.zx1.u_ModelDef()

FWMVCRotAuto(oModel, "ZX1", MODEL_OPERATION_INSERT, {{"ZX1MASTER", aDados}})
```

## Diagnóstico — browse abre, Incluir/Visualizar não

1. **Release ≥ 12.1.2410 e LIB ≥ 20240520?** Não → reescreva em `.prw` (orientação oficial).
2. **Includes atualizados** (FWMVCDEF.CH/tlpp-core.th da LIB nova)?
3. As *Def são **funções globais no namespace** (`Function U_Nome()`, **não** `Static Function`)? (`Static Function` = causa nº 1 — StaticCall inibida)
4. ACTION/`FWLoadModel`/`SetMenuDef` usam **`namespace.funçãoPrincipal`** (sem `U_`) e o nome confere com a função que existe?
5. Usou `FWMVCMenu("FONTE")`? Troque por aRotina manual com `ADD OPTION`.
6. Persiste? Adicione o bootstrap explícito (variante 1) e teste de novo.

## Anti-padrões

- **`Static Function ModelDef/ViewDef/MenuDef` em `.tlpp`** → o framework não alcança (StaticCall inibida). É exatamente o esqueleto `.prw` da `[[advpl-mvc]]` — não copie a casca de lá.
- **`SetMenuDef("NOMEFONTE")` / `FWLoadModel("NOMEFONTE")`** → em TLPP o eixo é o namespace, não o arquivo.
- **`FWMVCMenu("FONTE")`** → sem suporte documentado com namespace; monte o aRotina manual.
- **`oModel:SetPrimaryKey({})`** em cadastro com inclusão → informe a chave real (em monitor view-only passa despercebido).
- **`StaticCall(...)` em `.tlpp`** → inibida; chame `namespace.u_Funcao()` direto.
- **Misturar grafias** (`Function U_Nome` + `User Function Nome` no mesmo projeto) → ambas resolvem, mas padronize `Function U_Nome()` (convenção da casa).
- **`U_` na string do framework** (`FWLoadModel("custom.x.u_zx1Cad")`) → a string qualificada vai **sem** `U_` (`...zx1Cad`); o `u_` só aparece em chamada explícita de outro fonte.
- **`.tlpp` em cp1252** → TLPP é UTF-8 (`[[advpl-encoding]]`).

## Referência rápida — qual string vai onde

| Onde | String |
|---|---|
| `FWLoadModel(...)` / `FWLoadView(...)` / `FWLoadMenuDef(...)` | `"custom.ns.funcaoPrincipal"` |
| `ACTION` de View/Insert/Update/Delete | `"ViewDef.custom.ns.funcaoPrincipal"` |
| `ACTION` de opção custom do menu | `"custom.ns.u_minhaAcao()"` |
| `oBrowse:SetMenuDef(...)` | `"custom.ns.funcaoPrincipal"` |
| `FWLoadBrw(...)` | `"custom.ns.funcaoPrincipal"` |
| `ExistBlock`/`ExecBlock` (PE TLPP) | `"custom.ns.nomepe"` (sem `U_`) |
| Chamada explícita no seu código (outro fonte) | `custom.ns.u_Funcao()` |
| **Declaração** das *Def e da função principal | `Function U_Nome()` (convenção da casa) |

## Cross-references

- `[[advpl-mvc]]` — **REQUIRED BACKGROUND**: todo o miolo MVC (model, view, grids, FWModelEvent, FWMVCRotAuto) — aqui só muda a casca.
- `[[advpl-tlpp]]` — namespace, escopos, StaticCall inibida, tipagem `as`.
- `[[advpl-tlpp-named-params]]` — named args (`=`) nas chamadas TLPP.
- `[[advpl-mvc-avancado]]` — PEs `*STRU`/AddTrigger em MVC padrão (os PEs em TLPP seguem a regra do `U_` acima).
- `[[advpl-encoding]]` — `.tlpp` = UTF-8.

## Comandos plugadvpl relacionados

- `/plugadvpl:find function ModelDef` — localiza as *Def indexadas (em `.tlpp` aparecem como `Function U_*`/`User Function`).
- `/plugadvpl:arch <arquivo>` — confere namespace/funções do fonte antes de editar.
- `/plugadvpl:lint <arquivo>` — regras BP/MOD aplicam igual em `.tlpp`.

## Exemplos práticos

Em [`exemplos/`](exemplos/) (escritos do zero, genéricos, UTF-8):

- `custom.exemplo.zx1cad.tlpp` — **CRUD completo com inclusão**: master-detail (ZX1 cabeçalho + ZX2 grid), campo virtual na grid, `SetUniqueLine`, validação de linha, casca TLPP canônica.
- `custom.exemplo.zx9monitor.tlpp` — monitor view-only: FWMBrowse com legendas + filtro, ação custom de menu com `u_...()`.

## Sources

- [TDN — Suporte a TLPP no Protheus](https://tdn.totvs.com/display/public/framework/Suporte+a+TLPP+no+Protheus) (página central: versões LIB 20240520/12.1.2410, *Def deixam de ser estáticas, FWLoadModel/ACTION com namespace, PEs sem U_, includes)
- [TDN — StaticCall inibida em TLPP](https://tdn.totvs.com/display/tec/StaticCall+-+inibida+em+TLPP)
- [Central — MenuDef em arquivo TLPP (KB 360037714554)](https://centraldeatendimento.totvs.com/hc/pt-br/articles/360037714554)
- [Central — É possível criar uma rotina em MVC utilizando TLPP? (KB 27606833750423)](https://centraldeatendimento.totvs.com/hc/pt-br/articles/27606833750423)
- [TDN — Namespace (TLPP)](https://tdn.totvs.com/display/tec/Namespace)
- [Medium TOTVS Developers — TLPP no Protheus](https://medium.com/totvsdevelopers/tlpp-no-protheus-a113296e29b8) (FWLoadBrw/BrowseDef)
- [udesenv — MVC com TLPP](https://udesenv.com.br/post/advpl-mvc-tlpp) · [Terminal de Informação — Criar tela em MVC usando TLPP](https://terminaldeinformacao.com/2025/05/26/criar-tela-em-mvc-usando-tlpp-no-lugar-de-advpl/) (bootstrap aRotina/SetFunName)
- Padrões validados contra fontes TLPP MVC em produção (genéricos; sem identificação).
