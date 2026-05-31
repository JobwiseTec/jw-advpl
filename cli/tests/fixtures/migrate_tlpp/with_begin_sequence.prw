#Include "protheus.ch"

User Function FATA060()
    Local oErr
    Local lOk := .T.

    Begin Sequence
        If !lOk
            Break
        EndIf
        ConOut("Sucesso")
    Recover Using oErr
        ConOut("Falhou: " + oErr:Description)
    End Sequence
Return lOk
