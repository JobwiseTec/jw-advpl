-- v0.28.0 (#96) — catálogo de INTERFACES de config PO UI (PoTableColumn,
-- PoDynamicFormField, PoPageAction, ...). Companion do `poui_componentes`
-- (que tem os bindings `p-*`): aqui ficam as propriedades do OBJETO que vai
-- dentro do binding, onde a IA mais alucina. Populada via
-- lookups/poui_interfaces.json (gerado por scripts/build_poui_interfaces.py,
-- extraído do source do po-angular; `extends` resolvido; `valores` = enum
-- da união TS ou da lista JSDoc "Valores válidos").
-- `chave` sintética ('Interface:propriedade') é a PK p/ seed_lookups (upsert).
CREATE TABLE IF NOT EXISTS poui_interfaces (
    chave          TEXT PRIMARY KEY,  -- 'PoTableColumn:type'
    interface_nome TEXT NOT NULL,     -- 'PoTableColumn', 'PoDynamicFormField', ...
    propriedade    TEXT NOT NULL,     -- 'property', 'label', 'type', ...
    tipo           TEXT,              -- tipo TS textual ('string', 'boolean', ...)
    opcional       INTEGER NOT NULL DEFAULT 1,  -- 1 = prop opcional (`?`)
    valores        TEXT NOT NULL DEFAULT '[]',  -- JSON list de valores válidos (enum) ou '[]'
    herdado_de     TEXT NOT NULL DEFAULT '',    -- interface-pai se herdado via extends; '' se próprio
    fonte          TEXT               -- arquivo .interface.ts de origem no po-angular
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_poui_interfaces_nome ON poui_interfaces(interface_nome);
