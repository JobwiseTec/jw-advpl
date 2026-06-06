-- v0.29.0 (#99) — catálogo dos schematics oficiais do PO UI
-- (`ng generate @po-ui/...`). Para a IA recomendar o generator certo em vez de
-- montar a tela à mão e errar. Populada via lookups/poui_schematics.json
-- (gerado por scripts/build_poui_schematics.py, listando os ng-generate do
-- po-angular + caso-de-uso curado).
CREATE TABLE IF NOT EXISTS poui_schematics (
    chave     TEXT PRIMARY KEY,  -- '@po-ui/ng-templates:po-page-dynamic-table'
    generator TEXT NOT NULL,     -- 'po-page-dynamic-table'
    pacote    TEXT NOT NULL,     -- '@po-ui/ng-components' | '@po-ui/ng-templates'
    comando   TEXT NOT NULL,     -- 'ng generate @po-ui/...:...'
    gera      TEXT NOT NULL DEFAULT '',     -- o que o generator produz
    caso_uso  TEXT NOT NULL DEFAULT ''      -- quando usar
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_poui_schematics_gen ON poui_schematics(generator);
