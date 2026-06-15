---
description: Roda lint plugadvpl em um arquivo (42 regras); com --target-build inclui BUILD-001 (uso de método FW*/Ms* ausente na build Protheus alvo)
disable-model-invocation: true
arguments: [arquivo]
allowed-tools: [Bash]
---

# `/plugadvpl:lint`

Roda lint plugadvpl em um arquivo ADVPL/TLPP, aplicando o catalogo de regras configurado.

## Uso

```
/plugadvpl:lint <arquivo> [--severity error|warn|info] [--regra <id>] [--target-build <build>]
```

## Opcoes

- `--severity <nivel>` — filtra por severidade minima (`error`, `warn`, `info`)
- `--regra <id>` — roda apenas a regra com este id (ex: `--regra BP-001`)
- `--target-build <build>` — inclui findings `BUILD-001`: uso de metodo `FW*`/`Ms*`/`FWBrowse` ausente na build Protheus alvo (ex: `24.3.0.5`, a RELEASE Protheus — nao a build do AppServer), via catalogo `apis_por_build`. Use quando o cliente roda uma build especifica. **Persiste no indice**: depois de passar a flag uma vez, o `lint` (sem a flag) ja roda o build-check automatico com essa build.

## Execucao

```bash
uvx plugadvpl@0.40.0 --format md lint $ARGUMENTS
```

> **Para agente IA:** prefira `--format md` (ou `--format json` se for parsear achados). Default `table` trunca a coluna `sugestao_fix` em terminais estreitos. Flag eh global, vem **antes** do subcomando.

## Regras MVP (13)

Cobertura inclui:
- RecLock sem MsUnlock
- Uso de funcoes restritas/depreciadas
- SQL Injection (concatenacao de string em query)
- Falta de aspect U_ em User Function
- Includes ausentes / nao resolvidos
- Inconsistencias MVC (hooks com retorno errado)
- Padroes Protheus (DbSeek sem Tracker, alias inexistente, ...)
- ... (ver `/plugadvpl:status` para catalogo completo carregado)

## Exemplos

- `/plugadvpl:lint src/matxxx.prw` — lint completo
- `/plugadvpl:lint src/matxxx.prw --severity error` — so erros bloqueantes
- `/plugadvpl:lint src/matxxx.prw --rule reclock-without-msunlock` — uma regra so

## Saida

Para cada finding:
- regra (id, severidade)
- arquivo:linha
- mensagem e sugestao de correcao

## Proximos passos sugeridos

- `/plugadvpl:arch <arquivo>` — entender contexto do arquivo
- `/plugadvpl:reindex <arquivo>` — apos correcao, reindex para validar
