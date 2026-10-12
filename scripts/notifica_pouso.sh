#!/usr/bin/env bash
# GUARDIAN-TOAST-01 — wrapper de pouso de missão no Guardian (:8140).
# Uso: notifica_pouso.sh MISSIONID VEREDITO CUSTO_MS LINK?
#   MISSIONID  id da missão (6-40 chars), ex: MECANICO-01
#   VEREDITO   PASS | FAIL
#   CUSTO_MS   dois valores: custo_usd e duracao_ms, ex: 0.006 21000
#   LINK?      link opcional da prova
# Padrão de uso (nasce e morre junto): no despacho do worker direto,
#   trap 'notifica_pouso.sh MECANICO-01 PASS 0.006 21000' EXIT
# Endpoint ausente/servidor fora => {ok:false,error:"ENDPOINT_AUSENTE"} e exit 0
# (nunca derruba a sessão que está pousando).
set -u
PORT="${GUARDIAN_PORT:-8140}"
URL="http://127.0.0.1:${PORT}/api/notify"

usage() { echo "uso: $0 MISSIONID PASS|FAIL CUSTO_USD MS [LINK]" >&2; exit 2; }
[ $# -ge 4 ] || usage
MISSION_ID="$1"; VEREDITO="$2"; CUSTO="$3"; MS="$4"; LINK="${5:-}"

case "$VEREDITO" in PASS|FAIL) ;; *) echo "veredito deve ser PASS ou FAIL" >&2; exit 2 ;; esac

BODY=$(python3 - "$MISSION_ID" "$VEREDITO" "$CUSTO" "$MS" "$LINK" <<'EOF'
import json, sys
mid, ver, custo, ms, link = sys.argv[1:6]
d = {"missionId": mid, "veredito": ver, "custoUsd": float(custo), "ms": int(ms)}
if link: d["link"] = link
print(json.dumps(d))
EOF
) || { echo '{"ok":false,"error":"ENDPOINT_AUSENTE"}'; exit 0; }

RESP=$(curl -sS -m 5 -X POST "$URL" -H 'Content-Type: application/json' -d "$BODY" 2>/dev/null)
RC=$?
if [ $RC -ne 0 ] || ! echo "$RESP" | grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then
  echo '{"ok":false,"error":"ENDPOINT_AUSENTE"}'
  exit 0
fi
echo "$RESP"
exit 0
