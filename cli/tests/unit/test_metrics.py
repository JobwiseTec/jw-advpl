"""Tests dos extractors de métricas (Universo 4 / Feature B v0.6.0)."""
from __future__ import annotations

from plugadvpl.parsing.metrics import (
    compute_cyclomatic_complexity,
    compute_max_nesting,
    extract_function_metrics,
)


class TestComplexidadeCiclomatica:
    """McCabe simplificado pra ADVPL."""

    def test_baseline_returns_1(self) -> None:
        """Função sem ramificação tem CC=1."""
        src = "User Function Foo()\n   Return Nil\n"
        assert compute_cyclomatic_complexity(src) == 1

    def test_if_adds_1(self) -> None:
        """Cada If aumenta CC em 1."""
        src = "If x > 0\n   y := 1\nEndIf"
        assert compute_cyclomatic_complexity(src) == 2

    def test_elseif_adds_1_else_does_not(self) -> None:
        """ElseIf conta (branch novo); Else NÃO conta (padrão McCabe)."""
        src = "If x > 0\n   y := 1\nElseIf x < 0\n   y := -1\nElse\n   y := 0\nEndIf"
        # 1 (base) + 1 (If) + 1 (ElseIf) + 0 (Else) = 3
        assert compute_cyclomatic_complexity(src) == 3

    def test_while_for_each_add_1(self) -> None:
        src = "While !Eof()\n   For i := 1 To 10\n      x++\n   Next i\nEndDo"
        # base + While + For = 3
        assert compute_cyclomatic_complexity(src) == 3

    def test_do_case_each_case_adds_1(self) -> None:
        """Do Case = +1 base; cada Case = +1."""
        src = (
            "Do Case\n"
            "Case x == 1\n   y := 'a'\n"
            "Case x == 2\n   y := 'b'\n"
            "OtherWise\n   y := '?'\n"
            "EndCase"
        )
        # base + Case (1) + Case (2) = 3 (OtherWise não conta como ramo extra)
        assert compute_cyclomatic_complexity(src) == 3

    def test_iif_adds_1(self) -> None:
        """IIf ternário conta como caminho condicional."""
        src = "cVal := IIf(x > 0, 'pos', 'neg')"
        assert compute_cyclomatic_complexity(src) == 2

    def test_catch_adds_1(self) -> None:
        src = "Try\n   x := 1\nCatch oErr\n   ConOut('err')\nEnd"
        assert compute_cyclomatic_complexity(src) == 2

    def test_ignores_keywords_in_strings(self) -> None:
        """`If` dentro de string NÃO conta."""
        src = 'cMsg := "If you see this"\nReturn Nil'
        assert compute_cyclomatic_complexity(src) == 1

    def test_ignores_keywords_in_comments(self) -> None:
        src = "// If something then\n/* While true */\nReturn Nil"
        assert compute_cyclomatic_complexity(src) == 1


class TestProfundidadeAninhamento:
    """Stack-based scan de openers/closers."""

    def test_flat_returns_0(self) -> None:
        """Função sem blocos tem nesting=0."""
        src = "Local x := 1\nReturn x"
        assert compute_max_nesting(src) == 0

    def test_single_if_depth_1(self) -> None:
        src = "If x > 0\n   y := 1\nEndIf"
        assert compute_max_nesting(src) == 1

    def test_nested_if_depth_2(self) -> None:
        src = "If x > 0\n   If y > 0\n      z := 1\n   EndIf\nEndIf"
        assert compute_max_nesting(src) == 2

    def test_nested_if_while_for_depth_3(self) -> None:
        src = (
            "If x > 0\n"
            "   While !Eof()\n"
            "      For i := 1 To 10\n"
            "         z++\n"
            "      Next i\n"
            "   EndDo\n"
            "EndIf"
        )
        assert compute_max_nesting(src) == 3

    def test_sequential_blocks_not_nested(self) -> None:
        """Dois Ifs em sequência (não aninhados) = depth 1."""
        src = (
            "If x > 0\n   y := 1\nEndIf\n"
            "If x < 0\n   y := -1\nEndIf"
        )
        assert compute_max_nesting(src) == 1

    def test_do_case_counts_as_block(self) -> None:
        src = "Do Case\nCase x == 1\n   y := 1\nEndCase"
        assert compute_max_nesting(src) == 1


class TestExtractFunctionMetrics:
    """Agregação: dado um body de função, retorna métricas combinadas."""

    def test_simple_function(self) -> None:
        src = "Local x := 1\nReturn x"
        m = extract_function_metrics(src)
        assert m["cc"] == 1
        assert m["nesting"] == 0

    def test_complex_function(self) -> None:
        src = (
            "Local i\n"
            "For i := 1 To 10\n"
            "   If i % 2 == 0\n"
            "      ConOut('par')\n"
            "   Else\n"
            "      ConOut('impar')\n"
            "   EndIf\n"
            "Next i"
        )
        m = extract_function_metrics(src)
        # base + For + If = 3
        assert m["cc"] == 3
        # For aninhado com If dentro = depth 2
        assert m["nesting"] == 2
