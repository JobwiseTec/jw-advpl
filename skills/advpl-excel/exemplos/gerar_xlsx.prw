#include "totvs.ch"

/*/{Protheus.doc} ZExpCli
Gera uma planilha .xlsx a partir da tabela ZZ0 usando FWMsExcelXlsx.

FWMsExcelXlsx produz .xlsx BINÁRIO real (requer binário 17.3.0.0+ e printer.exe).
Para XML SpreadsheetML (abre no Excel, extensão diferente) use FWMsExcelEx.
NÃO use FWMsExcel (depreciada — estoura memória em volume grande).

Sequência canônica da família: New → AddWorkSheet → AddTable → AddColumn(s)
→ AddRow (uma por registro, valores em array) → Activate → GetXMLFile.
Tipo de coluna: 1 = texto, 3 = número.

@type  User Function
@since 10/06/2026
/*/
User Function ZExpCli()
    Local oExcel := FWMsExcelXlsx():New()
    Local cAba   := "Clientes"
    Local cTab   := "TB1"
    Local cArq   := "\import\clientes.xlsx"

    oExcel:AddWorkSheet(cAba)
    oExcel:AddTable(cAba, cTab)
    oExcel:AddColumn(cAba, cTab, "Código",    1, 1)   // tipo 1 = texto
    oExcel:AddColumn(cAba, cTab, "Descrição", 1, 1)
    oExcel:AddColumn(cAba, cTab, "Saldo",     3, 1)   // tipo 3 = número

    DbSelectArea("ZZ0")
    ZZ0->(DbGoTop())
    While ZZ0->(!Eof())
        // Cada linha = um array de valores (NÃO existe AddCell na API pública)
        oExcel:AddRow(cAba, cTab, {ZZ0->ZZ0_COD, ZZ0->ZZ0_DESC, ZZ0->ZZ0_SALDO})
        ZZ0->(DbSkip())
    EndDo

    oExcel:Activate()
    oExcel:GetXMLFile(cArq)   // grava o arquivo (saída é .xlsx binário nesta classe)

    FwAlertSuccess("Planilha gerada em " + cArq, "Exportação")
Return Nil
