#!/usr/bin/env bash
# prova-GB-SESSAO-GUARD-01.sh — prova hermetica do sessao_guard.sh (tempdir, sem rede, ps fake)
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
FAIL=0
ok() { echo "PASS: $1"; }
bad() { echo "FAIL: $1"; FAIL=$((FAIL+1)); }

# ---- (a) par vivo com filho fake => NAO mata
cat >"$T/ps_a" <<'EOF'
u 101 1 S ? x ui-tui/dist/entry.js
u 102 101 S ? x python3 -m tui_gateway.entry
u 103 102 S ? x bash /snap/hermes/scratch/chat.sh Hermes sessao
EOF
GUARD_PS_CMD="cat $T/ps_a" GUARD_LOG="$T/log_a" GUARD_DRY_RUN=1 bash "$DIR/sessao_guard.sh" >/dev/null 2>&1
grep -q "GUARD_PAR_VIVO" "$T/log_a" && ok "a: par vivo nao morto" || bad "a: par vivo"

# ---- (b) par orfao sem filhos com lock colidindo => mata e loga LOCK_COLIDINDO
cat >"$T/ps_b" <<'EOF'
u 201 1 S ? x ui-tui/dist/entry.js
u 202 201 S ? x python3 -m tui_gateway.entry
u 203 1 S ? x ui-tui/dist/entry.js
u 204 203 S ? x python3 -m tui_gateway.entry
EOF
mkdir -p "$T/env/202" "$T/env/204"
printf 'HERMES_SESSION_ID=sess-X\0' >"$T/env/202/environ"
printf 'HERMES_SESSION_ID=sess-X\0' >"$T/env/204/environ"
touch -d '1 minute ago' "$T/agent.log"
GUARD_PS_CMD="cat $T/ps_b" GUARD_LOG="$T/log_b" GUARD_ENV_DIR="$T/env" GUARD_AGENT_LOG="$T/agent.log" GUARD_STALE_MIN=120 GUARD_DRY_RUN=1 bash "$DIR/sessao_guard.sh" >/dev/null 2>&1
grep -q "LOCK_COLIDINDO" "$T/log_b" && ok "b: lock colidindo detectado" || bad "b: lock colidindo"
grep -q "GUARD_DRY_RUN mataria" "$T/log_b" && ok "b: kill registrado" || bad "b: kill registrado"

# ---- (c) par R sobrevivente a SIGTERM fake => kill -9
cat >"$T/ps_c" <<'EOF'
u 301 1 R ? x ui-tui/dist/entry.js
u 302 301 R ? x python3 -m tui_gateway.entry
EOF
mkdir -p "$T/env/302"
printf 'HERMES_SESSION_ID=sess-Y\0' >"$T/env/302/environ"
touch -d '2 hours ago' "$T/agent.log"
GUARD_PS_CMD="cat $T/ps_c" GUARD_LOG="$T/log_c" GUARD_ENV_DIR="$T/env" GUARD_AGENT_LOG="$T/agent.log" GUARD_STALE_MIN=1 bash "$DIR/sessao_guard.sh" >/dev/null 2>&1
grep -q "GUARD_KILL" "$T/log_c" && ok "c: kill de orfao stale" || bad "c: kill stale"
grep -q "GUARD_ESCALADO" "$T/log_c" && ok "c: escalou kill -9 (R sobrevivente)" || bad "c: escalou kill -9"

# ---- (d) erro de leitura => fail-open
GUARD_PS_CMD="false" GUARD_LOG="$T/log_d" bash "$DIR/sessao_guard.sh" >/dev/null 2>&1
grep -q "GUARD_FAIL_OPEN" "$T/log_d" && ok "d: fail-open em erro de leitura" || bad "d: fail-open"

echo "RESUMO: $FAIL falhas"
exit $FAIL