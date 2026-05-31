#Include "protheus.ch"

PUBLIC cVarGlobal := "x"
PUBLIC nContador := 0

User Function FATA080()
    nContador := nContador + 1
    ConOut(cVarGlobal)
Return nContador
