-- v0.29.0 (#97) — pacote npm por componente + imports @po-ui/* do projeto.
-- Base da regra POUI-IMPORT (componente usado cujo pacote não é importado no
-- projeto — ex.: <po-page-dynamic-table> de @po-ui/ng-templates usado mas só
-- @po-ui/ng-components importado).

-- (a) pacote por componente no catálogo (derivado do `fonte` em build_poui_catalog).
ALTER TABLE poui_componentes ADD COLUMN pacote TEXT NOT NULL DEFAULT '';

-- (b) imports @po-ui/* extraídos dos .ts do projeto (via ingest-poui).
CREATE TABLE IF NOT EXISTS poui_imports (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    caminho TEXT NOT NULL,   -- .ts que faz o import (absoluto)
    linha   INTEGER NOT NULL DEFAULT 1,
    pacote  TEXT NOT NULL    -- '@po-ui/ng-components', '@po-ui/ng-templates', ...
);

CREATE INDEX IF NOT EXISTS idx_poui_imports_pacote ON poui_imports(pacote);
