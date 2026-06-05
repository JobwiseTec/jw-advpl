"""Testes do parser de header doc declarativo (parsing/header.py, #63).

Fixtures usam nomes 100% fictícios (sem cliente real). Decisões de design foram
validadas contra bases reais — estes testes travam o comportamento.
"""

from __future__ import annotations

from plugadvpl.parsing.header import extract_header_doc


class TestExtractHeaderDoc:
    def test_header_classico_dotado(self) -> None:
        """Estilo clássico Protheus com pontuação '....:'."""
        src = (
            "/*\n"
            "===========================================================\n"
            "Programa............: ABC0001\n"
            "Autor...............: Fulano de Tal\n"
            "Data................: 01/01/2020\n"
            "Descricao/Objetivo..: Rotina exemplo de cadastro\n"
            "Uso.................: Empresa Exemplo\n"
            "Obs.................: Versao 1.0\n"
            "===========================================================\n"
            "*/\n"
            "User Function ABC0001()\n"
            "Return\n"
        )
        h = extract_header_doc(src)
        assert h["programa"] == "ABC0001"
        assert h["autor"] == "Fulano de Tal"
        assert h["data_criacao"] == "01/01/2020"
        assert h["descricao"] == "Rotina exemplo de cadastro"
        assert h["uso"] == "Empresa Exemplo"
        assert h["observacao"] == "Versao 1.0"
        assert "raw_header" in h

    def test_descricao_objetivo_com_espacos_ao_redor_da_barra(self) -> None:
        """Bug pego em base real: 'Descrição / Objetivo' (espaços) deve casar."""
        src = (
            "/*\n"
            "Programa : ABC0002\n"
            "Descrição / Objetivo : Faz algo importante\n"
            "*/\n"
            "Return\n"
        )
        h = extract_header_doc(src)
        assert h["descricao"] == "Faz algo importante"
        assert h["programa"] == "ABC0002"

    def test_estilo_dois_pontos_simples(self) -> None:
        src = "/*\nPrograma: ABC0003\nAutor: Beltrano\n*/\n"
        h = extract_header_doc(src)
        assert h["programa"] == "ABC0003"
        assert h["autor"] == "Beltrano"

    def test_ignora_bloco_protheus_doc(self) -> None:
        """/*/{Protheus.doc}*/ não é header declarativo — não deve casar."""
        src = (
            "#include 'protheus.ch'\n"
            "/*/{Protheus.doc} ABC0004\n"
            "Funcao exemplo\n"
            "@author Alguem\n"
            "@type function\n"
            "/*/\n"
            "Function ABC0004()\n"
        )
        assert extract_header_doc(src) == {}

    def test_nao_confunde_atribuicao_advpl(self) -> None:
        """':=' do ADVPL não pode virar 'label: valor' (falso-positivo massivo)."""
        src = (
            "User Function ABC0005()\n"
            "    Local aArea := GetArea()\n"
            "    Local cQuery := 'SELECT'\n"
            "    Local nX := 1\n"
            "Return\n"
        )
        assert extract_header_doc(src) == {}

    def test_exige_pelo_menos_dois_labels(self) -> None:
        """Um único 'Nome:' solto num comentário não é header."""
        src = "/*\nNome: so um campo aqui\n*/\nReturn\n"
        assert extract_header_doc(src) == {}

    def test_sem_bloco_de_comentario(self) -> None:
        assert extract_header_doc("User Function ABC0006()\nReturn\n") == {}

    def test_string_vazia(self) -> None:
        assert extract_header_doc("") == {}

    def test_tolera_acentos(self) -> None:
        """Labels com acento (cp1252 decodificado) devem normalizar."""
        src = "/*\nDescrição: com acento\nObservação: outra\n*/\n"
        h = extract_header_doc(src)
        assert h["descricao"] == "com acento"
        assert h["observacao"] == "outra"

    def test_header_em_comentario_de_linha(self) -> None:
        """Fallback: header em run de '//' no topo."""
        src = "// Programa: ABC0007\n// Autor: Ciclano\nUser Function ABC0007()\nReturn\n"
        h = extract_header_doc(src)
        assert h["programa"] == "ABC0007"
        assert h["autor"] == "Ciclano"

    def test_sinonimos_de_campo(self) -> None:
        """'Analista'->autor, 'Solicitante'->solicitante, 'Chamado'->doc_origem."""
        src = (
            "/*\n"
            "Rotina.....: ABC0008\n"
            "Analista...: Dev Um\n"
            "Chamado....: TICKET-123\n"
            "Cliente....: Empresa X\n"
            "*/\n"
        )
        h = extract_header_doc(src)
        assert h["programa"] == "ABC0008"
        assert h["autor"] == "Dev Um"
        assert h["doc_origem"] == "TICKET-123"
        assert h["solicitante"] == "Empresa X"

    def test_primeiro_valor_vence_em_label_duplicado(self) -> None:
        src = "/*\nAutor: Primeiro\nAutor: Segundo\nPrograma: ABC0009\n*/\n"
        h = extract_header_doc(src)
        assert h["autor"] == "Primeiro"

    def test_determinismo(self) -> None:
        src = "/*\nPrograma: ABC0010\nAutor: Fulano\nDescricao: x\n*/\n"
        assert extract_header_doc(src) == extract_header_doc(src)

    def test_valor_truncado_em_500(self) -> None:
        longo = "x" * 900
        src = f"/*\nPrograma: ABC0011\nDescricao: {longo}\n*/\n"
        h = extract_header_doc(src)
        assert len(h["descricao"]) == 500
