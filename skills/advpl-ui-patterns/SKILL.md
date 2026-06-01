---
description: Patterns visuais do Protheus (SmartClient) — browses (FWMarkBrowse/FWBrowse/FWFormBrowse/MsSelect), janelas MsDialog (MsAdvSize pra maximizar, OWNER, fechamento via TTimer), ParamBox por tipo, atalhos SetKey+VK_*, coloração de linha (AddLegend/SetBlkBackColor/bColor), export Excel via FWMSExcel:GetXMLFile (gera .xml, não .xlsx). Use ao construir/editar UI Protheus server-side fora de MVC, escolher tipo de browse, maximizar diálogo, colorir linha, montar ParamBox, registrar atalho de teclado, ou exportar grid pra Excel.
---

# advpl-ui-patterns — Patterns visuais do Protheus (SmartClient)

Catálogo dos patterns de UI server-side do Protheus que não são cobertos pelo
MVC (vide [[advpl-mvc]] para cadastros). Foco em telas ad-hoc: browses
customizados, diálogos, ParamBox, coloração, atalhos e export. Cada método
TOTVS pode **não existir** numa build específica — quando houver alternativa,
ela está anotada (vide a regra de discovery em `check-build` / catálogo
`apis_por_build`).

## Quando usar

- Construir/editar tela interativa fora do MVC (painel, consulta, conferência).
- Escolher entre `FWMarkBrowse`, `FWBrowse`, `FWFormBrowse`, `MsSelect`.
- Maximizar `MsDialog`, controlar fechamento, ou tratar erro de `RestoreArea`.
- Montar `ParamBox` (largura de campo, F3, validação) sem `Pergunte`/SX1.
- Colorir linha de browse por status.
- Registrar atalho de teclado (`SetKey` + `VK_*`).
- Exportar grid pra Excel (`FWMSExcel`).

## 1. Browses — qual classe usar

| Classe | Use quando | Marcação | Gotchas |
|---|---|---|---|
| **`FWMarkBrowse`** | grid com **checkbox de marcação** em massa (seleção múltipla) | nativa (coluna mark) | coloração via `AddLegend`/`SetColorFn`, **não** `SetBlkBackColor` |
| **`FWBrowse`** | grid genérico read-only ad-hoc sobre alias/temporária | não | mais leve; sem MVC. `SetTemporary(.T.)` pode não existir em builds antigas |
| **`FWFormBrowse`** | browse acoplado a um **MVC** (ViewDef) | via model | preferido dentro de MVC; fora dele é overkill |
| **`MsSelect`** | grid simples sobre alias já aberto (legado, ainda útil) | `lMark`/coluna | expõe `:oBrowse` (TCBrowse/TWBrowse) com `SetBlkBackColor` para colorir |

Regra prática: marcação em massa → `FWMarkBrowse`; grid simples sobre query/temp
→ `FWBrowse`; dentro de cadastro MVC → `FWFormBrowse`; legado com `:oBrowse`
exposto → `MsSelect`.

## 2. Janelas — `MsDialog`

### Maximizar — `MsAdvSize`, não `Maximize()`

`MsDialog` **não tem** método `Maximize()` (erro de runtime
`Cannot find method MSDIALOG:MAXIMIZE` na maioria das builds). Para abrir
maximizado/ocupando a área útil, calcule as dimensões com `MsAdvSize()`:

```advpl
Local aSize  := MsAdvSize()            // {esq, sup, dir, inf} da área útil
Local oDlg

DEFINE MSDIALOG oDlg TITLE "Painel" FROM aSize[1], aSize[2] TO aSize[3], aSize[4] PIXEL

    // ... componentes (oDlg como OWNER) ...

ACTIVATE MSDIALOG oDlg CENTERED ON INIT (/* monta browse aqui */)
```

### `OWNER` explícito e fechamento com `End()`

Passe o diálogo como **OWNER** dos componentes e guarde a referência: assim
`oDlg:End()` fecha de forma determinística. `DeActivate()` pode ser
**silencioso** (sem efeito) dependendo do componente — prefira `End()`.

```advpl
@ 10, 10 BUTTON "Fechar" SIZE 040, 013 OF oDlg PIXEL ACTION oDlg:End()
```

### Fechar de DENTRO de um evento — adie com `TTimer`

Chamar `oDlg:End()` (ou trocar de tela) de dentro do `Execute`/bloco de um
componente, enquanto a área de trabalho está em uso, dá erro de `RestoreArea`.
Adie o fechamento pra fora do contexto atual com um `TTimer` de disparo único:

```advpl
Local oTimer
oTimer := TTimer():New(100, {|| oTimer:DeActivate(), oDlg:End() }, oDlg)
oTimer:Activate()
```

## 3. `ParamBox` — perguntas sem SX1/`Pergunte`

`ParamBox()` monta uma janela de parâmetros em runtime (Code Analysis aprova;
SX1+`Pergunte` está deprecated para fluxo novo). Cada item de `aParamBox` é um
array cujo **tipo** (1º elemento) define a estrutura:

| Tipo | Campo | Posições relevantes |
|---|---|---|
| 1 | `Get` (texto/num/data) | `{1, label, default, **pixels(largura)**, valid, F3, ...}` — a **largura visual** é a posição de pixels |
| 2 | `Combo` | `{2, label, default, aOpcoes, larg, valid, ...}` |
| 3 | `Radio` | `{3, label, default, aOpcoes, larg, valid, ...}` |
| 4 | `Checkbox` | `{4, label, default(.T./.F.), ...}` |
| 5 | `Get com F3 (consulta)` | item Get + alias de consulta SXB |
| 6 | `Get numérico com botão` | variante com picture |

```advpl
Local aParamBox := {}
Local aRet      := {}

AAdd(aParamBox, {1, "Cliente De",  Space(6), 50, ".T.", "SA1", ".T.", 50, .F.})
AAdd(aParamBox, {1, "Cliente Ate", Space(6), 50, ".T.", "SA1", ".T.", 50, .F.})
AAdd(aParamBox, {2, "Status", "Todos", {"Todos","Aberto","Fechado"}, 60, ".T.", .F.})

If ParamBox(aParamBox, "Filtros", @aRet)
    // MV_PAR01 = de, MV_PAR02 = ate, MV_PAR03 = status (ou use aRet[n])
EndIf
```

> **Gotcha:** a posição de **pixels** controla a **largura visual** do campo —
> campo "espremido" geralmente é largura mal dimensionada, não bug de dado.

## 4. Atalhos de teclado — `SetKey` + `VK_*`

Registre uma tecla de função pra disparar um codeblock. **Sempre faça cleanup**
ao fechar a tela (restaure o handler anterior) pra não vazar o atalho:

```advpl
Local bF5Ant := SetKey(VK_F5, {|| MeuRefresh() })   // guarda o anterior
// ... tela ativa ...
SetKey(VK_F5, bF5Ant)                                // restaura ao fechar
```

Comuns: `VK_F2`..`VK_F12`, `VK_INSERT`, `VK_DELETE`. O escopo é global enquanto
registrado — daí a importância do cleanup.

## 5. Coloração de linha

| Componente | Como colorir |
|---|---|
| `FWMarkBrowse` | `oBrw:AddLegend(<exp>, <cor>, <legenda>)` ou `oBrw:SetColorFn({|| ... })` |
| `MsSelect` (`:oBrowse` = TCBrowse/TWBrowse) | `oBrw:oBrowse:SetBlkBackColor({|| IIf(<cond>, COR_A, COR_B) })` |
| `FWBrowse` (coluna) | `bColor` no `FWBrwColumn` da coluna |

```advpl
// FWMarkBrowse — legenda + cor por condição (status do registro)
oBrw:AddLegend("STATUS == '2'", "GREEN",  "Conferido")
oBrw:AddLegend("STATUS == '1'", "YELLOW", "Pendente")
oBrw:AddLegend("STATUS == '3'", "RED",    "Divergente")
```

> **Gotcha:** `SetBlkBackColor` **não existe** no `FWMarkBrowse` (erro
> `Cannot find method FWMARKBROWSE:SETBLKBACKCOLOR`). Use `AddLegend`/`SetColorFn`
> nele, ou exponha `MsSelect:oBrowse` se precisar do `SetBlkBackColor`.

## 6. Export para Excel — `FWMSExcel`

`FWMSExcel:GetXMLFile()` gera um arquivo **SpreadsheetML (XML)**, não um `.xlsx`
binário. Salve com extensão **`.xml`** — o Excel abre normalmente. Salvar como
`.xlsx` gera um arquivo "corrompido" (é XML com extensão errada).

```advpl
Local oExcel := FWMSExcel():New()
Local cArq   := "C:\Temp\relatorio.xml"    // .xml, NÃO .xlsx

oExcel:AddWorkSheet("Conferencia")
oExcel:AddTable("Conferencia", "Itens")
oExcel:AddColumn("Conferencia", "Itens", "Documento", 1, 1)
oExcel:AddColumn("Conferencia", "Itens", "Valor",     1, 3)
oExcel:AddRow("Conferencia", "Itens", {"NF 001", 1500.00})

oExcel:Activate()
oExcel:GetXMLFile(cArq)
// abre no client:
FWExecView( ... )  // ou shell para o arquivo gerado
```

> **Gotcha:** extensão `.xlsx` em saída de `GetXMLFile` = arquivo "quebrado".
> Sempre `.xml`.

## Compatibilidade por build

Métodos de `FW*`/`MsDialog`/`FWBrowse` **variam por build/patch** Protheus. Os
casos clássicos (`Maximize`, `SetBlkBackColor` em FWMarkBrowse, `SetTemporary`
em FWBrowse) só aparecem como erro em runtime. Antes de assumir que um método
existe, valide contra a build alvo (vide catálogo `apis_por_build` / comando
`check-build`) e tenha a alternativa em mãos (tabela acima).

## Cross-ref

- [[advpl-fundamentals]] — notação húngara, naming, escopos.
- [[advpl-mvc]] — para cadastros (use `FWFormBrowse`/`ViewDef`, não monte browse na mão).
- [[advpl-embedded-sql]] — alimentar o browse a partir de query/temporária.
