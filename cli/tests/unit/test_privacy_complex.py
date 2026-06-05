"""Testes COMPLEXOS da camada de privacidade — casos reais de cada ambiente.

Inspirados (sinteticamente, sem dado de cliente) em padrões encontrados nas bases:
contratos/financeiro (montagem de chave de título), NFe/fiscal (chave de acesso de
44 dígitos que CONTÉM o CNPJ, connection string em MV), SQL/REST (CNPJ em WHERE,
CPF em DbSeek), e dicionário SX (gatilho SX7, parâmetro SX6).

Foco: onde a máscara PODERIA quebrar a lógica — e como o modo format-preserving
(``style="fpe"``) resolve casos posicionais (SubStr da raiz do CNPJ, chave).
"""

from __future__ import annotations

import re

from plugadvpl.privacy import PrivacyConfig
from plugadvpl.privacy.brdocs import valid_cnpj, valid_cpf
from plugadvpl.privacy.engine import Masker

# Massa fictícia com dígito verificador correto.
CPF_A = "111.444.777-35"
CPF_B = "529.982.247-25"
CNPJ_A = "11.222.333/0001-81"
CNPJ_A_RAW = "11222333000181"


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


def _m(style: str = "label") -> Masker:
    return Masker(PrivacyConfig(enabled=True, style=style))


# =====================================================================
# 1. FORMAT-PRESERVING — o caso central: dado usado em lógica posicional
# =====================================================================
class TestFormatPreserving:
    def test_fpe_cnpj_keeps_shape_and_is_valid(self) -> None:
        out = _m("fpe").mask_text(CNPJ_A)
        assert out != CNPJ_A
        assert len(out) == len(CNPJ_A)
        assert valid_cnpj(out)  # fake, porém válido

    def test_fpe_cpf_keeps_shape_and_is_valid(self) -> None:
        out = _m("fpe").mask_text(CPF_A)
        assert out != CPF_A
        assert len(out) == len(CPF_A)
        assert valid_cpf(out)

    def test_fpe_substr_da_raiz_continua_fazendo_sentido(self) -> None:
        # gatilho que monta chave com a RAIZ do CNPJ: SubStr(cCgc, 1, 8)
        code = f'cRaiz := SubStr("{CNPJ_A_RAW}", 1, 8)'
        out = _m("fpe").mask_text(code)
        mo = re.search(r'SubStr\("(\d{14})"', out)
        assert mo is not None  # ainda são 14 dígitos -> SubStr(1,8) pega a raiz
        assert mo.group(1) != CNPJ_A_RAW

    def test_fpe_raiz_estavel_para_mesmo_cnpj(self) -> None:
        # mesmo CNPJ em 2 lugares -> mesma raiz fake -> chave consistente
        m = _m("fpe")
        a = _digits(m.mask_text(CNPJ_A))
        b = _digits(m.mask_text(CNPJ_A_RAW))
        assert a == b

    def test_label_quebra_substr_mas_fpe_resolve(self) -> None:
        raw = f'SubStr("{CNPJ_A_RAW}", 1, 8)'
        lbl = _m("label").mask_text(raw)
        fpe = _m("fpe").mask_text(raw)
        assert "CNPJ_" in lbl  # label: não tem 14 dígitos para fatiar
        assert re.search(r'"\d{14}"', fpe) is not None  # fpe: mantém fatiável

    def test_fpe_nao_vaza_o_valor_real(self) -> None:
        out = _m("fpe").mask_text(CNPJ_A)
        assert _digits(out) != CNPJ_A_RAW

    def test_fpe_deterministico_entre_maskers(self) -> None:
        a = _m("fpe").mask_text(CPF_A)
        b = _m("fpe").mask_text(CPF_A)
        assert a == b

    def test_fpe_cpfs_distintos_geram_fakes_distintos(self) -> None:
        m = _m("fpe")
        assert m.mask_text(CPF_A) != m.mask_text(CPF_B)


# =====================================================================
# 2. CONTRATOS / FINANCEIRO (inspirado no GH/GCT)
# =====================================================================
class TestContratoFinanceiro:
    def test_chave_titulo_prefixo_mantido_cnpj_mascarado(self) -> None:
        # chave = prefixo "GCT" + num; com CNPJ literal junto
        code = f'cChave := "GCT" + cNum ; cDoc := "{CNPJ_A}"'
        out = _m().mask_text(code)
        assert '"GCT"' in out  # prefixo estrutural intacto
        assert CNPJ_A not in out

    def test_campo_referencia_nao_mascarado(self) -> None:
        # A1_CGC é nome de CAMPO (valor em runtime), não literal -> intacto
        code = "cRaiz := SubStr(SA1->A1_CGC, 1, 8)"
        assert _m().mask_text(code) == code

    def test_mv_param_nome_mantido(self) -> None:
        code = 'nPerc := SuperGetMV("MV_XPCOMGH")'
        assert _m().mask_text(code) == code  # MV_* não é PII

    def test_cnpj_em_comentario_de_contrato(self) -> None:
        code = f"// contrato matriz CNPJ {CNPJ_A} situacao Vigente"
        out = _m().mask_text(code)
        assert CNPJ_A not in out
        assert "situacao Vigente" in out

    def test_sql_getmax_estrutura_intacta(self) -> None:
        sql = "cQuery := \" SELECT MAX(E1_NUM) FROM \" + RetSqlName('SE1')"
        assert _m().mask_text(sql) == sql  # nenhum identificador -> idêntico

    def test_lista_cpf_massa_teste(self) -> None:
        code = f'aCpfs := {{"{CPF_A}", "{CPF_B}"}}'
        out = _m().mask_text(code)
        assert CPF_A not in out
        assert CPF_B not in out
        assert "aCpfs :=" in out

    def test_cpf_distintos_tokens_distintos(self) -> None:
        m = _m()
        assert m.mask_text(CPF_A) != m.mask_text(CPF_B)


# =====================================================================
# 3. NFe / FISCAL (inspirado no MARFRIG)
# =====================================================================
class TestNFeFiscal:
    CHAVE_NFE = "35200711222333000181550010000000071123456780"  # 44 dígitos

    def test_chave_nfe_44_digitos_nao_corrompida(self) -> None:
        # a chave contém o CNPJ embutido, mas é um número de 44 dígitos:
        # o lookaround impede mascarar um "CNPJ substring" e corromper a chave
        out = _m().mask_text(f'_xChaveNfe := "{self.CHAVE_NFE}"')
        assert self.CHAVE_NFE in out

    def test_cnpj_isolado_e_mascarado(self) -> None:
        out = _m().mask_text(f'cCgc := "{CNPJ_A_RAW}"')
        assert CNPJ_A_RAW not in out
        assert "CNPJ_" in out

    def test_connstring_alias_infra_mantido(self) -> None:
        # alias TopConnect/infra é estrutural (a IA pode precisar saber "usa Oracle")
        code = 'cDBStr := GetMv("MGF_FAT59A",,"@!!@ORACLE/SPED")'
        out = _m().mask_text(code)
        assert "ORACLE/SPED" in out

    def test_unc_path_servidor_mantido(self) -> None:
        code = 'cDir := GetMv("MGF_FAT41A",,"\\\\SPDWVAPL182\\XML_NFE\\")'
        out = _m().mask_text(code)
        assert "XML_NFE" in out  # path de rede mantido (não é credencial)

    def test_url_com_credencial_redatada(self) -> None:
        code = 'cWs := "https://svc:p4ss@erp.interno:8443/ws"'
        out = _m().mask_text(code)
        assert "p4ss" not in out
        assert "[REDACTED]@erp.interno" in out

    def test_email_nfe_mascarado(self) -> None:
        out = _m().mask_text('cMail := "nfe@empresa.com.br"')
        assert "nfe@empresa.com.br" not in out
        assert "EMAIL_" in out

    def test_xml_com_cnpj_e_cpf(self) -> None:
        xml = f"<dest><CNPJ>{CNPJ_A_RAW}</CNPJ><CPF>{_digits(CPF_A)}</CPF></dest>"
        out = _m().mask_text(xml)
        assert CNPJ_A_RAW not in out
        assert _digits(CPF_A) not in out
        assert "<dest>" in out and "</dest>" in out  # tags intactas

    def test_fpe_em_chave_montada_com_cnpj(self) -> None:
        # chave = filial + CNPJ + serie (FPE mantém comprimento da chave)
        code = f'cId := "001" + "{CNPJ_A_RAW}" + "55"'
        out = _m("fpe").mask_text(code)
        assert re.search(r'"001" \+ "\d{14}" \+ "55"', out) is not None


# =====================================================================
# 4. SQL / REST (inspirado no VIVEO)
# =====================================================================
class TestSQLeREST:
    def test_cnpj_em_sql_where(self) -> None:
        sql = f"SELECT * FROM SA1010 WHERE A1_CGC = '{CNPJ_A_RAW}'"
        out = _m().mask_text(sql)
        assert CNPJ_A_RAW not in out
        assert "WHERE A1_CGC =" in out
        assert "SA1010" in out

    def test_cpf_em_dbseek(self) -> None:
        code = f'DbSeek(xFilial("SA1") + "{CPF_A}")'
        out = _m().mask_text(code)
        assert CPF_A not in out
        assert 'xFilial("SA1")' in out

    def test_cnpj_em_json_body(self) -> None:
        body = f'{{"cnpj": "{CNPJ_A}", "razao": "ACME LTDA"}}'
        out = _m().mask_text(body)
        assert CNPJ_A not in out
        assert '"cnpj":' in out
        assert '"razao": "ACME LTDA"' in out

    def test_wsmethod_assinatura_intacta(self) -> None:
        code = "WSMETHOD POST Clientes WSSERVICE 4MDGAPI"
        assert _m().mask_text(code) == code

    def test_query_in_clause_multiplos_cnpj(self) -> None:
        sql = f"WHERE A1_CGC IN ('{CNPJ_A_RAW}','{_digits(CNPJ_A)}')"
        out = _m().mask_text(sql)
        assert CNPJ_A_RAW not in out
        assert "A1_CGC IN (" in out

    def test_email_em_header_http(self) -> None:
        out = _m().mask_text('cHdr := "From: suporte@viveo.com.br"')
        assert "suporte@viveo.com.br" not in out
        assert "From:" in out

    def test_fpe_sql_where_continua_valido(self) -> None:
        sql = f"WHERE A1_CGC = '{CNPJ_A_RAW}'"
        out = _m("fpe").mask_text(sql)
        mo = re.search(r"'(\d{14})'", out)
        assert mo is not None
        assert valid_cnpj(mo.group(1))


# =====================================================================
# 5. DICIONÁRIO SX / GATILHOS (cross-cutting)
# =====================================================================
class TestSXeGatilhos:
    def test_sx7_regra_gatilho_com_cnpj(self) -> None:
        rule = f'If A1_EST == "SP" .And. A1_CGC == "{CNPJ_A}"'
        out = _m().mask_text(rule)
        assert CNPJ_A not in out
        assert 'A1_EST == "SP"' in out
        assert "A1_CGC ==" in out

    def test_sx6_mv_connstring_com_senha_redatada(self) -> None:
        code = 'cConex := GetMv("MV_X",,"DRIVER=SQL;PWD=secret123")'
        out = _m().mask_text(code)
        assert "secret123" not in out
        assert "REDACTED" in out

    def test_sx1_pergunta_default_cpf(self) -> None:
        code = f'PutSx1("XYZ","01","CPF?","","","mv_ch1","C",14,0,0,"G","","","","","{CPF_A}")'
        out = _m().mask_text(code)
        assert CPF_A not in out
        assert "PutSx1(" in out

    def test_x3_valid_expressao_intacta(self) -> None:
        # X3_VALID com regra (sem PII) -> idêntico
        code = "ExistChav('SA1',M->A1_COD,1)"
        assert _m().mask_text(code) == code

    def test_password_em_appserver_ini(self) -> None:
        ini = "[DBACCESS]\nPassword=totvs123\nServer=10.0.0.5"
        out = _m().mask_text(ini)
        assert "totvs123" not in out
        assert "REDACTED" in out

    def test_senha_advpl_assignment(self) -> None:
        code = 'cSenha := "Tr0ub4dor3"'
        out = _m().mask_text(code)
        assert "Tr0ub4dor3" not in out

    def test_gatilho_substr_raiz_fpe_consistente(self) -> None:
        # mesma raiz fake nos dois usos do mesmo CNPJ
        m = _m("fpe")
        a = m.mask_text(f'"{CNPJ_A_RAW}"')
        b = m.mask_text(f'SubStr("{CNPJ_A_RAW}",1,8)')
        assert _digits(a)[:8] == _digits(b)[:8]


# =====================================================================
# 6. NÃO-INTERFERÊNCIA — estrutura preservada, zero falso-positivo
# =====================================================================
class TestNaoInterferencia:
    def test_cpf_invalido_nao_mascarado(self) -> None:
        bad = "111.444.777-00"  # DV errado
        out = _m().mask_text(f"cod {bad}")
        assert bad in out

    def test_cnpj_invalido_nao_mascarado(self) -> None:
        bad = "11.222.333/0001-99"
        out = _m().mask_text(f"cod {bad}")
        assert bad in out

    def test_numero_de_versao_nao_e_ip(self) -> None:
        # IP não está nos recognizers default -> versão "7.00.190324" intacta
        code = 'cBuild := "7.00.190324P"'
        assert _m().mask_text(code) == code

    def test_codigo_produto_11_digitos_em_chave_maior(self) -> None:
        # número de 20 dígitos não vira CPF/CNPJ (lookaround)
        big = "12345678901234567890"
        out = _m().mask_text(f'cId := "{big}"')
        assert big in out

    def test_nome_funcao_e_tabela_intactos(self) -> None:
        code = "User Function FA040GRV() ; DbSelectArea('ZZ3') ; SE1->E1_NUM"
        assert _m().mask_text(code) == code

    def test_mask_rows_preserva_estrutura(self) -> None:
        from plugadvpl.privacy import mask_for_egress

        rows = [{"arquivo": "ABC.prw", "linha": 42, "trecho": f'cCgc := "{CNPJ_A}"'}]
        masked, counts = mask_for_egress(rows, PrivacyConfig(enabled=True))
        assert masked[0]["arquivo"] == "ABC.prw"
        assert masked[0]["linha"] == 42
        assert CNPJ_A not in str(masked[0]["trecho"])
        assert counts["cnpj"] == 1

    def test_disabled_nao_altera_nada(self) -> None:
        from plugadvpl.privacy import mask_for_egress

        rows = [{"t": f'{CPF_A} {CNPJ_A}'}]
        masked, counts = mask_for_egress(rows, PrivacyConfig(enabled=False))
        assert masked == rows
        assert sum(counts.values()) == 0

    def test_texto_sem_pii_idempotente(self) -> None:
        code = "Local nX := 0 ; For nI := 1 To Len(aDados) ; Next"
        assert _m().mask_text(code) == code
