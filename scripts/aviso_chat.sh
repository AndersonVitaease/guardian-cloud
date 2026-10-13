#!/usr/bin/env bash
# scripts/aviso_chat.sh — GB-AVISO-CHAT-02
# Aviso (nascimento/morte) no CHAT ATIVO do operador, com retry tipado.
# Reuso da resolucao de sessao do vigia_chat.sh (mesma logica, extraida).
# Env: AVISO_API (default http://127.0.0.1:8642/v1/chat/completions),
#      AVISO_CRED (arquivo de credencial hermes-notify),
#      AVISO_SPOOL (spool de eventos; falha de entrega grava AVISO_ENTREGA_FALHOU),
#      AVISO_SESSIONS_JSON (override do sessions.json p/ testes),
#      AVISO_TIMEOUT (default 900).
# Uso: aviso_chat.sh "<mensagem>"
# Saida: JSON 1-linha {ok, delivered, sessao, http, spool, motivo}. Exit 0 sempre (fail-open).
set -u

MSG="${1:-}"
emit() { printf '%s\n' "$1"; exit 0; }

[ -z "$MSG" ] && emit '{"ok":false,"tool":"aviso_chat","error":"SEM_MENSAGEM"}'

API="${AVISO_API:-http://127.0.0.1:8642/v1/chat/completions}"
CRED="${AVISO_CRED:-/opt/eng-mcp-release-data/credentials/hermes-notify-api-key}"
SPOOL="${AVISO_SPOOL:-/opt/mission-events/spool.jsonl}"
TMO="${AVISO_TIMEOUT:-900}"
TS="$(date +%s)"
LOG="/tmp/aviso-chat-$TS.log"
alog() { printf '%s\n' "$1" >> "$LOG" 2>/dev/null || true; }

# ---- resolucao DINAMICA da sessao de chat ativa (logica extraida do vigia_chat.sh) ----
SESS="$(python3 - "${AVISO_SESSION:-}" "${AVISO_SESSIONS_JSON:-}" <<'PY'
import json, os, sys

override, extra = sys.argv[1], sys.argv[2]
CANDIDATES = ([extra] if extra else []) + [
    "/root/.hermes/sessions.json",
    "/root/.hermes/runtime/active_sessions.json",
]
ACT_KEYS = ("last_activity", "updated_at", "mtime", "lastActivity", "timestamp", "started_at")
ID_KEYS = ("session_id", "sessionId", "id", "live_session_id")

def entries_of(doc):
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict):
        for k in ("sessions", "entries", "items", "active"):
            v = doc.get(k)
            if isinstance(v, list):
                return v
    return []

def sid_of(e):
    for k in ID_KEYS:
        v = e.get(k)
        if isinstance(v, str) and v:
            return v
    return None

def act_of(e):
    for k in ACT_KEYS:
        v = e.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return v
    return 0

best, best_act = None, -1
for path in CANDIDATES:
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception:
        continue
    for e in entries_of(doc):
        if not isinstance(e, dict):
            continue
        sid = sid_of(e)
        if not sid:
            continue
        blob = json.dumps(e)
        if "gh-notifications" in blob:
            continue  # sessao fixa PROIBIDA
        a = act_of(e)
        if a > best_act:
            best, best_act = sid, a
if override and "gh-notifications" not in override:
    print(override)
else:
    print(best or "")
PY
)"
if [ -z "$SESS" ]; then
  alog '{"evento":"SESSAO_AUSENTE"}'
  emit '{"ok":false,"tool":"aviso_chat","delivered":false,"motivo":"SESSAO_AUSENTE"}'
fi

BODY="$(python3 -c 'import json,sys; print(json.dumps({"model": "hermes-agent", "stream": False, "messages": [{"role": "user", "content": sys.argv[1]}]}))' "$MSG")"

# ---- POST paciente com RETRY TIPADO: 3 tentativas, backoff 5s/20s/60s ----
HTTP=""
BACKOFFS="5 20 60"
for tent in 1 2 3; do
  HTTP="$(curl -sS --max-time "$TMO" -o /dev/null -w '%{http_code}' \
    -X POST "$API" \
    -H "Authorization: Bearer $(cat "$CRED" 2>/dev/null)" \
    -H "X-Hermes-Session-Id: $SESS" \
    -H "Content-Type: application/json" \
    -d "$BODY" 2>/dev/null || true)"
  alog "{\"evento\":\"TENTATIVA\",\"n\":$tent,\"http\":\"${HTTP:-0}\"}"
  case "$HTTP" in
    2*)
      alog "{\"evento\":\"DELIVERED\",\"sessao\":\"$SESS\",\"http\":\"$HTTP\"}"
      emit '{"ok":true,"tool":"aviso_chat","delivered":true,"sessao":"'"$SESS"'","http":"'"${HTTP:-0}"'","spool":false}'
      ;;
  esac
  [ "$tent" -lt 3 ] && sleep "$(echo $BACKOFFS | cut -d' ' -f$tent)"
done

# ---- falhou tudo: evento tipado no spool configuravel ----
SPOOLOK="$(python3 - "$SPOOL" "$MSG" "${HTTP:-0}" <<'PY'
import json, sys, datetime
try:
    spool, msg, http = sys.argv[1], sys.argv[2], sys.argv[3]
    ev = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "aviso_chat",
        "kind": "AVISO_ENTREGA_FALHOU",
        "motivo": "ROTA_OFFLINE",
        "http": http,
        "msg": msg,
    }
    with open(spool, "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    print("true")
except Exception:
    print("false")
PY
)"
alog "{\"evento\":\"AVISO_ENTREGA_FALHOU\",\"http\":\"${HTTP:-0}\",\"spool\":$SPOOLOK}"
emit '{"ok":false,"tool":"aviso_chat","delivered":false,"motivo":"ROTA_OFFLINE","http":"'"${HTTP:-0}"'","spool":'"$SPOOLOK"'}'