#!/usr/bin/env bash
# test_run_stream.sh — teste hermético de run_stream.sh (fixture em scratch).
# Cobre: snapshot (6 eventos + veredito, 0 ruído), custo acumulado, hora BRT,
# --follow simulado (VEREDITO após 1s, com timeout), SEM_TRAIL, RUN_DIR_NAO_ENCONTRADO.
set -u
cd "$(dirname "$0")"
pass=0; failn=0
chk(){ if [ "$2" = "$3" ]; then pass=$((pass+1)); else failn=$((failn+1)); echo "FALHA: $1 (esperado [$3], obtido [$2])"; fi; }
has(){ if printf '%s' "$2" | grep -qF -- "$3"; then pass=$((pass+1)); else failn=$((failn+1)); echo "FALHA: $1 (não contém [$3])"; fi; }
nohas(){ if printf '%s' "$2" | grep -qF -- "$3"; then failn=$((failn+1)); echo "FALHA: $1 (contém ruído [$3])"; else pass=$((pass+1)); fi; }

SCRATCH="$(mktemp -d /tmp/test_run_stream.XXXXXX)"
trap 'rm -rf "$SCRATCH"' EXIT
RUNDIR="$SCRATCH/run-1"
mkdir -p "$RUNDIR"

# ---- fixture: 6 eventos + veredito + 3 linhas de ruído gigante ----
# ts UTC conhecido: 2026-10-10T03:00:00Z = 00:00:00 BRT
NOISE='{"tool":"Bash","input":"'"$(printf 'X%.0s' $(seq 1 5000))"'"}'
cat > "$RUNDIR/harness-trail.jsonl" <<EOF
{"ts":"2026-10-10T03:00:00Z","turno":1,"rotulo":"AGIR","custo_usd":0.001,"stops":[true,false]}
{"ts":"2026-10-10T03:00:01Z","turno":2,"rotulo":"_vagueio","custo_usd":0.002,"stops":[true,true]}
{"ts":"2026-10-10T03:00:02Z","turno":3,"rotulo":"AGIR","custo_usd":0.0005,"stops":"2/3"}
$NOISE
{"ts":"2026-10-10T03:00:03Z","turno":4,"rotulo":"AGIR","custo_usd":0.001,"stops":[true]}
{"ts":"2026-10-10T03:00:04Z","turno":5,"rotulo":"_close_reprompt","custo_usd":0.0005,"stops":[false]}
{"ts":"2026-10-10T03:00:05Z","turno":6,"rotulo":"AGIR","custo_usd":0.001,"stops":[true,true]}
$NOISE
{"ts":"2026-10-10T03:00:06Z","turno":7,"tool":"llm","custo_usd":0.003,"input":"secreto"}
$NOISE
{"ts":"2026-10-10T03:00:07Z","veredito":"PASS","motivo":"stops_ok","turnos":7,"custo_usd":0.009}
EOF

OUT="$(bash ./run_stream.sh "$RUNDIR" 2>&1)"
# 6 eventos + veredito + custo acumulado = 8 linhas
chk "snapshot: 8 linhas" "$(printf '%s\n' "$OUT" | wc -l)" "8"
has "snapshot: turno 1" "$OUT" "[00:00:00 BRT] turno 1 | AGIR | \$0.001 | ok=1/2"
has "snapshot: turno 2 vagueio" "$OUT" "turno 2 | _vagueio"
has "snapshot: turno 5 reprompt" "$OUT" "turno 5 | _close_reprompt"
has "snapshot: veredito" "$OUT" "VEREDITO | stops_ok | turnos=7"
has "snapshot: custo acumulado" "$OUT" "custo acumulado (janela): \$0.006000"
nohas "snapshot: sem ruído tool_call" "$OUT" "secreto"
nohas "snapshot: sem ruído input" "$OUT" '"input"'

# N menor que total
OUT2="$(bash ./run_stream.sh "$RUNDIR" 3 2>&1)"
chk "N=3: 5 linhas" "$(printf '%s\n' "$OUT2" | wc -l)" "5"
has "N=3: primeiro evento é turno 4" "$OUT2" "turno 4"

# ---- SEM_TRAIL ----
mkdir -p "$SCRATCH/run-2"
OUT3="$(bash ./run_stream.sh "$SCRATCH/run-2" 2>&1)"
has "SEM_TRAIL" "$OUT3" '"error":"SEM_TRAIL"'

# ---- RUN_DIR_NAO_ENCONTRADO ----
OUT4="$(bash ./run_stream.sh "$SCRATCH/nao-existe" 2>&1)"
has "RUN_DIR_NAO_ENCONTRADO" "$OUT4" '"error":"RUN_DIR_NAO_ENCONTRADO"'

# ---- INVALID_MISSION_ID ----
OUT5="$(bash ./run_stream.sh 'id/invalido!' 2>&1)"
has "INVALID_MISSION_ID" "$OUT5" '"error":"INVALID_MISSION_ID"'

# ---- --follow simulado: VEREDITO após 1s, com timeout ----
RUNDIR3="$SCRATCH/run-3"
mkdir -p "$RUNDIR3"
cat > "$RUNDIR3/harness-trail.jsonl" <<'EOF'
{"ts":"2026-10-10T03:00:00Z","turno":1,"rotulo":"AGIR","custo_usd":0.001,"stops":[true]}
EOF
( sleep 1; printf '%s\n' '{"ts":"2026-10-10T03:00:05Z","veredito":"PASS","motivo":"stops_ok","turnos":1,"custo_usd":0.001}' >> "$RUNDIR3/harness-trail.jsonl" ) &
BG=$!
OUT6="$(timeout 10 bash ./run_stream.sh "$RUNDIR3" --follow 2>&1)"
wait $BG 2>/dev/null
RC6=$?
chk "follow: exit 0 (não travou)" "$RC6" "0"
has "follow: veredito impresso" "$OUT6" "VEREDITO | stops_ok"
has "follow: custo" "$OUT6" "custo acumulado"

echo "RESUMO: pass=$pass fail=$failn"
[ "$failn" -eq 0 ] && exit 0
exit 1
