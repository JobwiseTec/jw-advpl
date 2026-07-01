"""Testes do emitter do aplicador de SXs (emit_aadd / emit_fsatu / emit_prw)."""

from __future__ import annotations

from plugadvpl.aplicador_sx import gen_prw
from plugadvpl.aplicador_sx.emit import emit_aadd, emit_fsatu


def test_emit_aadd_sx3_campo_simples():
    linha = emit_aadd(
        "sx3",
        {"alias": "ZXX", "campo": "ZXX_COD", "tipo": "C", "tamanho": 6, "titulo": "Codigo"},
    )
    assert "aAdd( aSX3, {" in linha
    assert "'ZXX'" in linha
    assert "'ZXX_COD'" in linha
    assert "'U'" in linha
    assert "'xxxxxx x'" in linha
    assert "//X3_CAMPO" in linha


def test_emit_aadd_sx3_titulo_espelha_3_idiomas():
    linha = emit_aadd(
        "sx3", {"alias": "ZXX", "campo": "ZXX_X", "tipo": "C", "tamanho": 1, "titulo": "Tit"}
    )
    assert linha.count("'Tit'") == 3


def test_emit_aadd_sx3_trigger_bool_vira_S():  # noqa: N802
    linha = emit_aadd(
        "sx3", {"alias": "ZXX", "campo": "ZXX_X", "tipo": "C", "tamanho": 1, "trigger": True}
    )
    assert "'S'" in linha.split("//X3_TRIGGER")[0].rsplit("aAdd", 1)[-1]


def test_mascara_usado_todos_115_chars_x_a_cada_8():
    # extraída de aplicadores reais que funcionam: 115 chars, 'x' nas posições
    # 0,8,16,...,112,114 (cada slot de 8 = módulo). 'x'*256 (errado) não ativa o campo.
    from plugadvpl.aplicador_sx.emit import _MASCARA_USADO_TODOS

    assert len(_MASCARA_USADO_TODOS) == 115
    assert [i for i, c in enumerate(_MASCARA_USADO_TODOS) if c == "x"] == [
        0,
        8,
        16,
        24,
        32,
        40,
        48,
        56,
        64,
        72,
        80,
        88,
        96,
        104,
        112,
        114,
    ]


def test_x3_usado_default_ativo_quando_ausente():
    # X3_USADO vazio = campo inativo = não funciona. Sem 'usado' no spec, o gerador
    # SEMPRE preenche com a máscara de todos os módulos (não deixa vazio).
    from plugadvpl.aplicador_sx.emit import _MASCARA_USADO_TODOS

    linha = emit_aadd("sx3", {"alias": "ZXX", "campo": "ZXX_X", "tipo": "C", "tamanho": 1})
    assert f"'{_MASCARA_USADO_TODOS}'" in linha
    assert "//X3_USADO" in linha


def test_x3_usado_mascara_custom_respeitada():
    custom = "x       x       "  # só os 2 primeiros módulos
    linha = emit_aadd(
        "sx3", {"alias": "ZXX", "campo": "ZXX_X", "tipo": "C", "tamanho": 1, "usado": custom}
    )
    assert f"'{custom}'" in linha


def test_emit_fsatu_sx3_estrutura_completa():
    e1 = {"alias": "ZXX", "campo": "ZXX_COD", "tipo": "C", "tamanho": 6, "titulo": "Cod"}
    e2 = {"alias": "ZXX", "campo": "ZXX_DESC", "tipo": "C", "tamanho": 40, "titulo": "Desc"}
    fn = emit_fsatu("sx3", [e1, e2])
    assert "Static Function FSAtuSX3()" in fn
    assert "aEstrut := {" in fn
    assert "RecLock(" in fn
    assert "FieldPut(" in fn
    assert "dbCommit()" in fn
    assert "MsUnLock()" in fn
    assert "aAdd( aArqUpd, " in fn
    # 2 blocos aAdd( aSX3,
    assert fn.count("aAdd( aSX3, {") == 2
    # @obs neutralizado (sem nome de ferramenta de cliente)
    assert "Aplicador de SXs gerado por plugadvpl" in fn


def test_emit_fsatu_sx3_sem_token_de_cliente():
    fn = emit_fsatu("sx3", [{"alias": "ZXX", "campo": "ZXX_X", "tipo": "C", "tamanho": 1}])
    low = fn.lower()
    for tok in ("expordic", "taura", "marfrig", "ernani"):
        assert tok not in low


def test_gen_prw_estrutura_minima_sx3():
    prw = gen_prw(
        {
            "numero": "099999",
            "sx3": [
                {"alias": "ZXX", "campo": "ZXX_COD", "tipo": "C", "tamanho": 6, "titulo": "Cod"}
            ],
        }
    )
    assert "User Function A099999(" in prw
    assert "Static Function FSTProc(" in prw
    assert "Static Function FSAtuSX3(" in prw
    assert "FSAtuSX3()" in prw
    assert "X31UpdTable(" in prw
    assert "Static Function MyOpenSM0(" in prw


def test_gen_prw_so_chama_fsatu_dos_tipos_presentes():
    prw = gen_prw(
        {"numero": "099999", "sx3": [{"alias": "ZXX", "campo": "ZXX_C", "tipo": "C", "tamanho": 1}]}
    )
    assert "FSAtuSX2()" not in prw


# --- SX2 (tabelas) -------------------------------------------------------


def test_emit_aadd_sx2_tabela_simples():
    linha = emit_aadd("sx2", {"alias": "ZXX", "nome": "Cadastro X"})
    assert "aAdd( aSX2, {" in linha
    assert "'ZXX'" in linha
    assert "'Cadastro X'" in linha
    assert "'E'" in linha  # X2_MODO default exclusivo
    assert "//X2_CHAVE" in linha
    assert linha.rstrip().endswith("//X2_MODULO")


def test_emit_aadd_sx2_nome_espelha_3_idiomas():
    linha = emit_aadd("sx2", {"alias": "ZXX", "nome": "Cadastro X"})
    assert linha.count("'Cadastro X'") == 3  # X2_NOME/NOMESPA/NOMEENG


def test_emit_aadd_sx2_chave_e_arquivo_ambos_recebem_alias():
    linha = emit_aadd("sx2", {"alias": "ZXX", "nome": "Cadastro X"})
    # X2_CHAVE e X2_ARQUIVO compartilham a chave 'alias' do spec.
    assert linha.split("//X2_CHAVE")[0].rsplit("aAdd", 1)[-1].count("'ZXX'") == 1
    assert "'ZXX', ; //X2_ARQUIVO" in linha


def test_emit_fsatu_sx2_estrutura_completa():
    fn = emit_fsatu("sx2", [{"alias": "ZXX", "nome": "Cadastro X"}])
    assert "Static Function FSAtuSX2()" in fn
    assert "aEstrut := {" in fn
    assert "dbSeek" in fn
    assert "RecLock(" in fn
    assert "MsUnLock()" in fn
    # branch de update parcial via cCpoUpd
    assert "cCpoUpd" in fn
    assert "X2_ROTINA" in fn and "X2_DISPLAY" in fn
    assert "Aplicador de SXs gerado por plugadvpl" in fn


def test_emit_fsatu_sx2_sem_token_de_cliente():
    fn = emit_fsatu("sx2", [{"alias": "ZXX", "nome": "Cadastro X"}]).lower()
    for tok in ("expordic", "taura", "marfrig", "ernani", "mgf_"):
        assert tok not in fn


def test_gen_prw_inclui_fsatu_sx2_quando_presente():
    prw = gen_prw({"numero": "099999", "sx2": [{"alias": "ZXX", "nome": "Cadastro X"}]})
    assert "Static Function FSAtuSX2(" in prw
    assert "FSAtuSX2()" in prw


# --- SIX (índices) -------------------------------------------------------


def test_emit_aadd_six_indice_simples():
    linha = emit_aadd(
        "six",
        {"alias": "ZXX", "ordem": "1", "chave": "ZXX_FILIAL+ZXX_COD", "descricao": "Filial+Cod"},
    )
    assert "aAdd( aSIX, {" in linha
    assert "'ZXX'" in linha
    assert "'1'" in linha
    assert "'ZXX_FILIAL+ZXX_COD'" in linha
    assert "'Filial+Cod'" in linha
    assert "//INDICE" in linha
    assert linha.rstrip().endswith("//SHOWPESQ")


def test_emit_aadd_six_descricao_espelha_3_idiomas():
    linha = emit_aadd(
        "six",
        {"alias": "ZXX", "ordem": "1", "chave": "ZXX_FILIAL+ZXX_COD", "descricao": "Filial+Cod"},
    )
    assert linha.count("'Filial+Cod'") == 3  # DESCRICAO/DESCSPA/DESCENG


def test_emit_aadd_six_showpesq_bool_vira_S():  # noqa: N802
    linha = emit_aadd(
        "six",
        {"alias": "ZXX", "ordem": "1", "chave": "ZXX_FILIAL+ZXX_COD", "showpesq": True},
    )
    assert "'S' } ) //SHOWPESQ" in linha


def test_emit_aadd_six_showpesq_string_passa():
    linha = emit_aadd(
        "six",
        {"alias": "ZXX", "ordem": "1", "chave": "ZXX_FILIAL+ZXX_COD", "showpesq": "S"},
    )
    assert "'S' } ) //SHOWPESQ" in linha


def test_emit_aadd_six_showpesq_default_N():  # noqa: N802
    linha = emit_aadd("six", {"alias": "ZXX", "ordem": "1", "chave": "ZXX_FILIAL+ZXX_COD"})
    assert "'N' } ) //SHOWPESQ" in linha


def test_emit_fsatu_six_estrutura_completa():
    fn = emit_fsatu(
        "six",
        [{"alias": "ZXX", "ordem": "1", "chave": "ZXX_FILIAL+ZXX_COD", "descricao": "Filial+Cod"}],
    )
    assert "Static Function FSAtuSIX()" in fn
    assert "aEstrut := {" in fn
    assert "dbSeek" in fn
    assert "RecLock(" in fn
    assert "MsUnLock()" in fn
    # drop do índice físico quando a chave muda
    assert "TcInternal( 60" in fn
    assert "Aplicador de SXs gerado por plugadvpl" in fn


def test_emit_fsatu_six_sem_token_de_cliente():
    fn = emit_fsatu("six", [{"alias": "ZXX", "ordem": "1", "chave": "ZXX_FILIAL+ZXX_COD"}]).lower()
    for tok in ("expordic", "taura", "marfrig", "ernani", "mgf_"):
        assert tok not in fn


def test_gen_prw_inclui_fsatu_six_quando_presente():
    prw = gen_prw(
        {"numero": "099999", "six": [{"alias": "ZXX", "ordem": "1", "chave": "ZXX_FILIAL+ZXX_COD"}]}
    )
    assert "Static Function FSAtuSIX(" in prw
    assert "FSAtuSIX()" in prw


# --- SX6 (parametros MV_*) ----------------------------------------------


def test_emit_aadd_sx6_parametro_simples():
    linha = emit_aadd("sx6", {"var": "MV_XCUST1", "tipo": "C", "conteudo": "1", "descric": "Desc"})
    assert "aAdd( aSX6, {" in linha
    assert "'MV_XCUST1'" in linha
    assert "'Desc'" in linha
    assert "//X6_VAR" in linha
    assert linha.rstrip().endswith("//X6_PYME")


def test_emit_aadd_sx6_fil_default_dois_espacos():
    linha = emit_aadd("sx6", {"var": "MV_XCUST1", "conteudo": "1"})
    assert "'  ', ; //X6_FIL" in linha


def test_emit_aadd_sx6_descric_espelha_3_idiomas():
    linha = emit_aadd("sx6", {"var": "MV_XCUST1", "conteudo": "1", "descric": "Param X"})
    assert linha.count("'Param X'") == 3  # DESCRIC/DSCSPA/DSCENG


def test_emit_aadd_sx6_conteudo_espelha_3_idiomas():
    linha = emit_aadd("sx6", {"var": "MV_XCUST1", "conteudo": "42"})
    assert linha.count("'42'") == 3  # CONTEUD/CONTSPA/CONTENG


def test_emit_fsatu_sx6_insert_only():
    fn = emit_fsatu("sx6", [{"var": "MV_XCUST1", "tipo": "C", "conteudo": "1", "descric": "Desc"}])
    assert "Static Function FSAtuSX6()" in fn
    assert "aEstrut := {" in fn
    assert "dbSeek" in fn
    assert 'RecLock( "SX6", .T. )' in fn  # insert-only
    assert "MsUnLock()" in fn
    # insert-only: nao deve ter RecLock .F. (nunca atualiza param existente)
    assert 'RecLock( "SX6", .F. )' not in fn
    assert "Aplicador de SXs gerado por plugadvpl" in fn


def test_emit_fsatu_sx6_sem_token_de_cliente():
    fn = emit_fsatu("sx6", [{"var": "MV_XCUST1", "conteudo": "1"}]).lower()
    for tok in ("expordic", "taura", "marfrig", "ernani", "mgf_", "gala"):
        assert tok not in fn


def test_gen_prw_inclui_fsatu_sx6_quando_presente():
    prw = gen_prw({"numero": "099999", "sx6": [{"var": "MV_XCUST1", "conteudo": "1"}]})
    assert "Static Function FSAtuSX6(" in prw
    assert "FSAtuSX6()" in prw


# --- SX7 (gatilhos) -----------------------------------------------------


def test_emit_aadd_sx7_gatilho_simples():
    linha = emit_aadd(
        "sx7",
        {"campo": "ZXX_COD", "cdomin": "ZXX_DESC", "regra": "ZXX->ZXX_X"},
    )
    assert "aAdd( aSX7, {" in linha
    assert "'ZXX_COD'" in linha
    assert "'ZXX_DESC'" in linha
    assert "'ZXX->ZXX_X'" in linha
    assert "//X7_CAMPO" in linha
    assert linha.rstrip().endswith("//X7_CONDIC")


def test_emit_aadd_sx7_defaults_sequenc_tipo_seek():
    linha = emit_aadd("sx7", {"campo": "ZXX_COD"})
    assert "'001', ; //X7_SEQUENC" in linha
    assert "'P', ; //X7_TIPO" in linha
    assert "'N', ; //X7_SEEK" in linha


def test_emit_fsatu_sx7_insert_e_flip_trigger_sx3():
    fn = emit_fsatu("sx7", [{"campo": "ZXX_COD", "cdomin": "ZXX_DESC", "regra": "ZXX->ZXX_X"}])
    assert "Static Function FSAtuSX7()" in fn
    assert "aEstrut := {" in fn
    assert "dbSeek" in fn
    assert 'RecLock( "SX7", .T. )' in fn  # insert
    assert "MsUnLock()" in fn
    # seek pelo campo no SX3 e marca X3_TRIGGER quando o campo existe
    assert "SX3" in fn
    assert "X3_TRIGGER" in fn
    assert "Aplicador de SXs gerado por plugadvpl" in fn


def test_emit_fsatu_sx7_sem_token_de_cliente():
    fn = emit_fsatu("sx7", [{"campo": "ZXX_COD", "regra": "ZXX->ZXX_X"}]).lower()
    for tok in ("expordic", "taura", "marfrig", "ernani", "mgf_", "b1_origem", "b1_vm_gi"):
        assert tok not in fn


def test_validate_sx7_campo_fora_do_spec_e_warning():
    from plugadvpl.aplicador_sx.schema import validate_spec

    erros, warns = validate_spec(
        {"numero": "099999", "sx7": [{"campo": "ZXX_COD", "regra": "ZXX->ZXX_X"}]}
    )
    assert erros == []  # campo fora do spec nao bloqueia
    assert any("ZXX_COD" in w for w in warns)


def test_gen_prw_inclui_fsatu_sx7_quando_presente():
    prw = gen_prw({"numero": "099999", "sx7": [{"campo": "ZXX_COD", "regra": "ZXX->ZXX_X"}]})
    assert "Static Function FSAtuSX7(" in prw
    assert "FSAtuSX7()" in prw


# --- SX1 (perguntas) ----------------------------------------------------


def test_emit_aadd_sx1_pergunta_simples():
    linha = emit_aadd(
        "sx1",
        {"grupo": "ZXXPRG", "ordem": "01", "pergunta": "Filial?", "variavel": "MV_X0"},
    )
    assert "aAdd( aSX1, {" in linha
    assert "'ZXXPRG'" in linha
    assert "'Filial?'" in linha
    assert "'MV_X0'" in linha
    assert "//X1_GRUPO" in linha
    assert linha.rstrip().endswith("//X1_IDFIL")
    assert "'G', ; //X1_GSC" in linha  # default GSC


def test_emit_aadd_sx1_pergunta_espelha_3_idiomas():
    linha = emit_aadd("sx1", {"grupo": "ZXXPRG", "ordem": "01", "pergunta": "Filial?"})
    assert linha.count("'Filial?'") == 3  # PERGUNT/PERSPA/PERENG


def test_emit_aadd_sx1_opcoes_preenche_blocos():
    linha = emit_aadd(
        "sx1",
        {
            "grupo": "ZXXPRG",
            "ordem": "01",
            "pergunta": "Tipo?",
            "tipo": "N",
            "opcoes": [
                {"var": "MV_PAR01", "def": "Sim", "cnt": "1"},
                {"var": "MV_PAR02", "def": "Nao", "cnt": "2"},
            ],
        },
    )
    # bloco 01
    assert "'MV_PAR01', ; //X1_VAR01" in linha
    assert "'Sim', ; //X1_DEF01" in linha
    assert "'1', ; //X1_CNT01" in linha
    # bloco 02
    assert "'MV_PAR02', ; //X1_VAR02" in linha
    assert "'Nao', ; //X1_DEF02" in linha
    assert "'2', ; //X1_CNT02" in linha
    # def espelha em spa/eng do mesmo bloco
    assert linha.count("'Sim'") == 3  # DEF01/DEFSPA1/DEFENG1
    assert linha.count("'Nao'") == 3  # DEF02/DEFSPA2/DEFENG2


def test_emit_aadd_sx1_opcoes_no_maximo_5():
    opcoes = [{"var": f"MV_PAR0{i}", "def": f"Op{i}", "cnt": str(i)} for i in range(1, 8)]
    linha = emit_aadd(
        "sx1",
        {"grupo": "ZXXPRG", "ordem": "01", "pergunta": "X", "opcoes": opcoes},
    )
    # so os 5 primeiros blocos sao preenchidos
    assert "'MV_PAR05', ; //X1_VAR05" in linha
    assert "MV_PAR06" not in linha
    assert "MV_PAR07" not in linha


def test_emit_aadd_sx1_sem_opcoes_blocos_vazios():
    linha = emit_aadd("sx1", {"grupo": "ZXXPRG", "ordem": "01", "pergunta": "X"})
    assert "'', ; //X1_VAR01" in linha


def test_emit_fsatu_sx1_insert_por_grupo_ordem():
    fn = emit_fsatu("sx1", [{"grupo": "ZXXPRG", "ordem": "01", "pergunta": "Filial?"}])
    assert "Static Function FSAtuSX1()" in fn
    assert "aEstrut := {" in fn
    assert "dbSeek" in fn
    assert 'RecLock( "SX1", .T. )' in fn
    assert "MsUnLock()" in fn
    assert "Aplicador de SXs gerado por plugadvpl" in fn


def test_emit_fsatu_sx1_sem_token_de_cliente():
    fn = emit_fsatu("sx1", [{"grupo": "ZXXPRG", "ordem": "01", "pergunta": "X"}]).lower()
    for tok in ("expordic", "taura", "marfrig", "ernani", "mgf", "mgfwscas"):
        assert tok not in fn


def test_gen_prw_inclui_fsatu_sx1_quando_presente():
    prw = gen_prw(
        {"numero": "099999", "sx1": [{"grupo": "ZXXPRG", "ordem": "01", "pergunta": "X"}]}
    )
    assert "Static Function FSAtuSX1(" in prw
    assert "FSAtuSX1()" in prw


# --- SXA (pastas/folders) -----------------------------------------------


def test_emit_aadd_sxa_pasta_simples():
    linha = emit_aadd("sxa", {"alias": "ZXX", "ordem": "01", "descricao": "Cadastrais"})
    assert "aAdd( aSXA, {" in linha
    assert "'ZXX'" in linha
    assert "'1', ; //XA_ORDEM" in linha  # '01' normalizado p/ '1' (XA_ORDEM é C(1))
    assert "'Cadastrais'" in linha
    assert "//XA_ALIAS" in linha
    assert linha.rstrip().endswith("//XA_PROPRI")
    assert "'U' } ) //XA_PROPRI" in linha  # default proprietario


def test_emit_aadd_sxa_descricao_espelha_3_idiomas():
    linha = emit_aadd("sxa", {"alias": "ZXX", "ordem": "01", "descricao": "Cadastrais"})
    assert linha.count("'Cadastrais'") == 3  # DESCRIC/DESCSPA/DESCENG


def test_emit_fsatu_sxa_insert():
    fn = emit_fsatu("sxa", [{"alias": "ZXX", "ordem": "01", "descricao": "Cadastrais"}])
    assert "Static Function FSAtuSXA()" in fn
    assert "aEstrut := {" in fn
    assert "dbSeek" in fn
    assert 'RecLock( "SXA", .T. )' in fn
    assert "MsUnLock()" in fn
    assert "Aplicador de SXs gerado por plugadvpl" in fn


def test_emit_fsatu_sxa_sem_token_de_cliente():
    fn = emit_fsatu("sxa", [{"alias": "ZXX", "ordem": "01", "descricao": "X"}]).lower()
    for tok in ("expordic", "taura", "marfrig", "ernani", "mgf_", "zgx"):
        assert tok not in fn


def test_gen_prw_inclui_fsatu_sxa_quando_presente():
    prw = gen_prw({"numero": "099999", "sxa": [{"alias": "ZXX", "ordem": "01", "descricao": "X"}]})
    assert "Static Function FSAtuSXA(" in prw
    assert "FSAtuSXA()" in prw


# --- SX5 (tabelas genericas) --------------------------------------------


def test_emit_aadd_sx5_item_simples():
    linha = emit_aadd("sx5", {"tabela": "ZX", "chave": "01", "descricao": "Item X"})
    assert "aAdd( aSX5, {" in linha
    assert "'ZX'" in linha
    assert "'01'" in linha
    assert "'Item X'" in linha
    assert "//X5_FILIAL" in linha
    assert linha.rstrip().endswith("//X5_DESCENG")


def test_emit_aadd_sx5_filial_default_dois_espacos():
    linha = emit_aadd("sx5", {"tabela": "ZX", "chave": "01"})
    assert "'  ', ; //X5_FILIAL" in linha


def test_emit_aadd_sx5_descricao_espelha_3_idiomas():
    linha = emit_aadd("sx5", {"tabela": "ZX", "chave": "01", "descricao": "Item X"})
    assert linha.count("'Item X'") == 3  # DESCRI/DESCSPA/DESCENG


def test_emit_fsatu_sx5_insert():
    fn = emit_fsatu("sx5", [{"tabela": "ZX", "chave": "01", "descricao": "Item X"}])
    assert "Static Function FSAtuSX5()" in fn
    assert "aEstrut := {" in fn
    assert "dbSeek" in fn
    assert 'RecLock( "SX5", .T. )' in fn
    assert "MsUnLock()" in fn
    assert "Aplicador de SXs gerado por plugadvpl" in fn


def test_emit_fsatu_sx5_sem_token_de_cliente():
    fn = emit_fsatu("sx5", [{"tabela": "ZX", "chave": "01", "descricao": "X"}]).lower()
    for tok in ("expordic", "taura", "marfrig", "ernani", "mgf_", "atacado"):
        assert tok not in fn


def test_gen_prw_inclui_fsatu_sx5_quando_presente():
    prw = gen_prw({"numero": "099999", "sx5": [{"tabela": "ZX", "chave": "01", "descricao": "X"}]})
    assert "Static Function FSAtuSX5(" in prw
    assert "FSAtuSX5()" in prw


def test_esc_char_preserva_aspas_em_expressao():
    # campos de expressão (X7_REGRA/X3_VALID) com aspas simples internas viram
    # aspas DUPLAS — preserva o código ADVPL em vez de remover as aspas (anti-erro).
    linha = emit_aadd("sx7", {"campo": "ZXX_COD", "regra": "Posicione('ZXX',1,xFilial('ZXX'))"})
    assert "\"Posicione('ZXX',1,xFilial('ZXX'))\"" in linha
    assert "Posicione(ZXX" not in linha  # NÃO removeu as aspas


def test_esc_char_valor_simples_continua_aspas_simples():
    linha = emit_aadd(
        "sx3", {"alias": "ZXX", "campo": "ZXX_X", "tipo": "C", "tamanho": 1, "titulo": "Tit"}
    )
    assert "'Tit'" in linha


def test_sx1_opcoes_vira_radio_gsc1():
    # pergunta COM opções (lista de labels) -> X1_GSC='1' (radio); label em X1_DEF0n, X1_VAR0n vazio.
    fn = emit_aadd(
        "sx1",
        {
            "grupo": "ZXX01",
            "ordem": "01",
            "pergunta": "Tipo?",
            "tipo": "N",
            "opcoes": ["Entrada", "Saida"],
        },
    )
    assert "'1', ; //X1_GSC" in fn
    assert "'Entrada', ; //X1_DEF01" in fn
    assert "'Saida', ; //X1_DEF02" in fn
    assert "'', ; //X1_VAR01" in fn


def test_sx1_sem_opcoes_continua_get_livre():
    fn = emit_aadd("sx1", {"grupo": "ZXX01", "ordem": "01", "pergunta": "Filial?", "tipo": "C"})
    assert "'G', ; //X1_GSC" in fn


def test_sx1_variavl_nao_recebe_mv_par():
    # X1_VARIAVL é C(6) e legado; o gerador não força MV_PARxx (vem da ordem). Vazio é válido.
    fn = emit_aadd("sx1", {"grupo": "ZXX01", "ordem": "01", "pergunta": "Filial?", "tipo": "C"})
    assert "'', ; //X1_VARIAVL" in fn


def test_sxa_seek_padroniza_xa_alias():
    # sem PadR, seek 'ZXX'+'01' não casa o índice 'ZXX   01' (XA_ALIAS C(6)) e duplica.
    from plugadvpl.aplicador_sx.emit import _LOOP_SXA

    assert "PadR( aSXA[nI][nPosAli], nTamAli )" in _LOOP_SXA
    assert "Len( SXA->XA_ALIAS )" in gen_prw(
        {"numero": "099999", "sxa": [{"alias": "ZXX", "ordem": "01", "descricao": "X"}]}
    )


def test_sxa_ordem_normaliza_para_digito_unico():
    # XA_ORDEM é C(1): '01' truncaria p/ '0' no banco e quebraria o seek -> vira '1'.
    assert "'1', ; //XA_ORDEM" in emit_aadd(
        "sxa", {"alias": "ZXX", "ordem": "01", "descricao": "X"}
    )
    assert "'2', ; //XA_ORDEM" in emit_aadd("sxa", {"alias": "ZXX", "ordem": "2", "descricao": "X"})
