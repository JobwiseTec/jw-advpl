#Include "protheus.ch"

User Function FATA070()
    Local oJson := JsonObject():New()

    oJson["id"] := 1
    oJson["nome"] := "Teste"
    oJson["ativo"] := .T.
Return oJson
