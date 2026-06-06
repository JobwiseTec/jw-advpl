"""Testes do parser extract_poui_iface_usage (#96 passo 2)."""

from __future__ import annotations

from plugadvpl.parsing.poui import extract_poui_iface_usage


def _keys(rows: list[dict]) -> set[tuple[str, str]]:
    return {(r["interface"], r["propriedade"]) for r in rows}


class TestIfaceUsageParser:
    def test_array_de_objetos(self) -> None:
        src = "cols: PoTableColumn[] = [ { property: 'a', label: 'A' }, { field: 'b' } ];"
        k = _keys(extract_poui_iface_usage(src))
        assert ("PoTableColumn", "property") in k
        assert ("PoTableColumn", "label") in k
        assert ("PoTableColumn", "field") in k

    def test_objeto_unico(self) -> None:
        src = "act: PoPageAction = { label: 'X', action: () => this.f() };"
        k = _keys(extract_poui_iface_usage(src))
        assert ("PoPageAction", "label") in k
        assert ("PoPageAction", "action") in k

    def test_array_generico(self) -> None:
        src = "fs: Array<PoDynamicFormField> = [ { property: 'a', divider: 'X' } ];"
        k = _keys(extract_poui_iface_usage(src))
        assert ("PoDynamicFormField", "property") in k
        assert ("PoDynamicFormField", "divider") in k

    def test_objeto_aninhado_nao_captura(self) -> None:
        src = "c: PoTableColumn[] = [ { property: 'a', detail: { property: 'nested' } } ];"
        rows = extract_poui_iface_usage(src)
        # `detail` é chave direta; o `property` aninhado pertence a outra interface
        assert ("PoTableColumn", "detail") in _keys(rows)
        linhas_property = [r for r in rows if r["propriedade"] == "property"]
        assert len(linhas_property) == 1  # só o de topo, não o aninhado

    def test_corpo_de_funcao_nao_captura(self) -> None:
        # `): PoTableColumn[] {` é corpo de função, não literal anotado (sem `=`)
        src = "getCols(): PoTableColumn[] { return [ { propX: 1 } ]; }"
        assert ("PoTableColumn", "propX") not in _keys(extract_poui_iface_usage(src))

    def test_valor_de_type_capturado(self) -> None:
        src = "c: PoTableColumn[] = [ { property: 'v', type: 'currency' } ];"
        rows = extract_poui_iface_usage(src)
        tipo = next(r for r in rows if r["propriedade"] == "type")
        assert tipo["valor"] == "currency"

    def test_linha_correta(self) -> None:
        src = "x: PoTableColumn[] = [\n  { property: 'a' },\n  { field: 'b' },\n];"
        rows = extract_poui_iface_usage(src)
        field = next(r for r in rows if r["propriedade"] == "field")
        assert field["linha"] == 3

    def test_sem_interface_po_nada(self) -> None:
        src = "x: MyCustomType[] = [ { qualquer: 1 } ];"
        assert extract_poui_iface_usage(src) == []

    def test_string_com_chave_falsa_nao_captura(self) -> None:
        # `http:` dentro de string não é chave
        src = "c: PoTableColumn[] = [ { property: 'http://x.com/a' } ];"
        k = _keys(extract_poui_iface_usage(src))
        assert ("PoTableColumn", "property") in k
        assert ("PoTableColumn", "http") not in k
