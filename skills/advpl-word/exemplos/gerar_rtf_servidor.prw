#include "totvs.ch"

/*/{Protheus.doc} ZWrRtf
Gera um documento Word no SERVIDOR (JOB/REST/headless) montando RTF e gravando
com MemoWrite. RTF e' texto puro que o Word/LibreOffice abrem — NAO precisa de
Word instalado e NAO usa OLE (que so roda client-side, ver skill advpl-word).

Caminho recomendado quando a rotina roda fora do SmartClient desktop (Schedule,
REST, RPC). Para fluxo interativo com template .dot, veja word_ole_template.prw.

RTF essencial: \rtf1\ansi (cp1252) | \fonttbl | \fsN (meio-ponto: 28=14pt) |
\b/\b0 (negrito) | \i/\i0 (italico) | \par (paragrafo) | \qc/\ql/\qj (alinhamento).
Escape no texto: \ -> \\, { -> \{, } -> \}.

@type  User Function
@param cNome, character, razao social
@param cCnpj, character, CNPJ
@param cArq,  character, caminho de saida (RootPath-relativo), ex: \docs\carta.rtf
@since 11/06/2026
/*/
User Function ZWrRtf(cNome, cCnpj, cArq)
    Local cRtf := ""

    Default cNome := "ABC Comercio LTDA"
    Default cCnpj := "12.345.678/0001-90"
    Default cArq  := "\docs\carta.rtf"

    cRtf := "{\rtf1\ansi\deff0 {\fonttbl{\f0 Arial;}}" + CRLF
    cRtf += "\qc\fs28\b CARTA AO CLIENTE\b0\par\par" + CRLF
    cRtf += "\ql\fs20 " + CRLF
    cRtf += "Razao Social: " + ZWrEsc(cNome) + "\par" + CRLF
    cRtf += "CNPJ: " + ZWrEsc(cCnpj) + "\par\par" + CRLF
    cRtf += "Sao Paulo, " + DToC(Date()) + ".\par" + CRLF
    cRtf += "}"

    If MemoWrite(cArq, cRtf)
        FwLogMsg("INFO", , "ZWrRtf", FunName(), "", "00", "RTF gerado: " + cArq, 0, 0)
    EndIf
Return Nil

/*/{Protheus.doc} ZWrEsc
Escapa os caracteres reservados do RTF (\ { }) num texto.
@type Static Function
/*/
Static Function ZWrEsc(cTxt)
    cTxt := StrTran(cTxt, "\", "\\")
    cTxt := StrTran(cTxt, "{", "\{")
    cTxt := StrTran(cTxt, "}", "\}")
Return cTxt
