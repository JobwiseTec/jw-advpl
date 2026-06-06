-- v0.28.0 (#96 passo 2) — uso de interfaces de config PO UI em fontes .ts.
-- Populada por ingest-poui (extract_poui_iface_usage): para cada object-literal
-- tipado `Po*` (ex.: `cols: PoTableColumn[] = [{...}]`), uma linha por chave
-- usada. Base da regra de lint POUI-IFACE (chave inexistente / valor fora do
-- enum), cruzando com o catálogo `poui_interfaces`.
CREATE TABLE IF NOT EXISTS poui_iface_uso (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    caminho        TEXT NOT NULL,     -- .ts onde o objeto é usado (absoluto)
    linha          INTEGER NOT NULL DEFAULT 1,
    interface_nome TEXT NOT NULL,     -- 'PoTableColumn', 'PoDynamicFormField', ...
    propriedade    TEXT NOT NULL,     -- chave usada no objeto literal
    valor          TEXT NOT NULL DEFAULT ''  -- valor string literal (p/ checar enum, ex.: type)
);

CREATE INDEX IF NOT EXISTS idx_poui_iface_uso_iface ON poui_iface_uso(interface_nome);
