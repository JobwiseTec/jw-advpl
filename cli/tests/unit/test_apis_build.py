"""Testes de cli/plugadvpl/parsing/apis_build.py (issue #26 — apis_por_build)."""
from __future__ import annotations

from plugadvpl.parsing.apis_build import (
    check_build,
    check_build_lint_rows,
    compare_builds,
    load_apis_catalog,
)


class TestLoadApisCatalog:
    def test_loads_bundled_catalog_with_setblkbackcolor(self) -> None:
        catalog = load_apis_catalog()
        assert isinstance(catalog, list)
        keys = {(c["classe"], c["metodo"]) for c in catalog}
        assert ("FWMarkBrowse", "SetBlkBackColor") in keys

    def test_entries_have_required_fields(self) -> None:
        for c in load_apis_catalog():
            for field in ("classe", "metodo", "build_min", "build_max", "fonte", "nota"):
                assert field in c


class TestCompareBuilds:
    def test_lower_minor_is_less(self) -> None:
        assert compare_builds("24.3.0.5", "24.3.1.4") == -1

    def test_higher_minor_is_greater(self) -> None:
        assert compare_builds("24.3.1.4", "24.3.0.5") == 1

    def test_equal(self) -> None:
        assert compare_builds("24.3.0.5", "24.3.0.5") == 0

    def test_different_length_padded_with_zeros(self) -> None:
        assert compare_builds("24.3", "24.3.0.0") == 0

    def test_patch_difference(self) -> None:
        assert compare_builds("24.3.0.5", "24.3.0.9") == -1


_CAT_SETBLK = {
    "classe": "FWMarkBrowse",
    "metodo": "SetBlkBackColor",
    "build_min": "24.3.1.4",
    "build_max": None,
    "fonte": "TDN @since",
    "nota": "use AddLegend/SetColorFn no FWMarkBrowse",
}


class TestCheckBuild:
    def test_positive_method_absent_in_target(self) -> None:
        src = (
            "User Function ZZUI()\n"                       # 1
            "  Local oBrowse := FWMarkBrowse():New()\n"    # 2
            '  oBrowse:SetBlkBackColor({|| "RED"})\n'      # 3
            "Return\n"                                     # 4
        )
        findings = check_build(src, [_CAT_SETBLK], "24.3.0.5")
        assert len(findings) == 1
        assert findings[0]["classe"] == "FWMarkBrowse"
        assert findings[0]["metodo"] == "SetBlkBackColor"
        assert findings[0]["linha"] == 3

    def test_negative_target_within_window(self) -> None:
        src = (
            "User Function ZZUI()\n"
            "  Local oBrowse := FWMarkBrowse():New()\n"
            '  oBrowse:SetBlkBackColor({|| "RED"})\n'
            "Return\n"
        )
        assert check_build(src, [_CAT_SETBLK], "24.3.1.4") == []

    def test_negative_var_not_resolved(self) -> None:
        src = (
            "User Function ZZUI2()\n"
            '  oBrowse:SetBlkBackColor({|| "RED"})\n'
            "Return\n"
        )
        assert check_build(src, [_CAT_SETBLK], "24.3.0.5") == []

    def test_negative_method_not_in_catalog(self) -> None:
        src = (
            "User Function ZZUI3()\n"
            "  Local oBrowse := FWMarkBrowse():New()\n"
            "  oBrowse:Refresh()\n"
            "Return\n"
        )
        assert check_build(src, [_CAT_SETBLK], "24.3.0.5") == []

    def test_negative_method_on_different_class(self) -> None:
        """SetBlkBackColor catalogado p/ FWMarkBrowse; chamada em MsDialog não dispara."""
        src = (
            "User Function ZZUI4()\n"
            "  Local oDlg := MsDialog():New()\n"
            "  oDlg:SetBlkBackColor(123)\n"
            "Return\n"
        )
        assert check_build(src, [_CAT_SETBLK], "24.3.0.5") == []

    def test_positive_method_removed_after_build_max(self) -> None:
        cat = {
            "classe": "FwOldClass",
            "metodo": "OldMethod",
            "build_min": None,
            "build_max": "23.0.0.0",
            "fonte": "TDN",
            "nota": "removido",
        }
        src = (
            "User Function ZZUI5()\n"
            "  Local oOld := FwOldClass():New()\n"
            "  oOld:OldMethod()\n"
            "Return\n"
        )
        findings = check_build(src, [cat], "24.3.0.5")
        assert len(findings) == 1
        assert findings[0]["metodo"] == "OldMethod"

    def test_finding_includes_funcao(self) -> None:
        src = (
            "User Function ZZUI()\n"
            "  Local oBrowse := FWMarkBrowse():New()\n"
            '  oBrowse:SetBlkBackColor({|| "RED"})\n'
            "Return\n"
        )
        findings = check_build(src, [_CAT_SETBLK], "24.3.0.5")
        assert findings[0]["funcao"] == "ZZUI"

    def test_negative_instantiation_in_other_function(self) -> None:
        """var instanciada na função A não resolve chamada na função B (escopo)."""
        src = (
            "User Function A()\n"
            "  Local oBrowse := FWMarkBrowse():New()\n"
            "Return\n"
            "User Function B()\n"
            '  oBrowse:SetBlkBackColor({|| "RED"})\n'
            "Return\n"
        )
        assert check_build(src, [_CAT_SETBLK], "24.3.0.5") == []


class TestCheckBuildLintRows:
    _SRC = (
        "User Function ZZUI()\n"
        "  Local oBrowse := FWMarkBrowse():New()\n"
        '  oBrowse:SetBlkBackColor({|| "RED"})\n'
        "Return\n"
    )

    def test_maps_to_lint_row_shape(self) -> None:
        rows = check_build_lint_rows(self._SRC, [_CAT_SETBLK], "24.3.0.5", "ZZUI.prw")
        assert len(rows) == 1
        r = rows[0]
        # mesmo shape do lint_query (mergeável no output do lint)
        for key in ("arquivo", "funcao", "linha", "regra_id", "severidade", "snippet", "sugestao_fix"):
            assert key in r
        assert r["regra_id"] == "BUILD-001"
        assert r["severidade"] == "warning"
        assert r["arquivo"] == "ZZUI.prw"
        assert r["funcao"] == "ZZUI"
        assert r["linha"] == 3

    def test_empty_when_build_ok(self) -> None:
        assert check_build_lint_rows(self._SRC, [_CAT_SETBLK], "24.3.1.4", "ZZUI.prw") == []
