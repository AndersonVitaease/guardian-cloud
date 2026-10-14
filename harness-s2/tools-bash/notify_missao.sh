#!/usr/bin/env bash
# VIGIA-NASCER-01: envia 1 aviso por chamada (evento do vigia). Fail-open.
set -u
EVENT_FILE="${1:-}"
if [ -z "$EVENT_FILE" ] || [ ! -f "$EVENT_FILE" ]; then
  echo '{"ok":false,"error":"SEM_EVENTO"}'; exit 0
fi
URL="${NOTIFY_URL:-http://127.0.0.1:8642/v1/chat/completions}"
BEARER_FILE="${NOTIFY_BEARER_FILE:-}"
if [ -z "$BEARER_FILE" ] || [ ! -r "$BEARER_FILE" ]; then
  echo '{"ok":false,"error":"SEM_BEARER"}'; exit 0
fi
BEARER="$(tr -d '\n\r' < "$BEARER_FILE" 2>/dev/null)"
if [ -z "$BEARER" ]; then
  echo '{"ok":false,"error":"SEM_BEARER"}'; exit 0
fi

BODY="$(python3 - "$EVENT_FILE" <<'PYEOF'
import json, sys
ev = json.load(open(sys.argv[1]))
tipo = ev.get("tipo") or ev.get("event") or ""
mid = ev.get("missao_id") or ev.get("mission_id") or ev.get("id") or "?"
if tipo == "inicio":
    seed = ev.get("seed", "?"); budget = ev.get("budget", "?")
    text = f"🛰️ NASCEU: missao {mid} — seed {seed} — budget {budget} (aba RUN:{mid}#s{seed})"
elif tipo == "fim":
    veredito = ev.get("veredito", "?"); custo = ev.get("custo", "?"); turnos = ev.get("turnos", "?")
    text = f"✅ MORREU: missao {mid} — veredito {veredito} — custo US${custo} — turnos {turnos}"
else:
    sys.exit(3)  # andamento ou desconhecido: silencioso
print(json.dumps({"model": "vigia", "messages": [{"role": "user", "content": text}]}))
PYEOF
)"
RC=$?
if [ $RC -ne 0 ] || [ -z "$BODY" ]; then
  echo '{"ok":true,"skipped":true}'; exit 0
fi

HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 -X POST "$URL" \
  -H "Authorization: Bearer $BEARER" -H 'Content-Type: application/json' \
  -d "$BODY" 2>/dev/null)"
if [ "$HTTP_CODE" = "200" ]; then
  echo '{"ok":true}'
else
  echo '{"ok":false,"error":"ROTA_OFFLINE"}'
fi
exit 0