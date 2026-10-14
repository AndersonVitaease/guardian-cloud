#!/usr/bin/env bash
# test_queue_eye.sh — testes herméticos para queue_eye.sh (0 LLM)
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
TOOL="bash $HERE/queue_eye.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
FAILS=0
ok(){ echo "PASS: $1"; }
bad(){ echo "FAIL: $1"; FAILS=$((FAILS+1)); }

# proc dump: 2 daemons na MESMA fila + 1 em outra fila + consumer
printf '2424807\tworker\x1forqd.daemon\x1f--db\x1f/var/lib/orqd-live/orqd.db\x1f--sock\x1f/run/orqd-live/orqd.sock\x1f--queue\x1f%s/orchestrator-queue.jsonl\n' "$TMP" > "$TMP/proc.txt"
printf '3772362\tworker\x1forqd.daemon\x1f--db\x1f/var/lib/orqd/orqd.db\x1f--sock\x1f/run/orqd.sock\x1f--queue\x1f%s/orchestrator-queue.jsonl\n' "$TMP" >> "$TMP/proc.txt"
printf '1111\tworker\x1forqd.daemon\x1f--db\x1f/var/lib/outro/orqd.db\x1f--queue\x1f%s/orchestrator-queue.js\n' "$TMP" >> "$TMP/proc.txt"
printf '5555\tworker\x1fpython3\x1f/opt/mission-events/orchestrator-consumer.py\x1f--queue\x1f%s/orchestrator-queue.jsonl\n' "$TMP" >> "$TMP/proc.txt"

# fila fake: 2 JSON válidos (1 dispatched sem veredito), 1 dispatched com veredito, 1 linha inválida, 1 JSON sem missionId
cat > "$TMP/orchestrator-queue.jsonl" <<'EOF'
{"missionId":"M-1","status":"dispatched"}
{"missionId":"M-2","status":"dispatched","verdict":"PASS"}
{"missionId":"M-3","status":"done","verdict":"FAIL"}
linha-lixo-nao-json
{"status":"dispatched"}
EOF
printf 'x' > "$TMP/orchestrator-queue.js"   # variante .js* vazia

OUT=$(QUEUE_EYE_DIR="$TMP" QUEUE_EYE_PROC="$TMP/proc.txt" $TOOL); RC=$?
[ $RC -eq 0 ] && ok "exit 0" || bad "exit=$RC"
[ "$(echo "$OUT" | wc -l)" -eq 1 ] && ok "JSON 1 linha" || bad "saida multi-linha"

echo "$OUT" | grep -q '"duplicado":true' && ok "duplicado:true (2 daemons mesma fila)" || bad "duplicado NAO detectado: $OUT"
echo "$OUT" | grep -q '"pid":"2424807"' && echo "$OUT" | grep -q '"pid":"3772362"' && ok "2 daemons listados" || bad "daemons ausentes: $OUT"
echo "$OUT" | grep -q '"profundidade":3' && ok "profundidade=3 (so JSON valido com missionId)" || bad "profundidade errada: $OUT"
echo "$OUT" | grep -q '"dispatched_sem_veredito":1' && ok "dispatched sem veredito=1" || bad "dispatched_sem_veredito errado: $OUT"
echo "$OUT" | grep -q '"consumidores":\[5555,' && ok "consumer 5555 como consumidor da fila" || bad "consumidor ausente: $OUT"
echo "$OUT" | grep -q '"arquivo":"'"$TMP"'/orchestrator-queue.js"' && ok "variante .js listada" || bad "variante .js ausente: $OUT"

# --only filas
OUT2=$(QUEUE_EYE_DIR="$TMP" QUEUE_EYE_PROC="$TMP/proc.txt" $TOOL --only filas)
echo "$OUT2" | grep -q '"filas"' && ! echo "$OUT2" | grep -q '"daemons"' && ok "--only filas" || bad "--only filas: $OUT2"
# --only daemons
OUT3=$(QUEUE_EYE_DIR="$TMP" QUEUE_EYE_PROC="$TMP/proc.txt" $TOOL --only daemons)
echo "$OUT3" | grep -q '"daemons"' && ! echo "$OUT3" | grep -q '"filas"' && ok "--only daemons" || bad "--only daemons: $OUT3"
# BAD_ARGS
OUT4=$($TOOL --foo)
echo "$OUT4" | grep -q '"error":"BAD_ARGS"' && ok "BAD_ARGS tipado" || bad "BAD_ARGS: $OUT4"

[ $FAILS -eq 0 ] && { echo "TODOS OS TESTES PASSARAM"; exit 0; } || { echo "$FAILS FALHAS"; exit 1; }