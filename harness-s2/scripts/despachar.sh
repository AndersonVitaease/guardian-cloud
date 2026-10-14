#!/bin/bash
# despachar.sh — Toda missão NASCE no herdr (ordem operator 08/10).
# Supervisor-side: cria run dir + tab/pane ANTES de spawnar o run.
# Uso: sudo bash scripts/despachar.sh <missao.md> <cwd-runs> <seed> <budget> <max-turns> <out.json> [label]
set -u
M="$1"; CWDR="$2"; SEED="$3"; BUDGET="$4"; MAXT="$5"; OUT="$6"; LABEL="${7:-RUN}"
TAG=$(basename "$M" .md | tr 'a-z.' 'A-Z_')
mkdir -p "$CWDR" && chmod 777 "$CWDR" 2>/dev/null || true
T=$(herdr tab create --label "RUN:$TAG#s$SEED" 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['root_pane']['pane_id'])" 2>/dev/null)
sudo -u worker /usr/bin/python3 /home/worker/harness-s2/mission_run.py --pane --escada on --vagueio on \
  --mission "$M" --cwd "$CWDR" --seed "$SEED" --budget "$BUDGET" --max-turns "$MAXT" --out "$OUT" &
PID=$!
# espelho logo que o run dir nascer (até 30s)
for i in $(seq 1 60); do
  R=$(ls -dt "$CWDR"/run-*seed$SEED* 2>/dev/null | head -1)
  [ -n "$R" ] && [ -f "$R/harness-pane.log" ] && break
  sleep 0.5
done
if [ -n "${R:-}" ] && [ -n "${T:-}" ]; then
  herdr pane run "$T" "tail -n 15 -F $R/harness-pane.log" >/dev/null 2>&1
  echo "despachada: tab=$T run=$R pid=$PID"
else
  echo "aviso: tab=$T run=${R:-?} pid=$PID (espelho incompleto — conferir)"
fi
wait $PID
