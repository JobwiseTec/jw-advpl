# POUI (PO UI) — Pesquisa + Plano de Suporte no plugadvpl

**Status:** pesquisa concluída (multi-fonte, verificada) · plano **proposto** · pendente aprovação do autor
**Data:** 2026-06-03
**Motivação:** temos cliente que usa POUI intensivamente; queremos que o plugadvpl **ingira e entenda** projetos POUI (como já faz com ADVPL/TLPP), + **skills** de IA.

> Documento em 2 partes: **(1) como o POUI funciona** (fatos verificados, com fontes) e **(2) plano de implementação** no plugadvpl (ingestão + skills, em fases, seguindo o fluxo research → spec → aprovação → código). Nada de código antes do aceite.

---

## Parte 1 — Como o POUI funciona

### 1.1 O que é (✅ confirmado)

**PO UI** é a biblioteca de componentes **Angular oficial da TOTVS**, open-source (**MIT**), num monorepo único em [`github.com/po-ui/po-angular`](https://github.com/po-ui/po-angular), com portal/docs em [po-ui.io](https://po-ui.io). Histórico de nome: **THF (TOTVS HTML Framework) → Portinari → PO UI**.

Distribuída como uma **família `@po-ui/*` mono-versionada** (todos os pacotes na mesma versão, em lockstep):

| Pacote | Papel |
|---|---|
| `@po-ui/ng-components` | **core** — componentes base (`po-button`, `po-table`, `po-field`, `po-page`, …) |
| `@po-ui/ng-templates` | **templates** — telas de alto nível: **`PoPageDynamicTable`/`PoPageDynamicEdit`**, `PoPageLogin`, `PoModalPasswordRecovery`, … |
| `@po-ui/style` | tema/tokens CSS |
| `@po-ui/ng-schematics` | schematics (`ng add`/`ng generate`) |
| `@po-ui/ng-code-editor`, `@po-ui/ng-sync`, `@po-ui/ng-storage` | editor, sync offline, storage |

`@po-ui/ng-components` **exact-pina** (`21.18.0`, sem `^`/`~`) o `@po-ui/style` e o `@po-ui/ng-schematics`. **Implicação de ingestão:** **uma única dep `@po-ui/*` no `package.json` já identifica a família inteira + a versão.**

### 1.2 Versionamento — major npm = major do Angular (✅ confirmado)

A versão npm do PO UI **rastreia o major do Angular**: `@po-ui/ng-components@21.18.0` → **Angular `^21`** (peerDependencies pinam `@angular/*`, `@angular/cdk`, `@angular-devkit/schematics` em `^21`; `rxjs ~7.8.1`, `zone.js ~0.15.0`). Branches LTS: `20.x → Angular ^20`, `19.x → Angular ^19`.

**Implicação:** o major do `@po-ui` de um projeto **dá diretamente o major do Angular exigido** → análise de compatibilidade/upgrade é trivial e de alto valor. ⚠️ **Versão muda rápido** (21.18.0 saiu 2026-06-01) → detectar **dinamicamente** do `package.json`/registry, **nunca hardcodar**.

### 1.3 Estrutura de um projeto POUI (Angular CLI app)

```
meu-app/
├── package.json          ← deps @po-ui/* + @angular/*  [alto sinal]
├── angular.json          ← build, assets, styles (@po-ui/style)
├── tsconfig.json
└── src/app/
    ├── app.module.ts     ← imports PoModule / PoTemplatesModule, HttpClientModule
    ├── *.component.ts     ← @Input('p-...')/@Output('p-...'), PoPageDynamic*
    ├── *.component.html   ← <po-*> tags + bindings [p-...]
    └── *.service.ts       ← HttpClient → APIs REST (Protheus)
```

- **`ng add @po-ui/ng-components`** configura tema + importa `HttpClientModule`; **`ng add @po-ui/ng-templates`** registra `PoTemplatesModules` no `app.module`. (✅ confirmado no README oficial.)
- **Convenção de binding `p-`** (de-facto): `<po-input p-label="Nome" [p-required]="true">`, eventos `(p-change)`. ⚠️ *amplamente conhecida mas a fonte específica falhou na verificação — confirmar contra um projeto real na implementação.*

### 1.4 A ponte com o Protheus — `PoPageDynamic*` + REST (✅ **re-confirmado via raw source**)

Este é **o ponto de maior valor** para nós. Os templates `PoPageDynamicTable`/`PoPageDynamicEdit` consomem um backend REST via `PoPageDynamicService`:

- **endpoint** configurável (`configServiceApi({ endpoint, metadata })`; tipicamente vindo de `route.data.serviceApi`);
- **CRUD → verbos HTTP:** `getResources`/`getResource` = **GET**, `createResource` = **POST**, `updateResource` = **PUT**, `deleteResource`/`deleteResources` = **DELETE**;
- **metadata endpoint:** `{endpoint}/metadata?type={type}&version={version}`;
- header padrão `X-PO-SCREEN-LOCK: true`.

→ Na prática, esse `endpoint` aponta para uma **API REST do Protheus** (TLPP/ADVPL `WSRESTFUL` ou `FWRestModel`). **O plugadvpl já entende esse lado de trás** (`ingest-rest` + dicionário). Cruzar o **datasource do POUI (front)** com o **endpoint REST do Protheus (back)** é a **rastreabilidade ponta-a-ponta** que nenhuma ferramenta entrega hoje. Existe inclusive página TDN oficial *"Nova interface do Protheus com PO UI"*.

### 1.5 Tooling existente (✅/⚠️)

- **Schematics oficiais** (`ng add`/`ng generate`): o `collection.json` ([raw](https://raw.githubusercontent.com/po-ui/po-angular/master/projects/ui/schematics/collection.json)) lista os scaffolds **ingeríveis**: `ng-add` + `sidemenu`, `po-page-list`, `po-page-edit`, `po-page-detail`, `po-page-default` (cada um com `schema.json`). ✅
- **`@po-ui/ng-tslint`** — regras de lint (TSLint, legado/deprecated em favor de ESLint). Primary source no npm.
- Portal **po-ui.io** (docs SPA — **não fetchável** server-side, retorna shell Angular).
- ⚠️ **Não há catálogo JSON público de API dos componentes** no caminho óbvio (`po-portal/.../api-list.json` → **404**). A metadata de API (props/events) é gerada do **source (JSDoc)** → ingerir isso exige parsing do `po-angular` ou **catálogo curado** (não um download simples).

### 1.6 O que análise estática deveria flagar (pitfalls)

- `@po-ui` major **incompatível** com o Angular do projeto (upgrade/compat). ✅ acionável.
- **Breaking changes** entre majors (guias de migração existem no repo).
- Binding `p-*` inexistente/deprecado por versão; componente removido. *(precisa catálogo — fase posterior.)*
- Acessibilidade/performance — *lead não verificado.*

### 1.7 Fontes

**Primárias verificadas:** [npm registry @po-ui/ng-components](https://registry.npmjs.org/@po-ui/ng-components) · [@po-ui/ng-schematics](https://www.npmjs.com/package/@po-ui/ng-schematics) · [po-angular (GitHub)](https://github.com/po-ui/po-angular) · [collection.json (raw)](https://raw.githubusercontent.com/po-ui/po-angular/master/projects/ui/schematics/collection.json) · [po-page-dynamic.service.ts (raw)](https://raw.githubusercontent.com/po-ui/po-angular/master/projects/templates/src/lib/services/po-page-dynamic/po-page-dynamic.service.ts) · [TDN — Nova interface do Protheus com PO UI](https://tdn.totvs.com/display/public/framework/Nova+interface+do+Protheus+com+PO+UI) · [@po-ui/ng-tslint](https://www.npmjs.com/package/@po-ui/ng-tslint).
**Leads a re-verificar contra source:** catálogo de API de componentes (JSDoc/Dgeni), convenção `p-`, `llms.txt`, "60+ componentes", schematic de `ng update`.

---

## Parte 2 — Plano de implementação no plugadvpl

### 2.1 Tensão de design: regex-strip vs parser TS real

O plugadvpl é **regex *strip-first*, Python, ADVPL-cêntrico** — não usa tokenizer/AST de verdade. POUI é **TypeScript/Angular** (tem AST real via `tsc`/`ts-morph`).

**Decisão proposta:** começar **regex-strip** (barato, no estilo da casa) sobre os artefatos de **alto sinal e baixa ambiguidade** — `package.json` (é JSON, parse direto), `.html` (`<po-*>` + `p-*`), `.ts` (achar `PoPageDynamic*` + `serviceApi`/`endpoint`). **Não precisa de AST TS pro MVP.** Parser TS real (`ts-morph` via subprocess Node, ou `tree-sitter`) fica como **fase futura** só se a precisão exigir.

### 2.2 Fases

#### Fase 1 — Detecção + compatibilidade (barato, alto valor)
- **`ingest-poui <dir>`**: lê `package.json` (JSON) → detecta `@po-ui/*`, versão, **major do Angular exigido**; lê `angular.json` e `app.module.ts` (módulos Po importados).
- Schema: tabela **`poui_projetos`** (`path`, `versao_poui`, `angular_major`, `pacotes_json`, `hash`, `mtime`) — modelo de `ini_files`.
- **Audit/skill:** flag `@po-ui` ↔ Angular incompatível, versão muito atrás da latest (consulta registry opcional), pacotes `@po-ui/*` em versões divergentes (quebra o lockstep).

#### Fase 2 — Uso de componentes + a ponte REST (o diferencial)
- **Parser de templates `.html`** (regex strip-first): extrai `<po-*>` + bindings `[p-*]`/`(p-*)`. Tabela **`poui_componentes_uso`** (`arquivo`, `linha`, `componente`, `bindings_json`).
- **Detector de datasource**: acha `PoPageDynamic*` + extrai o `endpoint`/`serviceApi` (de `route.data` e de property). Tabela **`poui_datasources`** (`arquivo`, `linha`, `componente`, `endpoint`, `verbos`).
- **🔗 Cross-link com `ingest-rest`:** casa o `endpoint` do POUI com a **API REST do Protheus já ingerida** → query "essa tela POUI consome qual `WSRESTFUL`/TLPP?" e o reverso. **É o recurso-assinatura.**

#### Fase 3 — Catálogo de componentes + lint
- **Catálogo curado `poui_componentes`** (lookups, migration + seed JSON) com props/events por componente e a versão em que existem — análogo ao `apis_por_build`. Fonte: extrair do source `po-angular` (script) ou curar por lote.
- **Lint rules POUI**: binding inexistente, prop deprecada por major, componente removido, datasource sem tratamento de erro. Guard de consistência (espelha `test_ini_rules_consistency`).

### 2.3 Skills
- **Knowledge:** `poui-fundamentals` (família @po-ui, versionamento, estrutura), `poui-page-dynamic` (templates + REST), **`poui-protheus-bridge`** (front POUI ↔ back Protheus REST/TLPP).
- **Command (wrappers):** `ingest-poui`, `poui-datasources`, `poui-audit`.

### 2.4 Roteiro técnico (espelha `architecture.md` §"nova extração")
regex no parser → função `_from_*` → `parse_*` → tabela/migration → testes (positive/comentário/string) → `query.py` + subcommand Typer (pt-BR) → skill → `docs/cli-reference.md` + `docs/schema.md` → ruff/mypy/pytest → Conventional Commit.

### 2.5 Decisões

1. **Escopo:** ✅ **Fase 1+2+3** (detecção/compat + ponte REST + catálogo de componentes & lint). Aprovado 2026-06-03.
2. **Onde vive:** ✅ **Dentro do `plugadvpl`** — reusa DB/CLI/skills/CI; a ponte REST fica ao lado do `ingest-rest`. Aprovado 2026-06-03.

**Ainda em aberto (decidir no plano detalhado):**

3. **Catálogo de componentes (Fase 3):** curar à mão, extrair por script do source `po-angular`, ou raspar docs? *Sem catálogo JSON oficial → é trabalho real.* — proposta: **extrair por script** do source (`@Input('p-...')`/`@Output`) como seed inicial + curadoria incremental (modelo `apis_por_build`).
4. **Calibração:** validar o parser contra **um projeto POUI real** (inspeção local apenas; **nunca** referenciar cliente em commit/fixture/doc — fixtures sintéticas com prefixo neutro).
5. **Parser TS:** regex-strip no MVP (proposto), AST real (`ts-morph`/`tree-sitter`) só se a precisão exigir.

### 2.6 Riscos
- **Version churn** (POUI lança quase semanal) → detectar dinâmico, nunca hardcode.
- **Sem catálogo de API oficial** → metadata de componente é o pedaço caro (Fase 3).
- **Regex em TS/Angular** tem teto de precisão (binding em multi-linha, computed) → se doer, escalar pra AST.
- **Escopo:** POUI puxa o plugadvpl pra fora do mundo ADVPL — alinhar visão de produto antes de Fase 2+.

---

## 2.7 Refinamentos pós-validação (2026-06-03)

### Validação da Fase 1 em projeto real
`ingest-poui` rodado contra um projeto POUI **real** (fornecido p/ inspeção local; sem dado identificável): detectou corretamente **PO UI 15 + Angular 15, compatível**, 2 pacotes `@po-ui/*`. Dois aprendizados:
- **Cliente fica em major antigo** (15, não o 21 atual) → a análise de **compat/upgrade da Fase 1 é diretamente útil** ("você está no 15, latest é 21").
- O projeto é **full-stack**: frontend POUI **+ backend `.tlpp` REST** (Protheus) lado a lado → é o **alvo de calibração ideal da Fase 2** (cruzar datasource POUI ↔ endpoint TLPP, ambos já ingeríveis pelo plugadvpl).

### Prior art — `claude-skills-poui` (plugin Claude Code community)
Existe um plugin Claude focado em PO UI ([claude-skills-poui](https://github.com/danielmontagna86-source/claude-skills-poui)). Ele é o **lado skill/prompt**: regras anti-alucinação ("não invente input/output/tipo/método") + **referências markdown curadas à mão** por componente (ex: `po-table-api.md` com tabelas `input | binding | purpose`). O roadmap dele **lista explicitamente como lacunas** justo o que o plugadvpl É: extração automática de API do source, validação de conformidade, **detecção de anti-pattern em projeto existente (estático)**, mapeamento de dependências, e *"alimentar as skills com dados ingeridos"*. **Forte validação de direção + diferenciação:** somos a camada de ingestão/análise que eles não têm.

**Refinamentos concretos que isso traz pra Fase 3:**
- **Schema do catálogo `poui_componentes`** (antes vago) agora concreto, no formato deles (provado): por componente, `inputs:[{name:"p-columns", type:"PoTableColumn[]", binding:"[p-columns]", purpose}]` + `outputs:[{name:"p-selected", event_type, binding:"(p-selected)"}]`. Seed extraído do source `po-angular` (`@Input('p-...')`/`@Output`), curado incremental.
- **Lint rules POUI (Fase 3)** ganham alvos concretos do "wishlist" deles: `POUI-PROP` (binding `p-*` inexistente na API da versão), `POUI-TYPE` (tipo de coluna inconsistente), `POUI-VIEWCHILD` (método inventado no `ViewChild`), `POUI-CTX` (padrão não bate com a categoria de tela).
- **Sinergia possível:** o `ingest-poui` pode **gerar/atualizar** as referências que uma skill anti-alucinação consome — reduzindo a manutenção manual que o roadmap deles assume. (Avaliar licença/credito antes de reusar conteúdo deles.)

---

## Próximo passo
Fase 1 **implementada + validada** (branch `feat/poui-fase1`). Fase 2 (ponte REST, calibrada no projeto real full-stack) e Fase 3 (catálogo + lint, refinados acima) ganham planos próprios.
