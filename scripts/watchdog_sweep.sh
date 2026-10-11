#!/usr/bin/env bash
# WATCHDOG-CTL-01 — sweep de watchdog.d: roda cada script habilitado em ordem alfabética,
# com timeout por script; silencioso quando nada reporta; JSON 1 linha; exit 0 sempre.
set -u
WATCHDOG_D_DIR="${WATCHDOG_D_DIR:-/opt/hermes/watchdog.d}"
WATCHDOG_TIMEOUT="${WATCHDOG_TIMEOUT:-120s}"

timeout_secs() {
  local t="$WATCHDOG_TIMEOUT"
  case "$t" in
    *s) t="${t%s}" ;;
    *m) t=$(( ${t%m} * 60 )) ;;
    *h) t=$(( ${t%h} * 3600 )) ;;
  esac
  printf '%s' "$t"
}

TMO="$(timeout_secs)"
rodados="[]"
falhas="[]"
declare -a rr=()
declare -a ff=()

if [ -d "$WATCHDOG_D_DIR" ]; then
  for script in "$WATCHDOG_D_DIR"/*.sh; do
    [ -e "$script" ] || continue
    [ -x "$script" ] || continue   # desabilitado (sem +x) é pulado
    nome="$(basename "$script" .sh)"
    out="/tmp/watchdog-${nome}-ultima.txt"
    : > "$out"
    chmod 0600 "$out" 2>/dev/null || true
    ini=$(date +%s%N)
    if timeout "$TMO" bash "$script" > "$out" 2>&1; then
      rc=0
    else
      rc=$?
    fi
    fim=$(date +%s%N)
    ms=$(( (fim - ini) / 1000000 ))
    reportou=false
    [ -s "$out" ] && reportou=true
    if [ "$rc" -eq 124 ]; then
      ff+=("{\"script\":\"$nome\",\"tipo\":\"timeout\",\"ms\":$ms}")
    elif [ "$rc" -ne 0 ]; then
      ff+=("{\"script\":\"$nome\",\"tipo\":\"exit_$rc\",\"ms\":$ms}")
    fi
    rr+=("{\"script\":\"$nome\",\"ms\":$ms,\"reportou\":$reportou}")
  done
fi

# monta JSON 1 linha (bash puro)
rodados="$(printf '%s\n' "${rr[@]-}" | python3 -c 'import sys,json;print(json.dumps([json.loads(l) for l in sys.stdin if l.strip()]))' 2>/dev/null || printf '[]')"
falhas="$(printf '%s\n' "${ff[@]-}" | python3 -c 'import sys,json;print(json.dumps([json.loads(l) for l in sys.stdin if l.strip()]))' 2>/dev/null || printf '[]')"
printf '{"ok":true,"rodados":%s,"falhas_tipadas":%s}\n' "$rodados" "$falhas"
exit 0