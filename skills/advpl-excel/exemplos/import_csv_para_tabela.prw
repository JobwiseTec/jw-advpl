#include "totvs.ch"

/*/{Protheus.doc} ZImpCli
Importa um CSV (export do Excel) e grava cada linha na tabela ZZ0.

Caminho ROBUSTO de leitura no Protheus: NÃO existe função nativa que leia
.xls/.xlsx — peça ao usuário "Salvar como CSV" e leia o texto linha a linha
com FWFileReader (server-side, sem Excel instalado, roda em qualquer ambiente).

Layout esperado do CSV (separado por ';', cabeçalho na 1ª linha):
    Codigo;Descricao
    000001;Cliente Exemplo

Gravação: campos customizados via RecLock/MsUnlock dentro de Begin Transaction.
Para tabela/campos PADRÃO, prefira MSExecAuto (respeita validações/gatilhos).

@type  User Function
@since 10/06/2026
/*/
User Function ZImpCli()
    Local cArq    := ""
    Local oReader := Nil
    Local aCols   := {}
    Local nLin    := 0
    Local nGrav   := 0

    cArq := cGetFile("Arquivo CSV (*.csv)|*.csv", "Selecione o CSV de importação")
    If Empty(cArq)
        Return Nil
    EndIf

    oReader := FWFileReader():New(cArq)
    If !oReader:Open()
        Help(, , "ZImpCli", , "Não foi possível abrir o arquivo: " + cArq, 1, 0)
        Return Nil
    EndIf

    Begin Transaction
        While oReader:HasLine()
            nLin++
            aCols := StrTokArr(oReader:GetLine(), ";")   // ; = separador padrão BR

            // Pula cabeçalho (linha 1) e linhas curtas/vazias
            If nLin == 1 .Or. Len(aCols) < 2 .Or. Empty(AllTrim(aCols[1]))
                Loop
            EndIf

            RecLock("ZZ0", .T.)
                ZZ0->ZZ0_FILIAL := xFilial("ZZ0")
                ZZ0->ZZ0_COD    := PadR(AllTrim(aCols[1]), TamSX3("ZZ0_COD")[1])
                ZZ0->ZZ0_DESC   := PadR(AllTrim(aCols[2]), TamSX3("ZZ0_DESC")[1])
            ZZ0->(MsUnlock())
            nGrav++
        EndDo
    End Transaction

    oReader:Close()
    FwAlertSuccess("Importados " + cValToChar(nGrav) + " registros.", "Importação")
Return Nil
