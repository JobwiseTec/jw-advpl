-- Migration 015 — Universo 8 (Menus): MPMENU completo (6 tabelas)
--
-- Absorve as 6 tabelas do schema MPMENU do Protheus que o COLETADB.tlpp
-- emite. Schema relacional: MENU 1→N ITEM ←FK→ FUNCTION, ITEM 1→N I18N
-- (descricoes traduzidas), ITEM 1→N KEY_WORDS (busca).
--
-- Casos de uso destravados:
--   - "Em qual menu aparece a funcao TCFA004?" → JOIN function ← item → menu
--   - "Quais menus o modulo SIGAFAT tem?" → menu WHERE module = '18'
--   - "Quais palavras-chave fazem o item X aparecer na busca?" → key_words

-- =============================================================================
-- MPMENU_MENU — definicoes de menu (raiz da hierarquia)
-- =============================================================================
-- Ex: SIGATCF (Ativo Fixo), SIGAFAT (Faturamento), etc. Cada menu tem
-- um arquivo .XNU em D:\TOTVS\protheus\system com a hierarquia compilada.
CREATE TABLE IF NOT EXISTS mpmenu_menu (
    id                     TEXT PRIMARY KEY,    -- M_ID (UUID hex 32)
    nome                   TEXT DEFAULT '',     -- M_NAME (ex: SIGATCF)
    versao                 TEXT DEFAULT '',     -- M_VERSION
    modulo                 TEXT DEFAULT '',     -- M_MODULE (codigo 18, 05, ...)
    md5_arquivo            TEXT DEFAULT '',     -- M_MD5_FILE
    is_default             TEXT DEFAULT '',     -- M_DEFAULT (1=padrao)
    arquivo_menu           TEXT DEFAULT ''      -- M_ARQMENU (ex: \SYSTEM\SIGATCF.XNU)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_mpmenu_menu_nome ON mpmenu_menu(nome);
CREATE INDEX IF NOT EXISTS idx_mpmenu_menu_modulo ON mpmenu_menu(modulo);

-- =============================================================================
-- MPMENU_FUNCTION — funcoes ADVPL referenciadas pelos itens de menu
-- =============================================================================
-- Cada funcao tem id UUID e nome (ex: TCFA004, MATA010). Item de menu
-- referencia function via I_ID_FUNC.
CREATE TABLE IF NOT EXISTS mpmenu_function (
    id                     TEXT PRIMARY KEY,    -- F_ID (UUID hex 32)
    funcao                 TEXT DEFAULT '',     -- F_FUNCTION (ex: TCFA004)
    is_default             TEXT DEFAULT ''      -- F_DEFAULT
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_mpmenu_function_funcao ON mpmenu_function(funcao);

-- =============================================================================
-- MPMENU_ITEM — items individuais dentro de um menu (estrutura hierarquica)
-- =============================================================================
-- Cada item pode ser folha (com I_ID_FUNC apontando pra function) ou
-- container (com filhos via I_FATHER apontando pra outro item). I_ORDER
-- define ordem visual entre irmaos.
CREATE TABLE IF NOT EXISTS mpmenu_item (
    id                     TEXT PRIMARY KEY,    -- I_ID (UUID hex 32)
    id_menu                TEXT DEFAULT '',     -- I_ID_MENU (FK -> mpmenu_menu.id)
    id_pai                 TEXT DEFAULT '',     -- I_FATHER (FK -> mpmenu_item.id, self)
    ordem                  TEXT DEFAULT '',     -- I_ORDER (visual)
    item_id_legado         TEXT DEFAULT '',     -- I_ITEMID (ex: A180000001)
    tp_menu                TEXT DEFAULT '',     -- I_TP_MENU (tipo)
    status                 TEXT DEFAULT '',     -- I_STATUS (1=Ativo)
    id_funcao              TEXT DEFAULT '',     -- I_ID_FUNC (FK -> mpmenu_function.id, NULL = container)
    res_name               TEXT DEFAULT '',     -- I_RESNAME
    tipo                   TEXT DEFAULT '',     -- I_TYPE
    tabelas                TEXT DEFAULT '',     -- I_TABLES
    acesso                 TEXT DEFAULT '',     -- I_ACCESS
    proprietario           TEXT DEFAULT '',     -- I_OWNER
    modulo                 TEXT DEFAULT '',     -- I_MODULE
    is_default             TEXT DEFAULT ''      -- I_DEFAULT
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_mpmenu_item_menu ON mpmenu_item(id_menu);
CREATE INDEX IF NOT EXISTS idx_mpmenu_item_pai  ON mpmenu_item(id_pai);
CREATE INDEX IF NOT EXISTS idx_mpmenu_item_func ON mpmenu_item(id_funcao);

-- =============================================================================
-- MPMENU_I18N — descricoes traduzidas (3 idiomas)
-- =============================================================================
-- N_PAREN_TP indica o tipo do parent: 1=menu, 2=item, 3=function.
-- N_PAREN_ID aponta pro UUID correspondente. N_LANG: 1=PT, 2=ES, 3=EN
-- (heuristica baseada no smoke -- pode variar por instalacao).
CREATE TABLE IF NOT EXISTS mpmenu_i18n (
    parent_tipo            TEXT NOT NULL,       -- N_PAREN_TP (1=menu/2=item/3=function)
    parent_id              TEXT NOT NULL,       -- N_PAREN_ID (UUID do menu/item/function)
    idioma                 TEXT NOT NULL,       -- N_LANG (1/2/3)
    descricao              TEXT DEFAULT '',     -- N_DESC
    is_default             TEXT DEFAULT '',     -- N_DEFAULT
    PRIMARY KEY (parent_tipo, parent_id, idioma)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_mpmenu_i18n_parent ON mpmenu_i18n(parent_id);

-- =============================================================================
-- MPMENU_KEY_WORDS — palavras-chave de busca dos items
-- =============================================================================
-- Texto livre que permite o usuario achar um item de menu pela busca rapida.
-- Ex: item de cadastro de cliente tem "Licitante,empresa,comprador" como
-- palavras-chave em PT.
CREATE TABLE IF NOT EXISTS mpmenu_key_words (
    id_item                TEXT NOT NULL,       -- K_ID_ITEM (FK -> mpmenu_item.id)
    idioma                 TEXT NOT NULL,       -- K_LANG
    palavras_chave         TEXT DEFAULT '',     -- K_DESC (comma-separated)
    is_default             TEXT DEFAULT '',     -- K_DEFAULT
    PRIMARY KEY (id_item, idioma)
) WITHOUT ROWID;

-- =============================================================================
-- MPMENU_RW — leitura/escrita por idioma (legenda?)
-- =============================================================================
-- Tabela pequena (sample do smoke: 1 row). Funcao exata depende da
-- documentacao TOTVS — preservamos as colunas sem assumir semantica.
CREATE TABLE IF NOT EXISTS mpmenu_rw (
    idioma                 TEXT NOT NULL,       -- R_LANG
    descricao              TEXT DEFAULT '',     -- R_DESC
    is_default             TEXT DEFAULT '',     -- R_DEFAULT
    PRIMARY KEY (idioma)
) WITHOUT ROWID;
