# RELATORIO-AVISO-CHAT-ATIVO-01

**CONCLUSÃO PRIMEIRO:** FECHO DO AVISO NO CHAT ATIVO DO OPERADOR FUNCIONANDO E PROVADO AO VIVO — 18/18 testes verdes + E2E real no gateway vivo: a tool entregou a mensagem na sessão de chat TUI ativa (HTTP 200) e o operador a viu no chat (persistida em state.db às 22:16:48 BRT). Evento `mission_end` appendo no spool do bus em cada entrega (spool:true). Bug worker-vs-root do tab_reap reconfirmado ao vivo (worker `herdr tab list` = 0 abas; root = 4 abas). Pendência de supervisor: handler `mission_end` no event_bus (comandos prontos abaixo).

## Entregas (branch `aviso-chat-ativo-01`, worktree `/home/worker/wt-aviso-chat-ativo-01`)

- `scripts/vigia_chat.sh` — modo `--send` reescrito (AVISO-CHAT-ATIVO-01):
  1. **Sessão dinâmica** (nunca fixa): override `VIGIA_CHAT_SESSION` (E2E/testes) → `/root/.hermes/sessions.json` (gateway, `write_sessions_json: true`) → fallback `/root/.hermes/runtime/active_sessions.json` (leases vivos do gateway). Escolhe a de maior atividade, só `surface` tui/chat, **gh-notifications PROIBIDO** (no resolver e no override). Parser tolerante a formatos (`sessions`/`entries`/lista; `session_id|id|sessionId|live_session_id`).
  2. **POST** `http://127.0.0.1:8642/v1/chat/completions` com `Authorization: Bearer` de `/opt/eng-mcp-release-data/credentials/hermes-notify-api-key` (nunca logado), `X-Hermes-Session-Id: <sessão ativa>`, body pequeno 1 linha (missionId, veredito, custo, turnos).
  3. **Falha tipada honesta**: `delivered:false` + `motivo` (`sessao_ativa_inexistente`, `ROTA_OFFLINE`, `SEM_ROTA`, `ja_enviado`, `dedupe_60s`), **exit 0 sempre**.
  4. **Rate-limit local**: máx 1 aviso por missão + dedupe 60s (`VIGIA_CHAT_RATELIMIT`, default `/tmp/vigia-chat-ratelimit.json`).
  5. **Log**: `/tmp/vigia-chat-<id>.log` (`VIGIA_CHAT_LOGDIR` p/ testes).
  6. **Timeout curl** 60s (`VIGIA_CHAT_TIMEOUT`) — o gateway demora >15s a responder o POST (dispara turno na sessão); com 15s o curl dava 000 mesmo entregando.
- **Escopo adicional (ordem 22:15 BRT)**: após entrega (2xx), appenda evento genérico no spool do mission-event-bus `/opt/mission-events/spool.jsonl` (schema do `event_bus.py`: `ts`, `source: vigia_chat`, `kind: mission_end`, `missionId`, `pane`, `session_id`, `msg`, `data.action=tab_reap`). Falha de append não quebra a tool (`spool:false` honesto); sem entrega não appenda. **Não editado**: `event_bus.py`, guard, core do bus.
- `tests/test_vigia_chat.py` — pytest (NÃO unittest), 18 casos: gateway FAKE (`http.server` em thread + tmp_path) provando sessão ativa resolvida do sessions.json fake, POST com header certo, body com missionId/veredito, gh-notifications excluída (resolver e override), sem sessão → `sessao_ativa_inexistente`, sessions.json inexistente → falha tipada, dedupe 60s/1 por missão, log escrito, **spool append após POST / não-append sem delivery / spool não-escrível não quebra (stub worker-vs-root via permissão 0444)**, retrocompat payload 5 chaves/dry-run/rollback/patch07 idempotente.

## Provas reais

- `python3 -m pytest tests/test_vigia_chat.py -q` (como worker): **18 passed**; `bash -n` OK.
- **E2E vivo**: `vigia_chat.sh AVISO-CHAT-ATIVO-01-T2 --send` → `{"ok":true,"delivered":true,"sessao":"20261010_214203_142245","http":"200","spool":true}`. Mensagem persistida no chat do operador (state.db, sessão TUI ativa, 22:16:48 BRT). Aceite final é do operador (ver linha "VIGIA: missao AVISO-CHAT-ATIVO-01-T2…").
- **Contexto worker-vs-root** (22:18 BRT, ao vivo): `sudo -u worker herdr tab list` → `tabs:[]` (0 abas); root → 4+ abas vivas. Confirma o bug do tab_reap no fecho (roda como worker).

## PASSO DE SUPERVISOR (handler mission_end — o bus não trata hoje; não toquei no bus)

Consumir o evento como root após o merge (cron do bus ou um-shot):

```bash
# roda como ROOT; reap das abas mortas quando houver mission_end não consumido
grep '"kind":"mission_end"' /opt/mission-events/spool.jsonl \
  | awk -F'"missionId":"' '{split($2,a,"\""); print a[1]}' \
  | sort -u > /tmp/mission_end_ids.txt
if [ -s /tmp/mission_end_ids.txt ]; then
  bash /opt/mission-events/tools-bash/tab_reap.sh --apply >> /tmp/tab_reap-root.log 2>&1
fi
```

(Alternativa durável: handler em `event_bus.py` no `process_events` que, para `kind=mission_end`, executa `tab_reap.sh --apply` como root — como o bus já roda como root. Decisão do supervisor; fora do escopo desta missão.)

## Não tocado / limitações

- routing/bridge/TLS, GB-STREAM-02, GB-CONEX-01B, GB-WEB-02, cadeia MT, guard e core do bus: intactos.
- `/root/.hermes/sessions.json` ainda não existe (gateway não o escreveu nesta VM até agora); o resolver usa `active_sessions.json` (leases vivos) como fonte real e aceita o sessions.json quando passar a existir. Worker não lê `/root` (0700) — o `--send` roda no ExecStopPost (root) via systemd; leituras de sessão/créden falham tipado se executado como worker.
- Deploy: supervisor faz merge ff na base após o PASS.