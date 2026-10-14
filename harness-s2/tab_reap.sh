#!/usr/bin/env bash
# tab_reap.sh — detecta abas de run mortas e (com --apply) fecha-as.
# Uso: tab_reap.sh [--tabs-json F] [--active-json F] [--apply]
set -u
cd "$(dirname "$0")" || exit 1

HERDR_BIN="${HERDR_BIN:-herdr}"
APPLY=0
TABS_JSON=""
ACTIVE_JSON=""

while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --tabs-json) TABS_JSON="${2:-}"; shift ;;
    --active-json) ACTIVE_JSON="${2:-}"; shift ;;
    *) shift ;;
  esac
  shift || true
done

fail() {
  printf '{"ok":false,"tool":"tab_reap","erro":"%s"%s}\n' "$1" "${2:+,\"hint\":\"$2\"}"
  exit 0
}

# ---------- obter tabs ----------
if [ -n "$TABS_JSON" ]; then
  [ -f "$TABS_JSON" ] || fail "TABS_JSON_AUSENTE"
  TABS_RAW="$(cat "$TABS_JSON")"
else
  TABS_RAW="$("$HERDR_BIN" tab list 2>/dev/null)"
fi
printf '%s' "$TABS_RAW" | python3 -c 'import sys,json; d=json.load(sys.stdin); d["result"]["tabs"]' >/dev/null 2>&1 \
  || fail "HERDR_INACESSIVEL" "a unit roda como worker sem a sessão do operador; use --tabs-json com fixture ou rode na sessão do operador"

# ---------- obter active-json ----------
if [ -n "$ACTIVE_JSON" ]; then
  [ -f "$ACTIVE_JSON" ] || fail "ACTIVE_JSON_AUSENTE"
  ACTIVE_RAW="$(cat "$ACTIVE_JSON")"
else
  ACTIVE_RAW="$(bash /opt/mission-events/tools-bash/runs_status.sh 2>/dev/null)"
fi
printf '%s' "$ACTIVE_RAW" | python3 -c 'import sys,json; d=json.load(sys.stdin); d["runs"]' >/dev/null 2>&1 \
  || fail "ACTIVE_JSON_INVALIDO"

# ---------- cruzamento (determinístico) ----------
CROSS="$(TABS_RAW="$TABS_RAW" ACTIVE_RAW="$ACTIVE_RAW" python3 -c '
import sys, json
tabs = json.loads(__import__("os").environ["TABS_RAW"])["result"]["tabs"]
active = json.loads(__import__("os").environ["ACTIVE_RAW"])
run_ids = set()
for r in active.get("runs", []):
    mid = r.get("missionId") or ""
    if mid: run_ids.add(mid)
mortas = []
for t in tabs:
    label = t.get("label") or ""
    if not (label.startswith("RUN:") or label.startswith("MISSION:") or label.startswith("AGENTE:")):
        continue
    rest = label.split(":", 1)[1]
    mid = rest.split("#", 1)[0]
    if mid and mid not in run_ids:
        mortas.append({"tab": t.get("tab_id",""), "label": label})
print(json.dumps({"abas_total": len(tabs), "mortas": mortas}, separators=(",", ":")))
')"
[ -n "$CROSS" ] || fail "CRUZAMENTO_FALHOU"
ABAS_TOTAL="$(printf '%s' "$CROSS" | python3 -c 'import sys,json; print(json.load(sys.stdin)["abas_total"])')"
MORTAS_JSON="$(printf '%s' "$CROSS" | python3 -c 'import sys,json; print(json.dumps(json.load(sys.stdin)["mortas"], separators=(",", ":")))')"

# ---------- ação ----------
FECHADAS="[]"
MODO="dry-run"
if [ "$APPLY" = "1" ]; then
  MODO="apply"
  if [ -z "$TABS_JSON" ]; then
    LIVE="$("$HERDR_BIN" tab list 2>/dev/null)"
    printf '%s' "$LIVE" | python3 -c 'import sys,json; d=json.load(sys.stdin); d["result"]["tabs"]' >/dev/null 2>&1 \
      || fail "HERDR_INACESSIVEL" "herdr inacessível no apply; NADA fechado"
  fi
  FECHADAS="$(MORTAS="$MORTAS_JSON" HERDR="$HERDR_BIN" python3 -c '
import os, json, subprocess
mortas = json.loads(os.environ["MORTAS"])
fechadas = []
for m in mortas:
    r = subprocess.run([os.environ["HERDR"], "tab", "close", m["tab"]], capture_output=True)
    if r.returncode == 0:
        fechadas.append(m)
print(json.dumps(fechadas, separators=(",", ":")))
')"
fi

printf '{"ok":true,"tool":"tab_reap","abas_total":%s,"mortas":%s,"fechadas":%s,"modo":"%s"}\n' \
  "$ABAS_TOTAL" "$MORTAS_JSON" "$FECHADAS" "$MODO"
exit 0