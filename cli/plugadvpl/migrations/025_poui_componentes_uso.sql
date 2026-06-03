-- v0.23.0 — uso de componentes PO UI em templates HTML (po-*, p-*)
-- Populada por `ingest-poui` ao varrer .html do projeto.
-- Cruzada com `poui_componentes` (catálogo) via `poui-lint`.
CREATE TABLE IF NOT EXISTS poui_componentes_uso (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    caminho     TEXT NOT NULL,     -- .html onde o componente é usado (absoluto)
    linha       INTEGER NOT NULL DEFAULT 1,
    componente  TEXT NOT NULL,     -- 'po-button', 'po-table', ...
    binding     TEXT NOT NULL,     -- 'p-label', 'p-click', ...
    kind        TEXT NOT NULL      -- 'input' | 'output'
);

CREATE INDEX IF NOT EXISTS idx_poui_uso_comp ON poui_componentes_uso(componente);
