"""Unit tests for plugadvpl/doc_writer.py (v0.17.0+).

Gerador de blocos Protheus.doc — inverso do parser em
``parsing/protheus_doc.py``. O spec aceito segue o shape de
``_empty_doc()`` pra possibilitar roundtrip ``extract → generate``.
"""

from __future__ import annotations

import pytest

from plugadvpl.doc_writer import (
    DocSpec,
    Param,
    Return,
    generate_protheus_doc,
    spec_from_cli_args,
)


class TestGenerateBasicDoc:
    def test_minimal_doc_has_header_and_closing(self) -> None:
        spec = DocSpec(funcao="MyFunc")
        result = generate_protheus_doc(spec)
        assert result.startswith("/*/{Protheus.doc} MyFunc")
        assert result.rstrip().endswith("/*/")
        assert "@type function" in result

    def test_default_type_is_function(self) -> None:
        spec = DocSpec(funcao="X")
        result = generate_protheus_doc(spec)
        assert "@type function" in result

    def test_custom_type(self) -> None:
        spec = DocSpec(funcao="MyClass", tipo="class")
        assert "@type class" in generate_protheus_doc(spec)

    def test_summary_appears_after_header(self) -> None:
        spec = DocSpec(funcao="MyFunc", summary="Calcula o ICMS conforme TES.")
        result = generate_protheus_doc(spec)
        # summary aparece antes do primeiro @tag
        idx_summary = result.find("Calcula o ICMS")
        idx_type = result.find("@type")
        assert 0 < idx_summary < idx_type


class TestGenerateMetadataTags:
    def test_author_tag(self) -> None:
        spec = DocSpec(funcao="X", author="Joao Silva")
        assert "@author Joao Silva" in generate_protheus_doc(spec)

    def test_since_version_tags(self) -> None:
        spec = DocSpec(funcao="X", since="2024-01-15", version="1.2.3")
        result = generate_protheus_doc(spec)
        assert "@since 2024-01-15" in result
        assert "@version 1.2.3" in result

    def test_no_optional_tags_when_unset(self) -> None:
        spec = DocSpec(funcao="X")
        result = generate_protheus_doc(spec)
        assert "@author" not in result
        assert "@since" not in result
        assert "@version" not in result
        assert "@deprecated" not in result


class TestGenerateParams:
    def test_single_param(self) -> None:
        spec = DocSpec(
            funcao="X",
            params=[Param(name="cCgc", type="character", desc="CNPJ do cliente")],
        )
        result = generate_protheus_doc(spec)
        assert "@param cCgc, character, CNPJ do cliente" in result

    def test_multiple_params_preserve_order(self) -> None:
        spec = DocSpec(
            funcao="X",
            params=[
                Param(name="a", type="numeric", desc="primeiro"),
                Param(name="b", type="character", desc="segundo"),
                Param(name="c", type="logical", desc="terceiro"),
            ],
        )
        result = generate_protheus_doc(spec)
        idx_a = result.find("@param a,")
        idx_b = result.find("@param b,")
        idx_c = result.find("@param c,")
        assert 0 < idx_a < idx_b < idx_c

    def test_optional_param_marked_with_brackets(self) -> None:
        """Convenção TOTVS: param opcional fica entre colchetes no @param.

        Padrão oficial: ``@param [nome], tipo, desc``.
        """
        spec = DocSpec(
            funcao="X",
            params=[Param(name="cExtra", type="character", desc="opcional", optional=True)],
        )
        assert "@param [cExtra], character, opcional" in generate_protheus_doc(spec)

    def test_param_with_only_name(self) -> None:
        spec = DocSpec(funcao="X", params=[Param(name="cNome")])
        result = generate_protheus_doc(spec)
        # Não emite vírgulas vazias — só nome
        assert "@param cNome" in result
        assert "@param cNome," not in result


class TestGenerateReturn:
    def test_return_with_type_and_desc(self) -> None:
        spec = DocSpec(funcao="X", returns=Return(type="logical", desc="True se OK"))
        assert "@return logical, True se OK" in generate_protheus_doc(spec)

    def test_return_with_only_type(self) -> None:
        spec = DocSpec(funcao="X", returns=Return(type="numeric"))
        result = generate_protheus_doc(spec)
        assert "@return numeric" in result
        assert "@return numeric," not in result

    def test_no_return_when_omitted(self) -> None:
        spec = DocSpec(funcao="X")
        assert "@return" not in generate_protheus_doc(spec)


class TestGenerateDeprecated:
    def test_deprecated_flag_only(self) -> None:
        spec = DocSpec(funcao="X", deprecated=True)
        assert "@deprecated" in generate_protheus_doc(spec)

    def test_deprecated_with_reason(self) -> None:
        spec = DocSpec(
            funcao="X", deprecated=True, deprecated_reason="Use NovaFunc no lugar"
        )
        assert "@deprecated Use NovaFunc no lugar" in generate_protheus_doc(spec)


class TestGenerateExamples:
    def test_single_example(self) -> None:
        spec = DocSpec(funcao="X", examples=["U_X(123, 'ABC')"])
        result = generate_protheus_doc(spec)
        assert "@example" in result
        assert "U_X(123, 'ABC')" in result

    def test_multiline_example_indented(self) -> None:
        spec = DocSpec(funcao="X", examples=["nVal := U_X()\nIf nVal > 0\n  // ok\nEndIf"])
        result = generate_protheus_doc(spec)
        # Cada linha do example fica indentada dentro do bloco
        assert "    nVal := U_X()" in result or "        nVal" in result


class TestGenerateHistory:
    def test_history_entry(self) -> None:
        spec = DocSpec(
            funcao="X",
            history=[{"date": "2024-01-15", "user": "JSilva", "desc": "Criada"}],
        )
        result = generate_protheus_doc(spec)
        assert "@history 2024-01-15, JSilva, Criada" in result


class TestSpecFromCliArgs:
    """Construtor que parseia argumentos CLI cruus em DocSpec."""

    def test_basic_funcao_only(self) -> None:
        spec = spec_from_cli_args(funcao="MyFunc")
        assert spec.funcao == "MyFunc"
        assert spec.tipo == "function"

    def test_param_strings_parsed(self) -> None:
        """Param vem como string 'nome,tipo,desc' (repetível)."""
        spec = spec_from_cli_args(
            funcao="X",
            params=["cCgc,character,CNPJ", "[nIdx],numeric,opcional"],
        )
        assert len(spec.params) == 2
        assert spec.params[0].name == "cCgc"
        assert spec.params[0].type == "character"
        assert spec.params[0].desc == "CNPJ"
        assert spec.params[0].optional is False
        # opcional via colchetes
        assert spec.params[1].name == "nIdx"
        assert spec.params[1].optional is True

    def test_return_parsed(self) -> None:
        spec = spec_from_cli_args(funcao="X", returns="logical,True se OK")
        assert spec.returns is not None
        assert spec.returns.type == "logical"
        assert spec.returns.desc == "True se OK"

    def test_deprecated_with_reason(self) -> None:
        spec = spec_from_cli_args(funcao="X", deprecated="Use Y no lugar")
        assert spec.deprecated is True
        assert spec.deprecated_reason == "Use Y no lugar"


class TestRoundtrip:
    """Garante que generate→extract recupera os dados originais (Protheus.doc canônico)."""

    def test_extract_recovers_basic_metadata(self) -> None:
        from plugadvpl.parsing.protheus_doc import extract_protheus_docs

        original = DocSpec(
            funcao="MyFunc",
            tipo="user_function",
            author="Joao",
            since="2024-01",
            summary="Calcula algo importante",
            params=[
                Param(name="cCgc", type="character", desc="CNPJ"),
                Param(name="nIdx", type="numeric", desc="indice", optional=True),
            ],
            returns=Return(type="logical", desc="ok"),
        )
        bloco = generate_protheus_doc(original)
        # Append fake function decl para o parser anchorar
        source = bloco + "\n\nUser Function MyFunc()\nReturn .T.\n"
        extracted = extract_protheus_docs(source, arquivo="myfunc.prw")
        assert len(extracted) == 1
        doc = extracted[0]
        assert doc["funcao_id"] == "MyFunc"
        assert doc["author"] == "Joao"
        assert doc["since"] == "2024-01"
        assert doc["tipo"] == "user_function"
        # 2 params
        assert len(doc["params"]) == 2
        assert doc["params"][0]["name"] == "cCgc"
        assert doc["params"][1]["optional"] is True


class TestEmptyEdgeCases:
    def test_empty_strings_treated_as_unset(self) -> None:
        """author='' não deve emitir @author."""
        spec = DocSpec(funcao="X", author="", since="")
        result = generate_protheus_doc(spec)
        assert "@author" not in result
        assert "@since" not in result

    def test_funcao_required(self) -> None:
        """DocSpec sem funcao deveria falhar (frozen dataclass exige funcao)."""
        with pytest.raises(TypeError):
            DocSpec()  # type: ignore[call-arg]
