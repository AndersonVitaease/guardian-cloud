#!/usr/bin/env bash
# test_run_close.sh — fixtures minimos, 3 casos: (a) run-dir direto,
# (b) missionId via MISSION_STATE_DIR, (c) SEM_RESUMO.
set -u
cd "$(dirname "$0")"
FIX=".tmp-run-close-fixture"
rm -rf "$FIX"
mkdir -p "$FIX/run" "$FIX/state"
trap 'rm -rf "$FIX"' EXIT

cat > "$FIX/run/resumo.json" <<'EOF'
{"veredito":"ok","tentativas":2,"turnos":7,"custo_usd":0.42,
 "stops":[{"id":"0:cmd","ok":true},{"id":"1:cmd","ok":false}]}
EOF
cat > "$FIX/run/autoretry-summary.json" <<'EOF'
{"veredito":"ok","tentativas":2,"turnos":7,"custo_usd":0.42,
 "stops":[{"id":"0:cmd","ok":true},{"id":"1:cmd","ok":false}]}
EOF
cat > "$FIX/state/RUN-CLOSE-01-FIX.json" <<EOF
{"cwd":"$PWD/$FIX/run"}
EOF

pass=0
fail_(){ echo "FALHOU: $1"; exit 1; }

# (a) run-dir direto
OUT="$(bash ./run_close.sh "$PWD/$FIX/run")"
echo "$OUT" | grep -q '"ok":true' || fail_ "caso a ok"
echo "$OUT" | grep -q '"veredito":"ok"' || fail_ "caso a veredito"
echo "$OUT" | grep -q '"tentativas":2' || fail_ "caso a tentativas"
echo "$OUT" | grep -q '"turnos":7' || fail_ "caso a turnos"
echo "$OUT" | grep -q '"custo_usd":0.42' || fail_ "caso a custo"
echo "$OUT" | grep -q '"id":"0:cmd"' || fail_ "caso a stops"
echo "$OUT" | grep -q '"close_state":"desconhecido"' || fail_ "caso a close_state"
echo "$OUT" | grep -q '"commit_msg"' || fail_ "caso a commit_msg"
echo "$OUT" | grep -q '"git_dirty"' || fail_ "caso a git_dirty"
pass=$((pass+1))

# (b) missionId com MISSION_STATE_DIR
OUT="$(MISSION_STATE_DIR="$PWD/$FIX/state" bash ./run_close.sh RUN-CLOSE-01-FIX)"
echo "$OUT" | grep -q '"ok":true' || fail_ "caso b ok"
echo "$OUT" | grep -q '"id":"RUN-CLOSE-01-FIX"' || fail_ "caso b id"
echo "$OUT" | grep -q '"veredito":"ok"' || fail_ "caso b veredito"
echo "$OUT" | grep -q '"stops":\[{"id":"0:cmd","ok":true}' || fail_ "caso b stops"
pass=$((pass+1))

# (c) SEM_RESUMO
mkdir -p "$FIX/empty"
OUT="$(bash ./run_close.sh "$PWD/$FIX/empty")"
echo "$OUT" | grep -q '"error": *"SEM_RESUMO"' || fail_ "caso c SEM_RESUMO"
echo "$OUT" | grep -q '"dica": *' || fail_ "caso c dica"
pass=$((pass+1))

echo "casos ok: $pass/3"
echo "RUN-CLOSE-01 TESTE OK"
exit 0