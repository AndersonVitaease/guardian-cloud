#!/usr/bin/env bash
# scripts/vigia_chat.sh — VIGIA-CHAT-01
# Notifica o chat (rota mapeada do event_bus) ao fim de uma missao.
# Dry-run default: imprime payload 1-linha, nao toca rede.
# --send: POST na rota. VIGIA_CHAT=0 = rollback total. Falhas tipadas, exit 0.
set -u

ID="${1:-}"
SEND=0
[ "${2:-}" = "--send" ] && SEND=1

emit() { printf '%s\n' "$1"; exit 0; }

# rollback
if [ "${VIGIA_CHAT:-1}" = "0" ]; then
  emit '{"ok":false,"tool":"vigia_chat","rollback":true}'
fi

if [ -z "$ID" ]; then
  emit '{"ok":false,"tool":"vigia_chat","error":"SEM_ID"}'
fi

# ---- resolve run-dir (mesmo resolvedor do run_close.sh) ----
SD="${VIGIA_CHAT_STATE_DIR:-/home/worker/.local/state/mission-ledger}"
RUN_DIR=""
LED="$SD/$ID.json"
if [ -f "$LED" ]; then
  RUN_DIR="$(python3 -c '
import json,sys
try:
    d=json.load(open(sys.argv[1]))
    c=d.get("cwd")
    print(c if isinstance(c,str) else "")
except Exception:
    print("")
' "$LED" 2>/dev/null)"
fi
ABA="$(python3 -c '
import json,sys
try:
    d=json.load(open(sys.argv[1]))
    a=d.get("aba")
    print(a if isinstance(a,str) else "")
except Exception:
    print("")
' "$LED" 2>/dev/null)"
if [ -z "$RUN_DIR" ]; then
  for d in /home/worker/wt-*/runs/"$ID"; do
    [ -d "$d" ] && { RUN_DIR="$d"; break; }
  done
fi
if [ -z "$RUN_DIR" ] || [ ! -d "$RUN_DIR" ]; then
  emit '{"ok":false,"tool":"vigia_chat","error":"SEM_RESUMO","missao":"'"$ID"'"}'
fi

# normalizacao tentativa-N (sobe ate ancestral com os JSONs)
if [ ! -f "$RUN_DIR/resumo.json" ] && [ ! -f "$RUN_DIR/autoretry-summary.json" ]; then
  p="$RUN_DIR"
  while :; do
    case "$p" in
      */tentativa-*/run-*|*/tentativa-*)
        p="$(dirname "$p")"
        if [ -f "$p/resumo.json" ] || [ -f "$p/autoretry-summary.json" ]; then
          RUN_DIR="$p"; break
        fi
        ;;
      *) break ;;
    esac
  done
fi

# ---- extrai veredito/turnos/custo (mesma logica do run_close.sh) ----
DATA="$(python3 - "$RUN_DIR" "$ID" "$ABA" <<'PY'
import json, os, sys
run_dir, mid, aba = sys.argv[1], sys.argv[2], sys.argv[3]

def load(p):
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except Exception:
        return None

res = load(os.path.join(run_dir, "resumo.json"))
aut = load(os.path.join(run_dir, "autoretry-summary.json"))
if res is None and aut is None:
    print(json.dumps({"ok": False, "tool": "vigia_chat", "error": "SEM_RESUMO",
                      "missao": mid}))
    sys.exit(0)

veredito = turnos = custo = None
if res is not None:
    veredito = res.get("veredito")
    turnos = res.get("turnos")
    custo = res.get("custo_usd")
else:
    vpt = aut.get("vereditos_por_tentativa")
    if isinstance(vpt, list) and vpt:
        veredito = vpt[-1]
    runs = aut.get("runs")
    if isinstance(runs, list) and runs:
        last = runs[-1] if isinstance(runs[-1], dict) else {}
        turnos = last.get("turnos")
        custo = aut.get("custo_total", (last.get("custo") or {}).get("usd"))
if veredito is None:
    veredito = "DESCONHECIDO"
if custo is None:
    custo = 0.0
if turnos is None:
    turnos = 0
print(json.dumps({"missao": mid, "veredito": veredito, "custo_usd": custo,
                  "turnos": turnos, "aba": aba or None},
                 ensure_ascii=False))
PY
)"
ERR="$(printf '%s' "$DATA" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("error",""))' 2>/dev/null)"
if [ -n "$ERR" ]; then
  emit "$DATA"
fi

# dry-run default: so o payload
if [ "$SEND" = "0" ]; then
  emit "$DATA"
fi

# ---- --send ----
CRED="${VIGIA_CHAT_CRED:-/root/.config/hermes/chat-cred}"
API="${VIGIA_CHAT_API:-http://127.0.0.1:8642/v1/chat/completions}"
SESS="${VIGIA_CHAT_SESSION:-gh-notifications}"

if [ ! -r "$CRED" ]; then
  emit '{"ok":false,"tool":"vigia_chat","error":"SEM_ROTA","missao":"'"$ID"'"}'
fi
TOKEN="$(tr -d '\n\r' < "$CRED" 2>/dev/null)"
if [ -z "$TOKEN" ]; then
  emit '{"ok":false,"tool":"vigia_chat","error":"SEM_ROTA","missao":"'"$ID"'"}'
fi

MSG="$(printf '%s' "$DATA" | python3 -c '
import json, sys
d = json.load(sys.stdin)
aba = d.get("aba")
suf = (", aba %s." % aba) if aba else "."
print("VIGIA: missao %s terminou - veredito %s, custo US$ %s, turnos %s%s" % (
    d["missao"], d["veredito"], d["custo_usd"], d["turnos"], suf))
')"
BODY="$(python3 -c 'import json,sys; print(json.dumps({"content": sys.argv[1], "session": sys.argv[2]}))' "$MSG" "$SESS")"

HTTP="$(curl -sS --max-time 15 -o /dev/null -w '%{http_code}' \
  -X POST "$API" \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Hermes-Session-Id: $SESS" \
  -H "Content-Type: application/json" \
  -d "$BODY" 2>/dev/null || true)"
case "$HTTP" in
  2*) emit '{"ok":true,"tool":"vigia_chat","missao":"'"$ID"'","http":'"${HTTP:-0}"'}' ;;
  *)  emit '{"ok":false,"tool":"vigia_chat","error":"ROTA_OFFLINE","missao":"'"$ID"'","http":'"${HTTP:-0}"'}' ;;
esac