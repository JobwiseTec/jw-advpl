"""Testes do schema do aplicador de SXs (Col + SX3_COLS + validate_spec)."""

from __future__ import annotations

from plugadvpl.aplicador_sx.schema import (
    SIX_COLS,
    SX1_COLS,
    SX2_COLS,
    SX3_COLS,
    SX5_COLS,
    SX6_COLS,
    SX7_COLS,
    SXA_COLS,
    Col,
    validate_spec,
)


def test_sx3_tem_46_colunas_e_primeira_e_arquivo():
    assert len(SX3_COLS) == 46
    assert SX3_COLS[0].nome == "X3_ARQUIVO"
    assert SX3_COLS[0].chave == "alias"
    assert SX3_COLS[0].obrig is True


def test_sx3_defaults_seguros():
    by = {c.nome: c for c in SX3_COLS}
    assert by["X3_PROPRI"].default == "U"
    assert by["X3_RESERV"].default == "xxxxxx x"
    assert by["X3_BROWSE"].default == "N"
    assert by["X3_CONTEXT"].default == "R"


def test_col_e_imutavel():
    assert isinstance(SX3_COLS[0], Col)


def test_valida_campo_obrigatorio_ausente():
    erros, _w = validate_spec({"numero": "099999", "sx3": [{"tipo": "C", "tamanho": 6}]})
    assert any("alias" in e and "obrig" in e.lower() for e in erros)
    assert any("campo" in e for e in erros)


def test_valida_tamanho_estourado():
    erros, _w = validate_spec(
        {
            "numero": "099999",
            "sx3": [{"alias": "ZXX", "campo": "ZXX_NOMEMUITOGRANDEX", "tipo": "C", "tamanho": 6}],
        }
    )
    assert any("X3_CAMPO" in e and "10" in e for e in erros)


def test_spec_valido_sem_erros():
    erros, warns = validate_spec(
        {
            "numero": "099999",
            "sx3": [
                {"alias": "ZXX", "campo": "ZXX_COD", "tipo": "C", "tamanho": 6, "titulo": "Cod"}
            ],
        }
    )
    assert erros == [] and warns == []


def test_numero_obrigatorio():
    erros, _w = validate_spec({"sx3": []})
    assert any("numero" in e for e in erros)


# --- SX2 (tabelas) -------------------------------------------------------


def test_sx2_tem_20_colunas_e_primeira_e_chave():
    assert len(SX2_COLS) == 20
    assert SX2_COLS[0].nome == "X2_CHAVE"
    assert SX2_COLS[0].chave == "alias"
    assert SX2_COLS[0].obrig is True


def test_sx2_defaults_de_modo_exclusivo():
    by = {c.nome: c for c in SX2_COLS}
    assert by["X2_MODO"].default == "E"
    assert by["X2_MODOEMP"].default == "E"
    assert by["X2_MODOUN"].default == "E"


def test_sx2_valida_nome_obrigatorio_ausente():
    erros, _w = validate_spec({"numero": "099999", "sx2": [{"alias": "ZXX"}]})
    assert any("nome" in e and "obrig" in e.lower() for e in erros)


def test_sx2_spec_valido_sem_erros():
    erros, warns = validate_spec(
        {"numero": "099999", "sx2": [{"alias": "ZXX", "nome": "Cadastro X"}]}
    )
    assert erros == [] and warns == []


# --- SIX (índices) -------------------------------------------------------


def test_six_tem_10_colunas_e_primeira_e_indice():
    assert len(SIX_COLS) == 10
    assert SIX_COLS[0].nome == "INDICE"
    assert SIX_COLS[0].chave == "alias"
    assert SIX_COLS[0].obrig is True


def test_six_defaults_ordem_propri_showpesq():
    by = {c.nome: c for c in SIX_COLS}
    assert by["ORDEM"].default == "1"
    assert by["PROPRI"].default == "U"
    assert by["SHOWPESQ"].default == "N"


def test_six_valida_chave_obrigatoria_ausente():
    erros, _w = validate_spec({"numero": "099999", "six": [{"alias": "ZXX", "ordem": "1"}]})
    assert any("chave" in e and "obrig" in e.lower() for e in erros)


def test_six_valida_chave_deve_comecar_por_alias_filial():
    erros, _w = validate_spec(
        {
            "numero": "099999",
            "six": [{"alias": "ZXX", "ordem": "1", "chave": "ZXX_COD+ZXX_DESC"}],
        }
    )
    assert any("ZXX_FILIAL" in e for e in erros)


def test_six_spec_valido_sem_erros():
    erros, warns = validate_spec(
        {
            "numero": "099999",
            "six": [
                {
                    "alias": "ZXX",
                    "ordem": "1",
                    "chave": "ZXX_FILIAL+ZXX_COD",
                    "descricao": "Filial+Cod",
                }
            ],
        }
    )
    assert erros == [] and warns == []


# --- SX6 (parametros MV_*) ----------------------------------------------


def test_sx6_tem_22_colunas_e_primeira_e_fil():
    assert len(SX6_COLS) == 22
    assert SX6_COLS[0].nome == "X6_FIL"
    assert SX6_COLS[1].nome == "X6_VAR"
    assert SX6_COLS[1].chave == "var"
    assert SX6_COLS[1].obrig is True


def test_sx6_default_fil_global_dois_espacos():
    by = {c.nome: c for c in SX6_COLS}
    assert by["X6_FIL"].default == "  "
    assert by["X6_TIPO"].default == "C"
    assert by["X6_PROPRI"].default == "U"


def test_sx6_valida_var_obrigatoria_ausente():
    erros, _w = validate_spec({"numero": "099999", "sx6": [{"tipo": "C"}]})
    assert any("var" in e and "obrig" in e.lower() for e in erros)


def test_sx6_spec_valido_sem_erros():
    erros, warns = validate_spec(
        {"numero": "099999", "sx6": [{"var": "MV_XCUST1", "tipo": "C", "conteudo": "1"}]}
    )
    assert erros == [] and warns == []


# --- SX7 (gatilhos) -----------------------------------------------------


def test_sx7_tem_11_colunas_e_primeira_e_campo():
    assert len(SX7_COLS) == 11
    assert SX7_COLS[0].nome == "X7_CAMPO"
    assert SX7_COLS[0].chave == "campo"
    assert SX7_COLS[0].obrig is True


def test_sx7_defaults_sequenc_tipo_seek():
    by = {c.nome: c for c in SX7_COLS}
    assert by["X7_SEQUENC"].default == "001"
    assert by["X7_TIPO"].default == "P"
    assert by["X7_SEEK"].default == "N"
    assert by["X7_PROPRI"].default == "U"


def test_sx7_campo_obrigatorio_ausente():
    erros, _w = validate_spec({"numero": "099999", "sx7": [{"regra": "X"}]})
    assert any("campo" in e and "obrig" in e.lower() for e in erros)


def test_sx7_campo_fora_do_spec_e_warning_nao_erro():
    # Gatilho sobre campo que nao esta no sx3 do spec -> WARNING (pode pre-existir).
    erros, warns = validate_spec(
        {
            "numero": "099999",
            "sx7": [{"campo": "ZXX_COD", "cdomin": "ZXX_DESC", "regra": "ZXX->ZXX_X"}],
        }
    )
    assert erros == []
    assert any("ZXX_COD" in w for w in warns)


def test_sx7_campo_no_spec_nao_gera_warning():
    erros, warns = validate_spec(
        {
            "numero": "099999",
            "sx3": [{"alias": "ZXX", "campo": "ZXX_COD", "tipo": "C", "tamanho": 6}],
            "sx7": [{"campo": "ZXX_COD", "cdomin": "ZXX_DESC", "regra": "ZXX->ZXX_X"}],
        }
    )
    assert erros == [] and warns == []


# --- SX1 (perguntas) ----------------------------------------------------


def test_sx1_tem_43_colunas_e_primeira_e_grupo():
    assert len(SX1_COLS) == 43
    assert SX1_COLS[0].nome == "X1_GRUPO"
    assert SX1_COLS[0].chave == "grupo"
    assert SX1_COLS[0].obrig is True
    assert SX1_COLS[-1].nome == "X1_IDFIL"


def test_sx1_defaults_tipo_gsc():
    by = {c.nome: c for c in SX1_COLS}
    assert by["X1_TIPO"].default == "C"
    assert by["X1_GSC"].default == "G"


def test_sx1_valida_grupo_ordem_pergunta_obrigatorios():
    erros, _w = validate_spec({"numero": "099999", "sx1": [{"variavel": "MV_X0"}]})
    assert any("grupo" in e and "obrig" in e.lower() for e in erros)
    assert any("ordem" in e and "obrig" in e.lower() for e in erros)
    assert any("pergunta" in e and "obrig" in e.lower() for e in erros)


def test_sx1_spec_valido_sem_erros():
    erros, warns = validate_spec(
        {
            "numero": "099999",
            "sx1": [{"grupo": "ZXXPRG", "ordem": "01", "pergunta": "Filial?"}],
        }
    )
    assert erros == [] and warns == []


# --- SXA (pastas/folders) -----------------------------------------------


def test_sxa_tem_8_colunas_e_primeira_e_alias():
    assert len(SXA_COLS) == 8
    assert SXA_COLS[0].nome == "XA_ALIAS"
    assert SXA_COLS[0].chave == "alias"
    assert SXA_COLS[0].obrig is True


def test_sxa_defaults_ordem_propri():
    by = {c.nome: c for c in SXA_COLS}
    assert by["XA_ORDEM"].default == "01"
    assert by["XA_PROPRI"].default == "U"


def test_sxa_valida_alias_obrigatorio_ausente():
    erros, _w = validate_spec({"numero": "099999", "sxa": [{"descricao": "X"}]})
    assert any("alias" in e and "obrig" in e.lower() for e in erros)


def test_sxa_spec_valido_sem_erros():
    erros, warns = validate_spec(
        {"numero": "099999", "sxa": [{"alias": "ZXX", "ordem": "01", "descricao": "Cadastrais"}]}
    )
    assert erros == [] and warns == []


# --- SX5 (tabelas genericas) --------------------------------------------


def test_sx5_tem_6_colunas_e_primeira_e_filial():
    assert len(SX5_COLS) == 6
    assert SX5_COLS[0].nome == "X5_FILIAL"
    assert SX5_COLS[1].nome == "X5_TABELA"
    assert SX5_COLS[1].chave == "tabela"
    assert SX5_COLS[1].obrig is True


def test_sx5_default_filial_dois_espacos():
    by = {c.nome: c for c in SX5_COLS}
    assert by["X5_FILIAL"].default == "  "


def test_sx5_valida_tabela_chave_obrigatorias():
    erros, _w = validate_spec({"numero": "099999", "sx5": [{"descricao": "X"}]})
    assert any("tabela" in e and "obrig" in e.lower() for e in erros)
    assert any("chave" in e and "obrig" in e.lower() for e in erros)


def test_sx5_spec_valido_sem_erros():
    erros, warns = validate_spec(
        {"numero": "099999", "sx5": [{"tabela": "ZX", "chave": "01", "descricao": "Item"}]}
    )
    assert erros == [] and warns == []
