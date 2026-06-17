"""Emitter determinístico: spec JSON -> blocos ADVPL (aAdd / FSAtu* / .prw).

Sem random, sem Date.now: a mesma entrada produz exatamente os mesmos bytes.
As funções aqui constroem o texto ADVPL a partir de ``SX_COLS`` (schema) +
o template fixo ``boilerplate.prw.tmpl``.
"""

from __future__ import annotations

import importlib.resources
from typing import Any

from .schema import SX_COLS, Col

# Ordem canônica de emissão das seções FSAtu* no FSTProc (determinística).
_ORDEM_TIPOS: tuple[str, ...] = ("sx2", "sx3", "six", "sx6", "sx7", "sx1", "sxa", "sx5")

# Máscara X3_USADO "todos os módulos" — extraída de aplicadores REAIS que funcionam:
# 115 chars, com 'x' a cada 8 posições (slot de módulo): posições 0,8,16,…,112 e 114.
# Cada slot de 8 chars é um módulo Protheus; 'x' no início do slot = campo ativo nele.
# Campo X3_USADO vazio = inativo = NÃO funciona, por isso o gerador SEMPRE preenche.
_MASCARA_USADO_TODOS: str = "x       " * 14 + "x x"  # 112 + 3 = 115 chars


# Mapa tipo -> nomes ADVPL. "six" não segue o padrão SXn (alias/array/função
# usam "SIX" literal), por isso a tabela explícita em vez de fatiar a string.
_NOMES_TIPO: dict[str, dict[str, str]] = {
    "sx2": {"alias": "SX2", "arr": "aSX2", "fn": "FSAtuSX2"},
    "sx3": {"alias": "SX3", "arr": "aSX3", "fn": "FSAtuSX3"},
    "six": {"alias": "SIX", "arr": "aSIX", "fn": "FSAtuSIX"},
    "sx6": {"alias": "SX6", "arr": "aSX6", "fn": "FSAtuSX6"},
    "sx7": {"alias": "SX7", "arr": "aSX7", "fn": "FSAtuSX7"},
    "sx1": {"alias": "SX1", "arr": "aSX1", "fn": "FSAtuSX1"},
    "sxa": {"alias": "SXA", "arr": "aSXA", "fn": "FSAtuSXA"},
    "sx5": {"alias": "SX5", "arr": "aSX5", "fn": "FSAtuSX5"},
}


def _alias(tipo: str) -> str:
    """Alias do dicionário (área aberta) — ex.: 'sx2' -> 'SX2', 'six' -> 'SIX'."""
    return _NOMES_TIPO[tipo]["alias"]


def _arr_name(tipo: str) -> str:
    """Nome do array local que acumula as entradas — ex.: 'six' -> 'aSIX'."""
    return _NOMES_TIPO[tipo]["arr"]


def _fn_name(tipo: str) -> str:
    """Nome da Static Function — ex.: 'sx2' -> 'FSAtuSX2', 'six' -> 'FSAtuSIX'."""
    return _NOMES_TIPO[tipo]["fn"]


def _esc_char(val: object) -> str:
    """Formata um valor ADVPL char como literal string.

    Default: aspas simples (``'valor'``). Mas campos de EXPRESSAO (X3_VALID, X3_WHEN,
    X3_RELACAO, X7_REGRA, X7_CONDIC, X6_INIT...) carregam codigo ADVPL com aspas
    simples internas (ex.: ``Posicione('ZXX',1,..)``). Nesse caso usa aspas DUPLAS
    para PRESERVAR o conteudo sem quebrar o literal (em vez de remover as aspas).
    Fallback defensivo: se o valor tiver os dois tipos de aspas, mantem simples e
    remove as internas (caso raro em dado de dicionario).
    """
    s = "" if val is None else str(val)
    if "'" in s and '"' not in s:
        return f'"{s}"'
    if '"' in s:
        return "'" + s.replace("'", "") + "'"
    return f"'{s}'"


def _fmt_value(col: Col, entry: dict[str, Any]) -> str:
    """Calcula o literal ADVPL para uma coluna a partir do entry do spec.

    Regras:
    - X3_TRIGGER: 'S' quando entry['trigger'] is True, senão ''.
    - X3_USADO: máscara de ativação por módulo (115 chars). SEMPRE preenchida —
      vazio/'todos'/ausente -> todos os módulos; string custom -> respeita.
    - SHOWPESQ: bool -> 'S'/'N'; string 'S'/'N' passa direto (default 'N').
    - tipo 'N': inteiro. tipo 'L': .T./.F. char: 'valor'.
    - default-fill a partir de Col.default quando a chave não está no entry.
    """
    # X3_TRIGGER é booleano no spec -> 'S' / ''
    if col.nome == "X3_TRIGGER":
        return "'S'" if entry.get("trigger") is True else "''"

    # Valor bruto: do spec (se houver chave) ou o default da coluna.
    if col.chave is not None and col.chave in entry and entry[col.chave] is not None:
        raw: object = entry[col.chave]
    else:
        raw = col.default

    # SHOWPESQ (SIX): bool -> 'S'/'N' (consistente com o trigger booleano do SX3);
    # string 'S'/'N' segue pelo caminho char normal.
    if col.nome == "SHOWPESQ" and isinstance(raw, bool):
        raw = "S" if raw else "N"

    # XA_ORDEM (SXA) é C(1): os reais usam dígito único (1..9). '01' truncaria pra '0'
    # no banco e o seek (XA_ALIAS+XA_ORDEM) não acharia o registro -> re-inserção.
    if col.nome == "XA_ORDEM" and isinstance(raw, str) and raw.strip().isdigit():
        raw = str(int(raw))

    # X3_USADO: SEMPRE preenchido (vazio = campo inativo = não funciona).
    # '' / 'todos' / ausente -> todos os módulos; máscara custom do usuário -> respeita.
    if col.nome == "X3_USADO":
        custom = isinstance(raw, str) and raw not in ("", "todos")
        return _esc_char(raw if custom else _MASCARA_USADO_TODOS)

    if col.tipo == "N":
        try:
            return str(int(str(raw)))
        except (TypeError, ValueError):
            return "0"
    if col.tipo == "L":
        return ".T." if bool(raw) else ".F."
    # char (default)
    return _esc_char(raw)


def _expand_opcoes(entry: dict[str, Any]) -> dict[str, Any]:
    """Expande ``entry['opcoes']`` (SX1) no bloco de radio var0N/def0N/cnt0N (N=1..5).

    Pergunta COM opções é radio mutuamente-exclusiva: `X1_GSC='1'` e o **label**
    de cada opção vai em `X1_DEF0N` (defspaN/defengN espelham via schema). O valor
    retornado em `MV_PARxx` é o ÍNDICE da opção (1..N). Cada opção pode ser uma
    string (só o label) ou um dict `{def, var, cnt}` (avançado). Máx 5 blocos.
    """
    opcoes = entry.get("opcoes")
    if not opcoes:
        return entry
    out = dict(entry)
    out["gsc"] = "1"  # com opções, a pergunta é radio (X1_GSC='1'), não Get livre ('G')
    for idx, opc in enumerate(opcoes[:5], start=1):
        if isinstance(opc, str):
            label, var, cnt = opc, "", ""
        else:
            label, var, cnt = opc.get("def", ""), opc.get("var", ""), opc.get("cnt", "")
        out[f"def0{idx}"] = label
        out[f"var0{idx}"] = var  # vazio no radio simples
        out[f"cnt0{idx}"] = cnt
    return out


def emit_aadd(tipo: str, entry: dict[str, Any]) -> str:
    """Emite um bloco ``aAdd( aSXn, { ... } )`` para uma entrada do spec.

    Uma linha por coluna, terminando em ``, ; //X3_NOME`` (a última fecha o
    array com ``} )`` em vez de vírgula). Para SX1, expande primeiro o bloco de
    ``opcoes`` nas chaves var0N/def0N/cnt0N antes de varrer as colunas.
    """
    if tipo == "sx1":
        entry = _expand_opcoes(entry)
    cols = SX_COLS[tipo]
    arr = _arr_name(tipo)
    linhas: list[str] = [f"aAdd( {arr}, {{ ;"]
    n = len(cols)
    for i, col in enumerate(cols):
        valor = _fmt_value(col, entry)
        if i < n - 1:
            linhas.append(f"\t{valor}, ; //{col.nome}")
        else:
            linhas.append(f"\t{valor} }} ) //{col.nome}")
    return "\n".join(linhas)


def _emit_aestrut(cols: list[Col]) -> str:
    """Monta o ``aEstrut := { { "X3_ARQUIVO", 0 }, ... }`` (pares nome/pos)."""
    pares = [f'{{ "{c.nome}", 0 }}' for c in cols]
    # Quebra em linhas de 4 pares pra legibilidade determinística.
    linhas: list[str] = []
    for i in range(0, len(pares), 4):
        grupo = ", ".join(pares[i : i + 4])
        sep = ", ;" if i + 4 < len(pares) else " }"
        prefixo = "aEstrut := { " if i == 0 else "             "
        linhas.append(f"{prefixo}{grupo}{sep}")
    return "\n".join(linhas)


# Molde fixo do loop de inserção do SX3 (insert-only). X3_ORDEM é calculada em
# runtime no ADVPL (sequência por alias). Adiciona o alias em aArqUpd. Modelado
# na referência canônica (FSAtuSX3, loop após os aAdd).
_LOOP_SX3: str = """nPosArq := aScan( aEstrut, { |x| AllTrim( x[1] ) == "X3_ARQUIVO" } )
nPosOrd := aScan( aEstrut, { |x| AllTrim( x[1] ) == "X3_ORDEM"   } )
nPosCpo := aScan( aEstrut, { |x| AllTrim( x[1] ) == "X3_CAMPO"   } )
nPosTam := aScan( aEstrut, { |x| AllTrim( x[1] ) == "X3_TAMANHO" } )
nPosSXG := aScan( aEstrut, { |x| AllTrim( x[1] ) == "X3_GRPSXG"  } )

aSort( aSX3,,, { |x,y| x[nPosArq]+x[nPosOrd]+x[nPosCpo] < y[nPosArq]+y[nPosOrd]+y[nPosCpo] } )

oProcess:SetRegua2( Len( aSX3 ) )

dbSelectArea( "SX3" )
dbSetOrder( 2 )
cAliasAtu := ""

For nI := 1 To Len( aSX3 )

\t//
\t// Verifica se o campo faz parte de um grupo e ajusta tamanho
\t//
\tIf !Empty( aSX3[nI][nPosSXG] )
\t\tSXG->( dbSetOrder( 1 ) )
\t\tIf SXG->( MSSeek( aSX3[nI][nPosSXG] ) )
\t\t\tIf aSX3[nI][nPosTam] <> SXG->XG_SIZE
\t\t\t\taSX3[nI][nPosTam] := SXG->XG_SIZE
\t\t\t\tAutoGrLog( "O tamanho do campo " + aSX3[nI][nPosCpo] + " foi mantido em [" + ;
\t\t\t\tAllTrim( Str( SXG->XG_SIZE ) ) + "]" + CRLF + ;
\t\t\t\t" por pertencer ao grupo de campos [" + SXG->XG_GRUPO + "]" + CRLF )
\t\t\tEndIf
\t\tEndIf
\tEndIf

\tSX3->( dbSetOrder( 2 ) )

\tIf aScan( aArqUpd, { |x| x == aSX3[nI][nPosArq] } ) == 0
\t\taAdd( aArqUpd, aSX3[nI][nPosArq] )
\tEndIf

\tIf !SX3->( dbSeek( PadR( aSX3[nI][nPosCpo], nTamSeek ) ) )

\t\t//
\t\t// Busca ultima ocorrencia do alias
\t\t//
\t\tIf ( aSX3[nI][nPosArq] <> cAliasAtu )
\t\t\tcSeqAtu   := "00"
\t\t\tcAliasAtu := aSX3[nI][nPosArq]

\t\t\tdbSetOrder( 1 )
\t\t\tSX3->( dbSeek( cAliasAtu + "ZZ", .T. ) )
\t\t\tdbSkip( -1 )

\t\t\tIf ( SX3->X3_ARQUIVO == cAliasAtu )
\t\t\t\tcSeqAtu := SX3->X3_ORDEM
\t\t\tEndIf

\t\t\tnSeqAtu := Val( RetAsc( cSeqAtu, 3, .F. ) )
\t\tEndIf

\t\tnSeqAtu++
\t\tcSeqAtu := RetAsc( Str( nSeqAtu ), 2, .T. )

\t\tRecLock( "SX3", .T. )
\t\tFor nJ := 1 To Len( aSX3[nI] )
\t\t\tIf     nJ == nPosOrd
\t\t\t\tSX3->( FieldPut( FieldPos( aEstrut[nJ][1] ), cSeqAtu ) )

\t\t\tElseIf aEstrut[nJ][2] > 0
\t\t\t\tSX3->( FieldPut( FieldPos( aEstrut[nJ][1] ), aSX3[nI][nJ] ) )

\t\t\tEndIf
\t\tNext nJ

\t\tdbCommit()
\t\tMsUnLock()

\t\tAutoGrLog( "Criado campo " + aSX3[nI][nPosCpo] )

\tEndIf

\toProcess:IncRegua2( "Atualizando Campos de Tabelas (SX3) ..." )

Next nI

AutoGrLog( CRLF + "Final da Atualizacao" + " SX3" + CRLF + Replicate( "-", 128 ) + CRLF )

Return NIL"""


# Declarações Local da FSAtuSX3 (insert-only).
_LOCALS_SX3: str = """Local aEstrut   := {}
Local aSX3      := {}
Local cAliasAtu := ""
Local cSeqAtu   := ""
Local nI        := 0
Local nJ        := 0
Local nPosArq   := 0
Local nPosCpo   := 0
Local nPosOrd   := 0
Local nPosSXG   := 0
Local nPosTam   := 0
Local nSeqAtu   := 0
Local nTamSeek  := Len( SX3->X3_CAMPO )"""


# Declarações Local da FSAtuSX2. cCpoUpd lista os campos atualizados quando a
# tabela já existe (update parcial — não recria a tabela, só ajusta metadados).
_LOCALS_SX2: str = """Local aEstrut   := {}
Local aIncl     := {}
Local aSX2      := {}
Local cCpoUpd   := "X2_ROTINA /X2_UNICO  /X2_DISPLAY/X2_SYSOBJ /X2_USROBJ /X2_POSLGT /"
Local nI        := 0
Local nJ        := 0
Local nPosChv   := 0
Local nPosUni   := 0"""


# Molde fixo do loop do SX2. Insere a tabela quando não existe (RecLock .T.,
# X2_ARQUIVO recebe sufixo de empresa em runtime) ou atualiza só os campos de
# cCpoUpd quando já existe. Modelado na referência canônica (FSAtuSX2).
_LOOP_SX2: str = """nPosChv := aScan( aEstrut, { |x| AllTrim( x[1] ) == "X2_CHAVE" } )
nPosUni := aScan( aEstrut, { |x| AllTrim( x[1] ) == "X2_UNICO" } )

oProcess:SetRegua2( Len( aSX2 ) )

dbSelectArea( "SX2" )
dbSetOrder( 1 )

For nI := 1 To Len( aSX2 )

\toProcess:IncRegua2( "Atualizando Arquivos (SX2) ..." )

\tIf aScan( aArqUpd, { |x| x == aSX2[nI][nPosChv] } ) == 0
\t\taAdd( aArqUpd, aSX2[nI][nPosChv] )
\tEndIf

\tIf !SX2->( dbSeek( aSX2[nI][nPosChv] ) )

\t\tIf aScan( aIncl, { |x| x == aSX2[nI][nPosChv] } ) == 0
\t\t\taAdd( aIncl, aSX2[nI][nPosChv] )
\t\t\tAutoGrLog( "Foi incluida a tabela " + aSX2[nI][nPosChv] )
\t\tEndIf

\t\tRecLock( "SX2", .T. )
\t\tFor nJ := 1 To Len( aSX2[nI] )
\t\t\tIf aEstrut[nJ][2] > 0
\t\t\t\tIf AllTrim( aEstrut[nJ][1] ) == "X2_ARQUIVO"
\t\t\t\t\tSX2->( FieldPut( aEstrut[nJ][2], SubStr( aSX2[nI][nJ], 1, 3 ) + cEmpAnt + "0" ) )
\t\t\t\tElse
\t\t\t\t\tSX2->( FieldPut( aEstrut[nJ][2], aSX2[nI][nJ] ) )
\t\t\t\tEndIf
\t\t\tEndIf
\t\tNext nJ

\t\tdbCommit()
\t\tMsUnLock()

\tElse

\t\tIf !( StrTran( Upper( AllTrim( SX2->X2_UNICO ) ), " ", "" ) == ;
\t\t      StrTran( Upper( AllTrim( aSX2[nI][nPosUni] ) ), " ", "" ) )
\t\t\tRecLock( "SX2", .F. )
\t\t\tSX2->X2_UNICO := aSX2[nI][nPosUni]
\t\t\tdbCommit()
\t\t\tMsUnLock()

\t\t\tIf MSFILE( RetSqlName( aSX2[nI][nPosChv] ), RetSqlName( aSX2[nI][nPosChv] ) + "_UNQ" )
\t\t\t\tTcInternal( 60, RetSqlName( aSX2[nI][nPosChv] ) + "|" + RetSqlName( aSX2[nI][nPosChv] ) + "_UNQ" )
\t\t\tEndIf

\t\t\tAutoGrLog( "Foi alterada a chave unica da tabela " + aSX2[nI][nPosChv] )
\t\tEndIf

\t\tRecLock( "SX2", .F. )
\t\tFor nJ := 1 To Len( aSX2[nI] )
\t\t\tIf aEstrut[nJ][2] > 0 .And. PadR( aEstrut[nJ][1], 10 ) $ cCpoUpd
\t\t\t\tSX2->( FieldPut( aEstrut[nJ][2], aSX2[nI][nJ] ) )
\t\t\tEndIf
\t\tNext nJ

\t\tdbCommit()
\t\tMsUnLock()

\tEndIf

Next nI

AutoGrLog( CRLF + "Final da Atualizacao" + " SX2" + CRLF + Replicate( "-", 128 ) + CRLF )

Return NIL"""


# Declarações Local da FSAtuSIX. lAlt indica update (índice já existe); lDelInd
# marca que a chave mudou e o índice físico precisa ser dropado no banco.
_LOCALS_SIX: str = """Local aEstrut   := {}
Local aSIX      := {}
Local lAlt      := .F.
Local lDelInd   := .F.
Local nI        := 0
Local nJ        := 0
Local nPosInd   := 0
Local nPosOrd   := 0
Local nPosChv   := 0"""


# Molde fixo do loop do SIX. Insere o índice quando não existe (RecLock .T.) ou
# atualiza quando já existe (RecLock .F.). Se a chave mudou, dropa o índice
# físico via TcInternal(60, ...). Modelado na referência canônica (FSAtuSIX).
_LOOP_SIX: str = """nPosInd := aScan( aEstrut, { |x| AllTrim( x[1] ) == "INDICE" } )
nPosOrd := aScan( aEstrut, { |x| AllTrim( x[1] ) == "ORDEM"  } )
nPosChv := aScan( aEstrut, { |x| AllTrim( x[1] ) == "CHAVE"  } )

oProcess:SetRegua2( Len( aSIX ) )

dbSelectArea( "SIX" )
dbSetOrder( 1 )

For nI := 1 To Len( aSIX )

\tlAlt    := .F.
\tlDelInd := .F.

\tIf !SIX->( dbSeek( aSIX[nI][nPosInd] + aSIX[nI][nPosOrd] ) )
\t\tAutoGrLog( "Indice criado " + aSIX[nI][nPosInd] + "/" + aSIX[nI][nPosOrd] + " - " + aSIX[nI][nPosChv] )
\tElse
\t\tlAlt := .T.

\t\tIf aScan( aArqUpd, { |x| x == aSIX[nI][nPosInd] } ) == 0
\t\t\taAdd( aArqUpd, aSIX[nI][nPosInd] )
\t\tEndIf

\t\tIf !( StrTran( Upper( AllTrim( SIX->CHAVE ) ), " ", "" ) == ;
\t\t      StrTran( Upper( AllTrim( aSIX[nI][nPosChv] ) ), " ", "" ) )
\t\t\tAutoGrLog( "Chave do indice alterada " + aSIX[nI][nPosInd] + "/" + aSIX[nI][nPosOrd] + " - " + aSIX[nI][nPosChv] )
\t\t\tlDelInd := .T. // Se for alteracao precisa apagar o indice do banco
\t\tEndIf
\tEndIf

\tRecLock( "SIX", !lAlt )
\tFor nJ := 1 To Len( aSIX[nI] )
\t\tIf aEstrut[nJ][2] > 0
\t\t\tSIX->( FieldPut( aEstrut[nJ][2], aSIX[nI][nJ] ) )
\t\tEndIf
\tNext nJ

\tdbCommit()
\tMsUnLock()

\tIf lDelInd
\t\tTcInternal( 60, RetSqlName( aSIX[nI][nPosInd] ) + "|" + RetSqlName( aSIX[nI][nPosInd] ) + aSIX[nI][nPosOrd] )
\tEndIf

\toProcess:IncRegua2( "Atualizando Indices (SIX) ..." )

Next nI

AutoGrLog( CRLF + "Final da Atualizacao" + " SIX" + CRLF + Replicate( "-", 128 ) + CRLF )

Return NIL"""


# Declarações Local da FSAtuSX6 (insert-only). nTamFil/nTamVar dimensionam o
# seek pela chave física X6_FIL+X6_VAR.
_LOCALS_SX6: str = """Local aEstrut   := {}
Local aSX6      := {}
Local nI        := 0
Local nJ        := 0
Local nPosFil   := 0
Local nPosVar   := 0
Local nTamFil   := Len( SX6->X6_FIL )
Local nTamVar   := Len( SX6->X6_VAR )"""


# Molde fixo do loop do SX6 (insert-only). Respeita parâmetros existentes: só
# insere quando a chave X6_FIL+X6_VAR não existe; nunca atualiza o conteúdo de um
# parâmetro já cadastrado. Modelado na referência canônica (FSAtuSX6).
_LOOP_SX6: str = """nPosFil := aScan( aEstrut, { |x| AllTrim( x[1] ) == "X6_FIL" } )
nPosVar := aScan( aEstrut, { |x| AllTrim( x[1] ) == "X6_VAR" } )

oProcess:SetRegua2( Len( aSX6 ) )

dbSelectArea( "SX6" )
dbSetOrder( 1 )

For nI := 1 To Len( aSX6 )

\toProcess:IncRegua2( "Atualizando Parametros (SX6) ..." )

\tIf !SX6->( dbSeek( PadR( aSX6[nI][nPosFil], nTamFil ) + PadR( aSX6[nI][nPosVar], nTamVar ) ) )

\t\tRecLock( "SX6", .T. )
\t\tFor nJ := 1 To Len( aSX6[nI] )
\t\t\tIf aEstrut[nJ][2] > 0
\t\t\t\tSX6->( FieldPut( aEstrut[nJ][2], aSX6[nI][nJ] ) )
\t\t\tEndIf
\t\tNext nJ

\t\tdbCommit()
\t\tMsUnLock()

\t\tAutoGrLog( "Foi incluido o parametro " + aSX6[nI][nPosFil] + aSX6[nI][nPosVar] )

\tEndIf

Next nI

AutoGrLog( CRLF + "Final da Atualizacao" + " SX6" + CRLF + Replicate( "-", 128 ) + CRLF )

Return NIL"""


# Declarações Local da FSAtuSX7 (insert + flip de X3_TRIGGER). aAreaSX3 preserva
# a área do SX3, que é navegada para marcar o campo de origem como gatilho.
_LOCALS_SX7: str = """Local aEstrut   := {}
Local aAreaSX3  := SX3->( GetArea() )
Local aSX7      := {}
Local nI        := 0
Local nJ        := 0
Local nPosCpo   := 0
Local nPosSeq   := 0
Local nTamSeek  := Len( SX7->X7_CAMPO )"""


# Molde fixo do loop do SX7 (insert). Insere o gatilho quando a chave
# X7_CAMPO+X7_SEQUENC não existe e, em seguida, marca X3_TRIGGER := "S" no campo
# de origem (se ele existir no SX3). Modelado na referência canônica (FSAtuSX7).
_LOOP_SX7: str = """nPosCpo := aScan( aEstrut, { |x| AllTrim( x[1] ) == "X7_CAMPO"   } )
nPosSeq := aScan( aEstrut, { |x| AllTrim( x[1] ) == "X7_SEQUENC" } )

oProcess:SetRegua2( Len( aSX7 ) )

dbSelectArea( "SX3" )
dbSetOrder( 2 )

dbSelectArea( "SX7" )
dbSetOrder( 1 )

For nI := 1 To Len( aSX7 )

\toProcess:IncRegua2( "Atualizando Gatilhos (SX7) ..." )

\tIf !SX7->( dbSeek( PadR( aSX7[nI][nPosCpo], nTamSeek ) + aSX7[nI][nPosSeq] ) )

\t\tRecLock( "SX7", .T. )
\t\tFor nJ := 1 To Len( aSX7[nI] )
\t\t\tIf aEstrut[nJ][2] > 0
\t\t\t\tSX7->( FieldPut( aEstrut[nJ][2], aSX7[nI][nJ] ) )
\t\t\tEndIf
\t\tNext nJ

\t\tdbCommit()
\t\tMsUnLock()

\t\tAutoGrLog( "Foi incluido o gatilho " + aSX7[nI][nPosCpo] + "/" + aSX7[nI][nPosSeq] )

\t\tSX3->( dbSetOrder( 2 ) )
\t\tIf SX3->( dbSeek( SX7->X7_CAMPO ) )
\t\t\tRecLock( "SX3", .F. )
\t\t\tSX3->X3_TRIGGER := "S"
\t\t\tdbCommit()
\t\t\tMsUnLock()
\t\tEndIf

\tEndIf

Next nI

RestArea( aAreaSX3 )

AutoGrLog( CRLF + "Final da Atualizacao" + " SX7" + CRLF + Replicate( "-", 128 ) + CRLF )

Return NIL"""


# Declarações Local da FSAtuSX1 (insert-only). nTam1/nTam2 dimensionam o seek
# pela chave física X1_GRUPO+X1_ORDEM.
_LOCALS_SX1: str = """Local aEstrut   := {}
Local aSX1      := {}
Local nI        := 0
Local nJ        := 0
Local nPosGrp   := 0
Local nPosOrd   := 0
Local nPosTam   := 0
Local nPosSXG   := 0
Local nTam1     := Len( SX1->X1_GRUPO )
Local nTam2     := Len( SX1->X1_ORDEM )"""


# Molde fixo do loop do SX1 (insert-only por grupo+ordem). Ajusta o tamanho da
# pergunta quando o campo pertence a um grupo do SXG e insere quando a chave
# X1_GRUPO+X1_ORDEM não existe. Modelado na referência canônica (FSAtuSX1).
_LOOP_SX1: str = """nPosGrp := aScan( aEstrut, { |x| AllTrim( x[1] ) == "X1_GRUPO"   } )
nPosOrd := aScan( aEstrut, { |x| AllTrim( x[1] ) == "X1_ORDEM"   } )
nPosTam := aScan( aEstrut, { |x| AllTrim( x[1] ) == "X1_TAMANHO" } )
nPosSXG := aScan( aEstrut, { |x| AllTrim( x[1] ) == "X1_GRPSXG"  } )

oProcess:SetRegua2( Len( aSX1 ) )

dbSelectArea( "SX1" )
dbSetOrder( 1 )

For nI := 1 To Len( aSX1 )

\t//
\t// Verifica se a pergunta faz parte de um grupo de campos e ajusta tamanho
\t//
\tIf !Empty( aSX1[nI][nPosSXG] )
\t\tSXG->( dbSetOrder( 1 ) )
\t\tIf SXG->( MSSeek( aSX1[nI][nPosSXG] ) )
\t\t\tIf aSX1[nI][nPosTam] <> SXG->XG_SIZE
\t\t\t\taSX1[nI][nPosTam] := SXG->XG_SIZE
\t\t\tEndIf
\t\tEndIf
\tEndIf

\toProcess:IncRegua2( "Atualizando Perguntas (SX1) ..." )

\tIf !SX1->( dbSeek( PadR( aSX1[nI][nPosGrp], nTam1 ) + PadR( aSX1[nI][nPosOrd], nTam2 ) ) )

\t\tRecLock( "SX1", .T. )
\t\tFor nJ := 1 To Len( aSX1[nI] )
\t\t\tIf aEstrut[nJ][2] > 0
\t\t\t\tSX1->( FieldPut( aEstrut[nJ][2], aSX1[nI][nJ] ) )
\t\t\tEndIf
\t\tNext nJ

\t\tdbCommit()
\t\tMsUnLock()

\t\tAutoGrLog( "Foi incluida a pergunta " + aSX1[nI][nPosGrp] + "/" + aSX1[nI][nPosOrd] )

\tEndIf

Next nI

AutoGrLog( CRLF + "Final da Atualizacao" + " SX1" + CRLF + Replicate( "-", 128 ) + CRLF )

Return NIL"""


# --- Loop de insert simples (compartilhado por SXA e SX5) ------------------
#
# Ambos seguem a mesma forma: seek por uma chave composta; se não existe,
# RecLock(.T.) + FieldPut de todas as colunas + commit. Diferem apenas no
# alias, nas partes da chave de seek e no rótulo de log. ``_KeyPart`` descreve
# uma parte da chave (variável de posição + se aplica PadR pelo tamanho físico).


class _KeyPart:
    """Parte da chave de seek de um loop de insert simples."""

    def __init__(self, nome_col: str, var_pos: str, pad_var: str | None = None) -> None:
        self.nome_col = nome_col  # nome físico da coluna (ex.: "X5_TABELA")
        self.var_pos = var_pos  # variável Local que guarda a posição (ex.: "nPosTab")
        self.pad_var = pad_var  # se != None, aplica PadR(..., pad_var) (ex.: "nTamFil")


def _locals_insert_simples(arr: str, key_parts: list[_KeyPart], pad_locals: str) -> str:
    """Declarações Local de um loop de insert simples (SXA/SX5)."""
    linhas = [
        "Local aEstrut   := {}",
        f"Local {arr}      := {{}}",
        "Local nI        := 0",
        "Local nJ        := 0",
    ]
    for kp in key_parts:
        linhas.append(f"Local {kp.var_pos}   := 0")
    if pad_locals:
        linhas.append(pad_locals)
    return "\n".join(linhas)


def _loop_insert_simples(
    alias: str, arr: str, key_parts: list[_KeyPart], log_label: str, sx_label: str
) -> str:
    """Monta o molde de loop de insert simples (insert-only) para SXA/SX5.

    Seek pela chave composta de ``key_parts``; se não existe, insere via
    RecLock(.T.) + FieldPut de todas as colunas mapeadas no aEstrut.
    """
    scans = "\n".join(
        f'{kp.var_pos} := aScan( aEstrut, {{ |x| AllTrim( x[1] ) == "{kp.nome_col}" }} )'
        for kp in key_parts
    )
    seek_terms: list[str] = []
    for kp in key_parts:
        termo = f"{arr}[nI][{kp.var_pos}]"
        if kp.pad_var:
            termo = f"PadR( {termo}, {kp.pad_var} )"
        seek_terms.append(termo)
    seek_expr = " + ".join(seek_terms)
    primeira = key_parts[0].var_pos
    ultima = key_parts[-1].var_pos
    return f"""{scans}

oProcess:SetRegua2( Len( {arr} ) )

dbSelectArea( "{alias}" )
dbSetOrder( 1 )

For nI := 1 To Len( {arr} )

\toProcess:IncRegua2( "Atualizando {log_label} ({alias}) ..." )

\tIf !{alias}->( dbSeek( {seek_expr} ) )

\t\tRecLock( "{alias}", .T. )
\t\tFor nJ := 1 To Len( {arr}[nI] )
\t\t\tIf aEstrut[nJ][2] > 0
\t\t\t\t{alias}->( FieldPut( aEstrut[nJ][2], {arr}[nI][nJ] ) )
\t\t\tEndIf
\t\tNext nJ

\t\tdbCommit()
\t\tMsUnLock()

\t\tAutoGrLog( "Foi incluido o registro " + {arr}[nI][{primeira}] + "/" + {arr}[nI][{ultima}] )

\tEndIf

Next nI

AutoGrLog( CRLF + "Final da Atualizacao" + " {sx_label}" + CRLF + Replicate( "-", 128 ) + CRLF )

Return NIL"""


# XA_ALIAS é padronizado à largura física (PadR) porque o índice grava o campo
# completo: sem padding, seek 'ZXX'+'01' não casa o key 'ZXX   01' (XA_ALIAS C(6))
# e o registro existente não é encontrado -> re-inserção (duplicata).
_KEY_SXA: list[_KeyPart] = [
    _KeyPart("XA_ALIAS", "nPosAli", pad_var="nTamAli"),
    _KeyPart("XA_ORDEM", "nPosOrd"),
]
_KEY_SX5: list[_KeyPart] = [
    _KeyPart("X5_FILIAL", "nPosFil", pad_var="nTamFil"),
    _KeyPart("X5_TABELA", "nPosTab"),
    _KeyPart("X5_CHAVE", "nPosChv"),
]

_LOCALS_SXA: str = _locals_insert_simples(
    "aSXA", _KEY_SXA, "Local nTamAli   := Len( SXA->XA_ALIAS )"
)
_LOOP_SXA: str = _loop_insert_simples("SXA", "aSXA", _KEY_SXA, "Pastas", "SXA")

_LOCALS_SX5: str = _locals_insert_simples(
    "aSX5", _KEY_SX5, "Local nTamFil   := Len( SX5->X5_FILIAL )"
)
_LOOP_SX5: str = _loop_insert_simples("SX5", "aSX5", _KEY_SX5, "Tabelas", "SX5")


_DOCBLOCK_FSATU: dict[str, str] = {
    "sx2": "Funcao de processamento da gravacao do SX2 - Arquivos",
    "sx3": "Funcao de processamento da gravacao do SX3 - Campos",
    "six": "Funcao de processamento da gravacao do SIX - Indices",
    "sx6": "Funcao de processamento da gravacao do SX6 - Parametros",
    "sx7": "Funcao de processamento da gravacao do SX7 - Gatilhos",
    "sx1": "Funcao de processamento da gravacao do SX1 - Perguntas",
    "sxa": "Funcao de processamento da gravacao do SXA - Pastas",
    "sx5": "Funcao de processamento da gravacao do SX5 - Tabelas",
}

# Declarações Local por tipo (cada loop tem seu próprio conjunto de variáveis).
_LOCALS: dict[str, str] = {
    "sx2": _LOCALS_SX2,
    "sx3": _LOCALS_SX3,
    "six": _LOCALS_SIX,
    "sx6": _LOCALS_SX6,
    "sx7": _LOCALS_SX7,
    "sx1": _LOCALS_SX1,
    "sxa": _LOCALS_SXA,
    "sx5": _LOCALS_SX5,
}

# Molde fixo do loop de gravação por tipo (modelado nas FSAtu* canônicas).
_LOOP: dict[str, str] = {
    "sx2": _LOOP_SX2,
    "sx3": _LOOP_SX3,
    "six": _LOOP_SIX,
    "sx6": _LOOP_SX6,
    "sx7": _LOOP_SX7,
    "sx1": _LOOP_SX1,
    "sxa": _LOOP_SXA,
    "sx5": _LOOP_SX5,
}

# Rótulo do comentário acima dos blocos aAdd, por tipo.
_AADD_LABEL: dict[str, str] = {
    "sx2": "Arquivos",
    "sx3": "Campos",
    "six": "Indices",
    "sx6": "Parametros",
    "sx7": "Gatilhos",
    "sx1": "Perguntas",
    "sxa": "Pastas",
    "sx5": "Tabelas",
}


def _docblock(nome_fn: str, descricao: str) -> str:
    """Cabeçalho Protheus.doc neutralizado (sem ferramenta/nome de cliente)."""
    sep = "//" + "-" * 66
    return (
        f"{sep}\n"
        f"/*/{{Protheus.doc}} {nome_fn}\n\n"
        f"{descricao}\n\n"
        f"@author UPDATE gerado automaticamente\n"
        f"@obs    Aplicador de SXs gerado por plugadvpl\n"
        f"@version 1.0\n"
        f"/*/\n"
        f"{sep}"
    )


def emit_fsatu(tipo: str, entradas: list[dict[str, Any]]) -> str:
    """Emite a função ``Static Function FSAtuSXn()`` completa para um tipo SX.

    Estrutura comum: docblock + locals (por tipo) + aEstrut + aEval(FieldPos)
    + blocos aAdd + loop fixo de gravação (por tipo). Os moldes específicos de
    cada dicionário vêm dos mapas ``_LOCALS``/``_LOOP``/``_AADD_LABEL``.
    """
    cols = SX_COLS[tipo]
    nome_fn = _fn_name(tipo)
    arr = _arr_name(tipo)
    alias = _alias(tipo)

    doc = _docblock(
        nome_fn, _DOCBLOCK_FSATU.get(tipo, f"Funcao de processamento do {tipo.upper()}")
    )
    aestrut = _emit_aestrut(cols)
    blocos = "\n\n".join(emit_aadd(tipo, e) for e in entradas)
    rotulo = _AADD_LABEL.get(tipo, "Registros")

    partes = [
        doc,
        f"Static Function {nome_fn}()",
        _LOCALS[tipo],
        "",
        f'AutoGrLog( "Inicio da Atualizacao" + " {tipo.upper()}" + CRLF )',
        "",
        aestrut,
        "",
        f"aEval( aEstrut, {{ |x| x[2] := {alias}->( FieldPos( x[1] ) ) }} )",
        "",
        "//",
        f"// {rotulo} ({arr})",
        "//",
        blocos,
        "",
        _LOOP[tipo],
    ]
    return "\n".join(partes)


def _read_template() -> str:
    """Lê o boilerplate.prw.tmpl (UTF-8, LF) empacotado com o módulo."""
    return (
        importlib.resources.files("plugadvpl.aplicador_sx")
        .joinpath("boilerplate.prw.tmpl")
        .read_text("utf-8")
    )


def emit_prw(spec: dict[str, Any]) -> str:
    """Monta o .prw final: template + FSAtu* + FSTProc dinâmico.

    Determinístico: mesma spec -> mesmos bytes. ``numero`` vira A{numero}.
    Só emite FSAtu* dos tipos presentes na spec (ordem canônica). ``regua`` =
    nº de chamadas FSAtu* no FSTProc INCLUINDO FSAtuHlp.
    """
    template = _read_template()
    numero = str(spec.get("numero", "")).strip()

    presentes = [t for t in _ORDEM_TIPOS if t in SX_COLS and spec.get(t)]

    # Chamadas FSAtu*() no FSTProc (indentadas 3 tabs, como o restante do loop).
    # Usa _fn_name pra "six" virar FSAtuSIX (não FSAtuSXX via fatiamento).
    calls = [f"\t\t\t{_fn_name(t)}()" for t in presentes]
    fsatu_calls = "\n".join(calls)

    # régua: chamadas presentes + FSAtuHlp (sempre chamada no template).
    regua = len(calls) + 1

    # Corpos das funções FSAtu*.
    fsatu_bodies = "\n\n".join(emit_fsatu(t, spec[t]) for t in presentes)

    out = template
    out = out.replace("{numero}", numero)
    out = out.replace("{regua}", str(regua))
    out = out.replace("{fsatu_calls}", fsatu_calls)
    return out.replace("{fsatu_bodies}", fsatu_bodies)
