"""Fase 4 do roadmap-ia — dispatch hardening (routing-eval + lint de descrições).

Ver docs/roadmap-ia/04-dispatch-hardening.md. Scorers determinísticos ($0); a
predição de skill por um LLM é opt-in/offline e não entra no CI.
"""

from __future__ import annotations


class TestTop1Accuracy:
    def test_all_correct_is_one(self) -> None:
        from plugadvpl.dispatch_eval import top1_accuracy

        cases = [{"predicted": "advpl-mvc", "expected": "advpl-mvc"}]
        assert top1_accuracy(cases) == 1.0

    def test_half_correct(self) -> None:
        from plugadvpl.dispatch_eval import top1_accuracy

        cases = [
            {"predicted": "advpl-mvc", "expected": "advpl-mvc"},
            {"predicted": "advpl-web", "expected": "advpl-webservice"},
        ]
        assert top1_accuracy(cases) == 0.5

    def test_empty_is_one(self) -> None:
        from plugadvpl.dispatch_eval import top1_accuracy

        assert top1_accuracy([]) == 1.0


class TestSetF1:
    def test_identical_sets_is_one(self) -> None:
        from plugadvpl.dispatch_eval import set_f1

        assert set_f1({"a", "b"}, {"a", "b"}) == 1.0

    def test_disjoint_sets_is_zero(self) -> None:
        from plugadvpl.dispatch_eval import set_f1

        assert set_f1({"a"}, {"b"}) == 0.0

    def test_both_empty_is_one(self) -> None:
        from plugadvpl.dispatch_eval import set_f1

        assert set_f1(set(), set()) == 1.0

    def test_partial_overlap(self) -> None:
        from plugadvpl.dispatch_eval import set_f1

        # predicted {a,b}, expected {a} -> P=1/2, R=1/1 -> F1 = 2*.5*1/1.5 = 0.666..
        assert abs(set_f1({"a", "b"}, {"a"}) - 2 / 3) < 1e-9


class TestLintDescription:
    def test_good_description_has_no_errors(self) -> None:
        from plugadvpl.dispatch_eval import lint_description

        d = "Use ao criar ou editar cadastro MVC em .prw clássico; NÃO use para .tlpp (use advpl-mvc-tlpp)."
        assert lint_description("advpl-mvc", d) == []

    def test_too_short_is_error(self) -> None:
        from plugadvpl.dispatch_eval import lint_description

        assert lint_description("x", "Helper de coisas") != []

    def test_vague_standalone_is_error(self) -> None:
        from plugadvpl.dispatch_eval import lint_description

        assert lint_description("x", "utils") != []

    def test_first_person_is_error(self) -> None:
        from plugadvpl.dispatch_eval import lint_description

        d = "Eu ajudo você a criar cadastros MVC e webservices no Protheus rapidamente."
        assert lint_description("x", d) != []
