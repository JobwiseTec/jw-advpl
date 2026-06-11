#include "totvs.ch"

/*/{Protheus.doc} ZWrOle
Gera um documento Word preenchendo um template .dot/.dotx via automacao OLE
(familia OLE_*). Roda CLIENT-SIDE no SmartClient desktop, com Word instalado.

NAO existe classe MsWord() nem FWMSWord — a API real e' a familia OLE_* (ver
skill advpl-word). NAO roda em JOB/REST/servidor/SmartClient HTML (ApOleClient
indisponivel); nesses casos use RTF (gerar_rtf_servidor.prw).

O template carta.dotx deve ter campos DocVariable (Inserir > Partes Rapidas >
Campo > DocVariable) chamados NomeCli / CnpjCli / DataDoc.

@type  User Function
@since 11/06/2026
/*/
User Function ZWrOle()
    Local nWord  := 0
    Local cTmpl  := "C:\dots\carta.dotx"              // template na ESTACAO
    Local cSaida := GetTempPath() + "carta.docx"      // saida na ESTACAO

    BeginMsOle()
        nWord := OLE_CreateLink()                     // abre link OLE com o Word
        If ValType(nWord) == "N" .And. nWord > 0
            OLE_SetProperty(nWord, OLEWDVISIBLE, .F.)
            OLE_NewFile(nWord, cTmpl)                 // novo doc a partir do template

            OLE_SetDocumentVar(nWord, "NomeCli", "ABC Comercio LTDA")  // = DocVariable
            OLE_SetDocumentVar(nWord, "CnpjCli", "12.345.678/0001-90")
            OLE_SetDocumentVar(nWord, "DataDoc", DToC(Date()))
            OLE_UpdateFields(nWord)                   // aplica nos campos (apos os SetVar)

            OLE_SaveAsFile(nWord, cSaida)             // .docx; nFormato=17 salvaria PDF
            // OLE_PrintFile(nWord, "ALL", , , 1)     // imprime, se quiser

            OLE_CloseFile(nWord)                      // fecha doc
            OLE_CloseLink(nWord)                      // fecha link (senao WINWORD.EXE fica preso)
        Else
            MsgStop("Nao foi possivel abrir o Word. Office instalado na estacao?", "Word")
        EndIf
    EndMsOle()
Return Nil
