/*
 * uexec.prw — Reference implementation do contrato U_EXEC (docs/exec-contract.md).
 *
 * MIT License
 * Copyright (c) 2026 plugadvpl contributors
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.
 *
 * --------------------------------------------------------------------------
 * Anti-pattern em producao. Use apenas em DEV/HML/CI atras de firewall.
 * Endpoint que executa funcao arbitraria expoe o RPO inteiro.
 * --------------------------------------------------------------------------
 */

#include "totvs.ch"
#include "restful.ch"

WSRESTFUL UEXEC DESCRIPTION "Headless function executor (DEV/CI only)"
    WSDATA cBody AS STRING
ENDWSRESTFUL

/*
 * POST /rest/uexec
 *
 * Body : {"function":"U_<NAME>","args":[<json values>]}
 * Resp : {"ok":bool,"function":"...","type":"C|N|L|D|A|O|U","result":...,"error":"..."}
 */
WSMETHOD POST exec WSSERVICE UEXEC
    Local cBody    := ""
    Local cFunc    := ""
    Local aArgs    := {}
    Local oJsonIn  := JsonObject():New()
    Local oJsonOut := JsonObject():New()
    Local xResult  := Nil
    Local cType    := "U"
    Local cErr     := ""
    Local lOk      := .F.
    Local cParse   := ""
    Local cExec    := ""

    ::SetContentType("application/json; charset=utf-8")

    // Encoding boundary: body chega UTF-8 (charset declarado no header).
    cBody := DecodeUtf8(::GetContent())

    cParse := oJsonIn:FromJson(cBody)
    If !Empty(cParse)
        oJsonOut["ok"]    := .F.
        oJsonOut["error"] := "JSON invalido: " + cParse
        ::SetResponse(EncodeUtf8(FwJsonSerialize(oJsonOut, .F., .F., .T.)))
        Return .T.
    EndIf

    cFunc := AllTrim(Upper(oJsonIn:GetJsonText("function")))
    If Empty(cFunc) .Or. Left(cFunc, 2) != "U_"
        oJsonOut["ok"]    := .F.
        oJsonOut["error"] := "function obrigatorio e deve comecar com U_"
        ::SetResponse(EncodeUtf8(FwJsonSerialize(oJsonOut, .F., .F., .T.)))
        Return .T.
    EndIf

    If oJsonIn:HasProperty("args")
        aArgs := JsonArgsToAdvplArray(oJsonIn["args"])
    EndIf

    BEGIN SEQUENCE
        xResult := ExecuteUserFunc(cFunc, aArgs)
        cType   := ValType(xResult)
        lOk     := .T.
    RECOVER USING oErr
        cErr  := "Excecao em " + cFunc + ": " + GetExcError(oErr)
        lOk   := .F.
    END SEQUENCE

    oJsonOut["ok"]       := lOk
    oJsonOut["function"] := cFunc
    If lOk
        oJsonOut["type"]   := cType
        oJsonOut["result"] := AdvplValueToJson(xResult)
    Else
        oJsonOut["error"]  := cErr
    EndIf

    cExec := EncodeUtf8(FwJsonSerialize(oJsonOut, .F., .F., .T.))
    ::SetResponse(cExec)
Return .T.

/*
 * ExecuteUserFunc — chama ExecBlock com aArgs (preserva acentos, evita macro).
 */
Static Function ExecuteUserFunc(cFunc, aArgs)
    Local xRet := Nil
    Default aArgs := {}

    xRet := ExecBlock(cFunc, .F., .F., aArgs)
Return xRet

/*
 * JsonArgsToAdvplArray — mapeia array JSON em array ADVPL.
 *   string ISO YYYY-MM-DD -> data ADVPL via CToD (formato BR DD/MM/YYYY).
 *   demais tipos passam direto.
 */
Static Function JsonArgsToAdvplArray(aJsonArgs)
    Local aOut := {}
    Local i
    Local x
    Local cIso := ""

    If !(ValType(aJsonArgs) == "A")
        Return aOut
    EndIf

    For i := 1 To Len(aJsonArgs)
        x := aJsonArgs[i]
        If ValType(x) == "C" .And. Len(x) == 10 .And. SubStr(x, 5, 1) == "-" .And. SubStr(x, 8, 1) == "-"
            // ISO YYYY-MM-DD -> CToD("DD/MM/YYYY")
            cIso := SubStr(x, 9, 2) + "/" + SubStr(x, 6, 2) + "/" + SubStr(x, 1, 4)
            AAdd(aOut, CToD(cIso))
        Else
            AAdd(aOut, x)
        EndIf
    Next i
Return aOut

/*
 * AdvplValueToJson — serializa qualquer ValType para algo JSON-safe.
 *   D -> "YYYY-MM-DD"
 *   O/A -> deixa o FwJsonSerialize cuidar
 *   U -> NIL
 */
Static Function AdvplValueToJson(xValue)
    Local cType := ValType(xValue)
    Local cDateStr := ""

    Do Case
        Case cType == "D"
            cDateStr := DToS(xValue)
            If !Empty(cDateStr)
                cDateStr := SubStr(cDateStr, 1, 4) + "-" + SubStr(cDateStr, 5, 2) + "-" + SubStr(cDateStr, 7, 2)
            EndIf
            Return cDateStr
        Case cType == "U"
            Return Nil
    EndCase
Return xValue

/*
 * GetExcError — extrai mensagem humana de um ErrorObject.
 */
Static Function GetExcError(oErr)
    Local cMsg := ""
    If ValType(oErr) == "O"
        cMsg := AllTrim(oErr:Description) + " [" + AllTrim(oErr:OsCode) + "]"
    Else
        cMsg := "Erro desconhecido"
    EndIf
Return cMsg
