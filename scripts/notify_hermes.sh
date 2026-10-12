#!/usr/bin/env bash
# VIGIA-NASCER-03: helper de aviso ao gateway hermes (reutilizavel).
# GB-MIGRA-100-01A(a): o TEXTO do aviso (ja com titulo da missao, formato
# "✅ <TITULO> (<ID>) — veredito ... · custo US$x · N turnos") vem pronto
# de vigia_chat.sh via stdin; este helper nao altera o payload do gateway.
# Le o texto de stdin, faz POST no gateway. Exit 0 SEMPRE (fail-open).
# Falha tipada no stdout: SEM_BEARER | ROTA_OFFLINE
set -u
BEARER_FILE="${HERMES_NOTIFY_BEARER_FILE:-/opt/eng-mcp-release-data/credentials/hermes-notify-api-key}"
URL="${HERMES_NOTIFY_URL:-http://127.0.0.1:8642/v1/chat/completions}"
TEXT="$(cat)"
if [ ! -r "$BEARER_FILE" ]; then
  echo "SEM_BEARER"
  exit 0
fi
BEARER="$(tr -d '\r\n' < "$BEARER_FILE")"
PAYLOAD="$(python3 -c 'import json,sys; print(json.dumps({"model":"hermes","messages":[{"role":"user","content":sys.stdin.read()}]}, ensure_ascii=False))' <<<"$TEXT")"
if python3 - "$URL" "$BEARER" "$PAYLOAD" <<'PYEOF'
import sys, urllib.request
url, bearer, payload = sys.argv[1], sys.argv[2], sys.argv[3]
req = urllib.request.Request(url, data=payload.encode("utf-8"), method="POST",
    headers={"Content-Type": "application/json", "Authorization": "Bearer " + bearer,
             "X-Hermes-Session-Id": "gh-notifications"})
urllib.request.urlopen(req, timeout=5)
PYEOF
then
  echo "OK"
else
  echo "ROTA_OFFLINE"
fi
exit 0
