#include "totvs.ch"
#include "fwmvcdef.ch"

/* ============================================================================
   ZEXPEDIDO.prw  -  Exemplo MVC CLASSICO (.prw) - cadastro master-detail

   Contraparte ADVPL classica dos exemplos .tlpp desta pasta. Demonstra a
   triade como Static Function (StaticCall disponivel em .prw), referencias
   pelo NOME DO FONTE ("ZEXPEDIDO") e o miolo master-detail completo:

     ZX1 (capa do pedido)  1--N  ZX2 (itens)

   Cobre: FWMBrowse + legendas, MenuDef via FWMVCMenu + opcao custom,
   ModelDef com AddFields/AddGrid/SetRelation/SetPrimaryKey/SetUniqueLine e
   hook moderno via FWModelEvent (InstallEvent), ViewDef com cabecalho + grid
   em boxes.

   Para a versao .tlpp (namespace + User Function) veja [[advpl-mvc-tlpp]] e os
   demais exemplos .tlpp desta pasta. O MIOLO e o mesmo; muda so a casca.
   ============================================================================ */

// -----------------------------------------------------------------------------
// Funcao de entrada: monta o browse do cadastro.
// -----------------------------------------------------------------------------
User Function ZEXPEDIDO()
    Local oBrowse := FWMBrowse():New()

    oBrowse:SetAlias("ZX1")
    oBrowse:SetDescription("Pedidos (exemplo MVC classico)")
    // .prw: referencia a propria rotina pelo NOME DO FONTE.
    oBrowse:SetMenuDef("ZEXPEDIDO")

    // Legendas por status da capa (ZX1_STATUS).
    oBrowse:AddLegend("ZX1_STATUS == '1'", "YELLOW", "Em digitacao")
    oBrowse:AddLegend("ZX1_STATUS == '2'", "GREEN" , "Aprovado")
    oBrowse:AddLegend("ZX1_STATUS == '3'", "RED"   , "Cancelado")

    oBrowse:Activate()
Return Nil

// -----------------------------------------------------------------------------
// MenuDef: aRotina padrao via FWMVCMenu + uma opcao custom ("Aprovar").
// -----------------------------------------------------------------------------
Static Function MenuDef()
    Local aRotina := FWMVCMenu("ZEXPEDIDO")  // Pesquisar/Visualizar/Incluir/Alterar/Excluir/Imprimir/Copiar
    aAdd(aRotina, {"Aprovar", "U_ZEXAPROV", 0, 4, 0, .F.})  // opera como UPDATE (nOperacao=4)
Return aRotina

// -----------------------------------------------------------------------------
// ModelDef: capa ZX1 (master) + itens ZX2 (grid).
// -----------------------------------------------------------------------------
Static Function ModelDef()
    Local oModel  := MPFormModel():New("ZEXPEDM")        // ID unico do model
    Local oStrZX1 := FWFormStruct(1, "ZX1")              // estrutura MODEL da capa
    Local oStrZX2 := FWFormStruct(1, "ZX2")              // estrutura MODEL dos itens

    // Capa (master) e grid de itens (detail filho da capa).
    oModel:AddFields("ZX1MASTER", /*cOwner*/, oStrZX1)
    oModel:AddGrid("ZX2DETAIL", "ZX1MASTER", oStrZX2)

    // Relacao master-detail: liga cada item a capa pela filial + numero.
    oModel:SetRelation("ZX2DETAIL", {;
        {"ZX2_FILIAL", "xFilial('ZX2')"},;
        {"ZX2_NUM"   , "ZX1_NUM"}},;
        ZX2->(IndexKey(1)))

    // Chave primaria da capa (NUNCA {} em cadastro com inclusao).
    oModel:SetPrimaryKey({"ZX1_FILIAL", "ZX1_NUM"})

    // Item nao pode repetir o mesmo produto no mesmo pedido.
    oModel:GetModel("ZX2DETAIL"):SetUniqueLine({"ZX2_PRODUT"})

    // Pos-validacao de linha do grid (ex: quantidade > 0).
    oModel:GetModel("ZX2DETAIL"):SetLinePost({|oGrid| ZX2LinePost(oGrid)})

    oModel:SetDescription("Pedidos (exemplo MVC classico)")

    // Hook MODERNO via FWModelEvent (substitui bCommit/bTudoOk descontinuados).
    oModel:InstallEvent("EVT_ZEXPED", /*cOwner*/, ZEvPed():New())
Return oModel

// -----------------------------------------------------------------------------
// ViewDef: cabecalho (capa) em cima, grid de itens embaixo.
// -----------------------------------------------------------------------------
Static Function ViewDef()
    Local oModel  := FWLoadModel("ZEXPEDIDO")            // reaproveita o model
    Local oView   := FWFormView():New()
    Local oStrZX1 := FWFormStruct(2, "ZX1")              // estrutura VIEW da capa
    Local oStrZX2 := FWFormStruct(2, "ZX2")              // estrutura VIEW dos itens

    oView:SetModel(oModel)

    oView:AddField("VIEW_ZX1", oStrZX1, "ZX1MASTER")
    oView:AddGrid("VIEW_ZX2" , oStrZX2, "ZX2DETAIL")

    // Dois boxes horizontais: capa (35%) + itens (65%).
    oView:CreateHorizontalBox("CABEC", 35)
    oView:CreateHorizontalBox("ITENS", 65)

    oView:SetOwnerView("VIEW_ZX1", "CABEC")
    oView:SetOwnerView("VIEW_ZX2", "ITENS")

    // Titulo em cada area.
    oView:EnableTitleView("VIEW_ZX1", "Dados do Pedido")
    oView:EnableTitleView("VIEW_ZX2", "Itens")
Return oView

// -----------------------------------------------------------------------------
// Pos-validacao de linha do grid ZX2.
// -----------------------------------------------------------------------------
Static Function ZX2LinePost(oGrid)
    Local lOk    := .T.
    Local nQuant := oGrid:GetValue("ZX2_QUANT")

    If nQuant <= 0
        Help(, , "ZX2LinePost", , "Quantidade do item deve ser maior que zero.", 1, 0)
        lOk := .F.
    EndIf
Return lOk

// -----------------------------------------------------------------------------
// Opcao custom de menu: aprova o pedido posicionado (ZX1_STATUS = '2').
// Carrega o proprio model em UPDATE, troca o status e grava direto via
// VldData()+CommitData() (sem reabrir a View). Para gravacao 100% headless a
// partir de arrays (ex: batch/integracao) o caminho seria FWMVCRotAuto.
// -----------------------------------------------------------------------------
User Function ZEXAPROV()
    Local aArea   := GetArea()
    Local oModel  := FWLoadModel("ZEXPEDIDO")
    Local lOk     := .F.

    oModel:SetOperation(MODEL_OPERATION_UPDATE)
    oModel:Activate()
    oModel:SetValue("ZX1MASTER", "ZX1_STATUS", "2")

    lOk := oModel:VldData() .And. oModel:CommitData()
    oModel:DeActivate()

    If lOk
        MsgInfo("Pedido aprovado.")
    Else
        MsgStop("Falha ao aprovar o pedido.")
    EndIf

    RestArea(aArea)
Return Nil

// =============================================================================
// FWModelEvent: hooks de transacao (auditoria + notificacao pos-commit).
// =============================================================================
Class ZEvPed From FWModelEvent
    Method New() CONSTRUCTOR
    Method InTTS()      // dentro da transacao: gravacoes auxiliares
    Method AfterTTS()   // depois do commit: notificacoes/integracoes
EndClass

Method New() Class ZEvPed
Return Self

// Grava log de auditoria na ZX9 dentro da mesma transacao do pedido.
Method InTTS(oModel) Class ZEvPed
    Local cNum := oModel:GetValue("ZX1MASTER", "ZX1_NUM")

    DbSelectArea("ZX9")
    RecLock("ZX9", .T.)
    ZX9->ZX9_FILIAL := xFilial("ZX9")
    ZX9->ZX9_NUM    := cNum
    ZX9->ZX9_DTHR   := FwTimeStamp()
    ZX9->ZX9_USER   := RetCodUsr()
    ZX9->(MsUnlock())
Return .T.

// Pos-commit: aqui rede pode falhar sem afetar a transacao ja confirmada.
Method AfterTTS(oModel) Class ZEvPed
    // Ex: U_NotificaIntegracao(oModel:GetValue("ZX1MASTER", "ZX1_NUM"))
Return .T.
