#!/usr/bin/env bash
# GUARDIAN-TOAST-01 — wrapper de pouso de missão no Guardian (:8140).
# Uso: notifica_pouso.sh MISSIONID VEREDITO CUSTO_USD MS [LINK?] [TITULO?]
#   MISSIONID  id da missão (6-40 chars), ex: MECANICO-01
#   VEREDITO   PASS | FAIL
#   CUSTO_MS   dois valores: custo_usd e duracao_ms, ex: 0.006 21000
#   LINK?      link opcional da prova
#   TITULO?    título legível opcional (máx 80; default: o próprio MISSIONID)
# GB-NOTIFY-NOME-01: TITULO opcional vai no body (default = missionId) e o token
# usa a MESMA busca do espelho.sh (GUARDIAN_NOTIFY_TOKEN ou ADMIN_TOKEN em
# /home/worker/guardian-app/.env, depois /home/worker/.hermes/.env).
# MOPS-CUSTO-REAL-01: custo REAL vem do .espelho.json (campo custo_usd) —
#   notifica_pouso.sh --espelho-json <arquivo> MISSIONID VEREDITO - MS [LINK] [TITULO]
# com CUSTO_USD = "-" o custo e lido do json do espelho (nunca estimado); se o
# json nao tiver custo, avisa CUSTO_AUSENTE no stderr e posta custoUsd null.
# Recusas tipadas sem quebrar a sessão que pousa (exit 0 sempre):
#   NOTIFY_SEM_TOKEN / NOTIFY_401 / ENDPOINT_AUSENTE
# O token NUNCA é impresso em output/trilha.
set -u
PORT="${GUARDIAN_PORT:-8140}"
URL="http://127.0.0.1:${PORT}/api/notify"

usage() { echo "uso: $0 [--espelho-json arquivo] MISSIONID PASS|FAIL CUSTO_USD|- MS [LINK] [TITULO]" >&2; exit 2; }
ESP_JSON=""
while [ "${1:-}" = "--espelho-json" ]; do
  [ -n "${2:-}" ] || usage
  ESP_JSON="$2"; shift 2
done
[ $# -ge 4 ] || usage
MISSION_ID="$1"; VEREDITO="$2"; CUSTO="$3"; MS="$4"; LINK="${5:-}"; TITULO="${6:-$MISSION_ID}"

case "$VEREDITO" in PASS|FAIL) ;; *) echo "veredito deve ser PASS ou FAIL" >&2; exit 2 ;; esac

# MOPS-CUSTO-REAL-01: CUSTO = "-" -> custo real do .espelho.json (nao estimar)
if [ "$CUSTO" = "-" ]; then
  CUSTO="$(ESP_JSON="$ESP_JSON" python3 - <<'EOF'
import json, os, sys
try:
    with open(os.environ["ESP_JSON"]) as fh:
        v = json.load(fh).get("custo_usd")
    if isinstance(v, (int, float)):
        print(v)
except Exception:
    pass
EOF
)"
  [ -n "$CUSTO" ] || echo "CUSTO_AUSENTE: sem custo_usd em $ESP_JSON (postando null)" >&2
fi

BODY=$(python3 - "$MISSION_ID" "$VEREDITO" "$CUSTO" "$MS" "$LINK" "$TITULO" <<'EOF'
import json, sys
mid, ver, custo, ms, link, titulo = sys.argv[1:7]
custo_val = float(custo) if custo and custo not in ("-",) else None
d = {"missionId": mid, "veredito": ver, "custoUsd": custo_val, "ms": int(ms),
     "titulo": (titulo or mid)[:80]}
if link: d["link"] = link
print(json.dumps(d))
EOF
) || { echo '{"ok":false,"error":"ENDPOINT_AUSENTE"}'; exit 0; }

# Token de serviço — mesma busca do espelho.sh: GUARDIAN_NOTIFY_TOKEN ou
# ADMIN_TOKEN, em /home/worker/guardian-app/.env e /home/worker/.hermes/.env.
TOKEN_ARG=""
NOTIFY_TOKEN="${GUARDIAN_NOTIFY_TOKEN:-}"
if [ -z "${NOTIFY_TOKEN:-}" ]; then
  # GUARDIAN_NOTIFY_ENV permite apontar outro env-file (provas); default: os dois fixos
  for ENVF in ${GUARDIAN_NOTIFY_ENV:-/home/worker/guardian-app/.env /home/worker/.hermes/.env}; do
    [ -r "$ENVF" ] || continue
    NOTIFY_TOKEN=$(grep -E '^(GUARDIAN_NOTIFY_TOKEN|ADMIN_TOKEN)=' "$ENVF" | head -n 1 | cut -d= -f2- | tr -d '"'"'"'')
    [ -n "${NOTIFY_TOKEN:-}" ] && break
  done
fi
if [ -z "${NOTIFY_TOKEN:-}" ]; then
  echo '{"ok":false,"error":"NOTIFY_SEM_TOKEN"}'
  exit 0
fi
TOKEN_ARG="X-Notify-Token: $NOTIFY_TOKEN"
unset NOTIFY_TOKEN

HTTP_CODE=$(curl -s -o /tmp/notify_pouso_resp.$$ -w '%{http_code}' -m 5 -X POST "$URL" \
  -H 'Content-Type: application/json' ${TOKEN_ARG:+-H "$TOKEN_ARG"} -d "$BODY" 2>/dev/null)
RC=$?
RESP=$(cat /tmp/notify_pouso_resp.$$ 2>/dev/null || true)
rm -f /tmp/notify_pouso_resp.$$ 2>/dev/null || true
if [ $RC -ne 0 ] || [ -z "$HTTP_CODE" ]; then
  echo '{"ok":false,"error":"ENDPOINT_AUSENTE"}'
  exit 0
fi
if [ "$HTTP_CODE" = "401" ]; then
  echo '{"ok":false,"error":"NOTIFY_401"}'
  exit 0
fi
if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "201" ] && [ "$HTTP_CODE" != "202" ]; then
  echo "{\"ok\":false,\"error\":\"NOTIFY_${HTTP_CODE}\"}"
  exit 0
fi
echo "${RESP:-{\"ok\":true}}"
exit 0
