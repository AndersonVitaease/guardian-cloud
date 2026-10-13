#!/bin/bash
# Despacho DESP-EXECSTOP-FIX-01 sem sudo (worker direto), imitando despachar.sh.
set -u
M=/home/worker/harness-s2/missao-DESP-EXECSTOP-FIX-01.md
CWDR=/home/worker/harness-s2
SEED=2287
BUDGET=0.30
MAXT=26
OUT=/opt/mission-events/out-DESP-EXECSTOP-FIX-01.json
mkdir -p /opt/mission-events 2>/dev/null || OUT=/home/worker/harness-s2/out-DESP-EXECSTOP-FIX-01.json

WS=$(herdr workspace create --cwd "$CWDR" --label harness-s2 2>/dev/null \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['workspace']['workspace_id'])")
echo "workspace=$WS"
T=$(herdr tab create --workspace "$WS" --label "RUN:DESP_EXECSTOP_FIX_01#s$SEED" 2>/dev/null \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['root_pane']['pane_id'])")
echo "tab=$T"

/usr/bin/python3 /home/worker/harness-s2/mission_run.py --pane --escada on --vagueio on \
  --mission "$M" --cwd "$CWDR" --seed "$SEED" --budget "$BUDGET" --max-turns "$MAXT" --out "$OUT" &
PID=$!
echo "pid=$PID"

R=""
for i in $(seq 1 60); do
  R=$(ls -dt "$CWDR"/run-*seed$SEED* 2>/dev/null | head -1)
  [ -n "$R" ] && [ -f "$R/harness-pane.log" ] && break
  sleep 0.5
done
if [ -n "$R" ] && [ -n "$T" ]; then
  herdr pane run "$T" "tail -n 15 -F $R/harness-pane.log" >/dev/null 2>&1
  echo "despachada: tab=$T run=$R pid=$PID out=$OUT"
else
  echo "aviso: tab=$T run=${R:-?} pid=$PID (espelho incompleto — conferir)"
fi
wait $PID
echo "run terminou: exit=$?"
