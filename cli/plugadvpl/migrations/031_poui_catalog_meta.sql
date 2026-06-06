-- v0.29.0 (#98) — metadados do catálogo PO UI embarcado (versão do po-angular
-- de onde os catálogos `poui_componentes`/`poui_interfaces` foram extraídos).
-- Permite o lint avisar (POUI-VERSION) quando o projeto está num major diferente
-- do catálogo — bindings/props mudam entre majors (ex.: `p-hide-text-overflow`
-- removido do po-table). Populada via lookups/poui_catalog_meta.json.
CREATE TABLE IF NOT EXISTS poui_catalog_meta (
    chave TEXT PRIMARY KEY,  -- 'poui_major', 'poui_version', 'fonte'
    valor TEXT NOT NULL
) WITHOUT ROWID;
