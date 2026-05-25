# Troca Quente: como restartar o AppServer Protheus e confirmar que voltou — em 1 comando

> **Sub-título:** Compilou um fonte. Precisa testar. Aí começa o ritual: rodar o `restart-totvs.bat`, esperar, dar `curl` pra ver se subiu, dar `curl` de novo porque não subiu ainda, abrir SmartClient... O `plugadvpl tq` automatiza esse loop em 1 comando com healthcheck HTTP real.

## O problema real

Loop de desenvolvimento típico em ADVPL:

```
edita FONTE.PRW
↓
compila (TDS-VSCode ou plugadvpl compile)
↓
restart manual do AppServer (.bat / systemctl / Docker)
↓
"será que voltou já?" → curl http://protheus:8181/rest
↓
HTTP 000 (connection refused) → ainda não
↓
espera 10s, tenta de novo
↓
HTTP 000 → espera mais
↓
HTTP 200 → \o/ pode testar
↓
testa, não funciona, edita de novo
↓
[REPETE TODA A SEQUÊNCIA]
```

Em uma sessão de debug de 1 hora, você gasta tipicamente **15-20 minutos** só nesse loop de "restart + esperar voltar". Multiplica por 5 sessões na semana → **~1.5 horas/semana de overhead** que vira **dezenas de horas/ano**.

E pior: cada restart manual tira você do contexto. Você estava no flow debugando um problema, vai esperar 30s, mente desvia pra outra coisa, perdeu o contexto, recomeça do zero quando volta.

## A solução

O **`plugadvpl tq`** (Troca Quente) automatiza o passo "restart + healthcheck" em 1 comando:

```bash
plugadvpl tq --use-server Local --port 8019
```

O que faz:

1. Lê o `restart_cmd` configurado pro server (pode ser `.bat`, `systemctl`, `docker restart`, qualquer coisa shell)
2. Executa via `subprocess`
3. Captura exit code + stderr
4. Inicia loop de healthcheck HTTP: GET `/` na porta REST, espera status `200/401/404`
5. Retorna table/JSON estruturado com `ok`, durações em ms, attempts, total
6. Exit code 0 = up, 1 = falha

**Encadeamento típico** (o flow que muda tudo):

```bash
plugadvpl compile --use-server Local --all-envs FONTE.PRW && \
plugadvpl tq --use-server Local --port 8019
```

Compile pros N envs + restart + healthcheck. Quando o comando volta, o AppServer está 100% pronto pra teste. Você sabe disso porque o exit code é 0 + HTTP 200 foi recebido.

### Setup (2 comandos, 1x na vida)

```bash
# 1. Configura o restart_cmd no server do registry global
plugadvpl compile --set-restart-cmd Local --cmd "cmd.exe /c gaps\\restart-totvs.bat"

# (ou Linux)
plugadvpl compile --set-restart-cmd Local --cmd "sudo systemctl restart totvs-appserver12"

# (ou Docker)
plugadvpl compile --set-restart-cmd Local --cmd "docker restart totvs-protheus"
```

O `restart_cmd` mora em `~/.plugadvpl/servers.json`, no campo novo `restart_cmd` do `Server` dataclass.

### Uso

```bash
plugadvpl tq --use-server Local                              # restart + healthcheck completo
plugadvpl tq --use-server Local --port 8019                  # port REST diferente do TCP advpls
plugadvpl tq --use-server Local --timeout 120                # AppServer lento, da mais tempo
plugadvpl tq --use-server Local --no-healthcheck             # so restart, sem esperar voltar
plugadvpl tq --use-server Local --dry-run                    # mostra o que faria sem executar
```

### Output

```
tq (Local)
┌──────┬─────────────┬────────────────────┬─────────────────────┬──────────────────────┬──────────────────────┬──────────────────────┬───────┐
│ ok   │ server_name │ restart_exit_code  │ restart_duration_ms │ healthcheck_status   │ healthcheck_attempts │ total_duration_ms    │ error │
├──────┼─────────────┼────────────────────┼─────────────────────┼──────────────────────┼──────────────────────┼──────────────────────┼───────┤
│ True │ Local       │ 0                  │ 52671               │ up                   │ 17                   │ 55686                │       │
└──────┴─────────────┴────────────────────┴─────────────────────┴──────────────────────┴──────────────────────┴──────────────────────┴───────┘
```

JSON estruturado com `--format json`, consumível por CI.

## Detalhes técnicos importantes

### Healthcheck HTTP (não só TCP)

A diferença crítica que economiza horas de "false positive":

**TCP ping (insuficiente):** verifica se a porta abre. Mas a porta abre **antes** do REST estar pronto — o processo do AppServer iniciou, escutando, mas o WSRESTFUL ainda está carregando. Resultado: você acha que subiu, mas o primeiro request real volta erro.

**HTTP probe (o que `tq` faz):** `GET /` via `http.client.HTTPConnection`. Considera AppServer up SÓ quando responde HTTP `200`, `401` ou `404` (algum status REST válido).

E o detalhe ainda mais sutil:

**`5xx` no healthcheck NÃO conta como up.** Em build 7.00.240223P observei na prática: porta abre, REST framework retorna 503 por uns segundos enquanto carrega, depois passa a retornar 200. Se considerasse 5xx como "up", você testaria o serviço num momento que ele ainda não está pronto. O `tq` continua tentando até pegar 200/401/404 ou timeout.

### `--port` pra portas diferentes

Caso real do meu ambiente: AppServer Local tem:
- TCP `advpls` (compile via TCP) na porta `1234`
- REST na porta `8019`

O `--port 8019` no `tq` sobrescreve o port do healthcheck mas preserva o `server.port` no registry pra outras chamadas. Sem ambiguidade.

### Timeout configurável

Default 60s. Se o restart envolve UAC (Windows com `runas`), Docker pull de imagem nova, ou healthcheck inicial de schema longo, aumenta com `--timeout 180`.

## Ganhos concretos

### Em desenvolvimento local

- **Loop dev compile → teste:** caiu de "edita + compile + restart manual + curl loop" pra "edita + `compile --all-envs && tq`". Lit literally 1 comando encadeado.
- **Sem perda de contexto:** você não desvia atenção pro restart. O comando rodando é background mental.
- **Healthcheck confiável:** quando volta `ok=True`, o AppServer está PRONTO. Não é "TCP abre".

### Em CI/CD

- `exit_code 0` = up, `1` = falha. Pipeline para se quebrar.
- Output JSON `--format json` documenta exatamente quanto tempo cada etapa levou — observabilidade out of the box.
- Encadeamento com `compile --all-envs` faz sentido em pipeline de patch: testa, compila, restart, healthcheck, retorna OK.

### Em consultoria / multi-ambiente

- Cliente A usa `.bat`, cliente B usa `systemctl`, cliente C usa `docker restart` — cada um configura uma vez no `restart_cmd` do seu server, depois é só `--use-server X` que funciona.

## O que `tq` NÃO faz (escopo MVP cortado)

Honestidade upfront sobre o escopo atual:

- ❌ **Versionamento de RPO** — `tq` NÃO promove o `custom.rpo` ativo pra pasta dated `apo/<env>/rpo_versions/<ts>/`. Pra MVP local, `compile --all-envs` já copia o RPO pros N envs.
- ❌ **Edição de `appserver.ini`** — não muda nada nos `.ini`. O RPO sobrescreve o ativo, AppServer pega no restart.
- ❌ **Lock file** — sem proteção contra 2 devs rodando `tq` no mesmo env simultâneo (local, 1 dev — sem concorrência).
- ❌ **`--confirm-prod`** — sem PROD-safety. Pra MVP local, não tem PROD.
- ❌ **Rollback automático** — se restart falhar, `tq` reporta erro e sai. User decide.

Esses ficam pra a versão robusta (issue #5 do roadmap) quando precisar de TQ pra produção real. Pra teste local, o MVP entrega o que importa: **restart + healthcheck em 1 comando**.

## Quanto tempo economiza, na prática

Ambiente local, base de teste:

- Restart manual + curl loop = **~30-45s por iteração** + perda de foco (intangível)
- `plugadvpl tq` = **~55s elapsed**, **0 segundos de atenção do dev** (vai rodar enquanto você lê o próximo PR)

Em uma sessão de debug de 2 horas com 10 iterações: **5-7 minutos economizados de tempo real**, mas o mais valioso é o **foco mantido** — você não vira pro Slack/Twitter entre restarts, fica no problema.

## Open-source, MIT, sem telemetria

Tudo Python stdlib (`subprocess`, `http.client`, `socket`, `time`). Sem deps novas. 8 testes unit + 6 integration cobrindo happy path + edge cases (restart vazio, exit non-zero, healthcheck timeout, 5xx false positive, no-healthcheck, port override).

→ **PyPI:** [pypi.org/project/plugadvpl](https://pypi.org/project/plugadvpl)
→ **GitHub:** [github.com/JoniPraia/plugadvpl](https://github.com/JoniPraia/plugadvpl)
→ **Spec:** `docs/superpowers/specs/2026-05-25-plugadvpl-tq-mvp-design.md` (transparência total do design)

#ADVPL #TLPP #Protheus #TOTVS #DevOps #HotSwap #OpenSource
