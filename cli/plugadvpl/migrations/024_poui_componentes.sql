-- v0.22.0 — catálogo de bindings PO UI (inputs/outputs `p-*`)
-- por componente Angular. Populada via lookups/poui_componentes.json.
-- `chave` sintética ('componente:kind:binding') é a PK para
-- compatibilidade com seed_lookups (upsert single-column).
CREATE TABLE IF NOT EXISTS poui_componentes (
    chave       TEXT PRIMARY KEY,  -- 'po-table:input:p-actions'
    componente  TEXT NOT NULL,     -- 'po-table', 'po-input', ...
    kind        TEXT NOT NULL,     -- 'input' | 'output'
    binding     TEXT NOT NULL,     -- 'p-actions', 'p-columns', ...
    propriedade TEXT NOT NULL,     -- nome da propriedade TypeScript
    fonte       TEXT               -- arquivo .ts de origem no repositório po-angular
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_poui_componentes_comp ON poui_componentes(componente);
