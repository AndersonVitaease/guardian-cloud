#!/usr/bin/env bash
# prova-GB-SESSAO-GUARD-02.sh - cura do finding do 01: casamento node/gateway por ARVORE de processos.
# (a) python FILHO do node vivo com filho de chat => PAR_VIVO;
# (b) mesma topologia, orfao sem filhos + lock colidindo => KILL;
# (c) node FILHO do python => tambem casa;
# (d) gw fora da arvore => candidato orfao (nao skip silencioso);
# (e) fail-open preservado.
set -u
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
FAIL=0
ok() { echo "PASS: $1"; }
bad() { echo "FAIL: $1"; FAIL=$((FAIL+1)); }

# ---- (a) python FILHO do node, com filho de chat vivo => PAR_VIVO (nao mata)
cat >"$T/ps_a" <<'PSEOF'
u 101 1 S ? x /root/.hermes/tools/node-26.7.0/bin/node --expose-gc ui-tui/dist/entry.js
u 102 101 S ? x /root/.hermes/tools/python-3.14.7+/bin/python3 -m tui_gateway.entry
u 103 102 S ? x bash /snap/hermes/scratch/chat.sh Hermes sessao
PSEOF
GUARD_PS_CMD="cat $T/ps_a" GUARD_LOG="$T/log_a" GUARD_DRY_RUN=1 bash "$DIR/sessao_guard.sh" >/dev/null 2>&1
grep -q "GUARD_PAR_VIVO node=101 gw=102" "$T/log_a" && ok "a: python filho do node + chat vivo => PAR_VIVO" || bad "a: PAR_VIVO topologia filho"

# ---- (b) mesma topologia, orfao sem filhos + lock colidindo => KILL
cat >"$T/ps_b" <<'PSEOF'
u 201 1 S ? x node --expose-gc ui-tui/dist/entry.js
u 202 201 S ? x python3 -m tui_gateway.entry
u 203 1 S ? x node --expose-gc ui-tui/dist/entry.js
u 204 203 S ? x python3 -m tui_gateway.entry
PSEOF
mkdir -p "$T/env/202" "$T/env/204"
printf 'HERMES_SESSION_ID=sess-X\0' >"$T/env/202/environ"
printf 'HERMES_SESSION_ID=sess-X\0' >"$T/env/204/environ"
touch -d '1 minute ago' "$T/agent.log"
GUARD_PS_CMD="cat $T/ps_b" GUARD_LOG="$T/log_b" GUARD_ENV_DIR="$T/env" GUARD_AGENT_LOG="$T/agent.log" GUARD_STALE_MIN=120 GUARD_DRY_RUN=1 bash "$DIR/sessao_guard.sh" >/dev/null 2>&1
grep -q "LOCK_COLIDINDO" "$T/log_b" && ok "b: lock colidindo detectado (python filho do node)" || bad "b: lock colidindo"
grep -q "GUARD_DRY_RUN mataria node=201 gw=202" "$T/log_b" && ok "b: par casado por arvore (201<->202)" || bad "b: casamento 201/202"
grep -q "GUARD_DRY_RUN mataria node=203 gw=204" "$T/log_b" && ok "b: par casado por arvore (203<->204)" || bad "b: casamento 203/204"

# ---- (c) node FILHO do python => tambem casa
cat >"$T/ps_c" <<'PSEOF'
u 301 1 S ? x python3 -m tui_gateway.entry
u 302 301 S ? x node --expose-gc ui-tui/dist/entry.js
u 303 302 S ? x bash /snap/hermes/scratch/chat.sh Hermes sessao
PSEOF
GUARD_PS_CMD="cat $T/ps_c" GUARD_LOG="$T/log_c" GUARD_DRY_RUN=1 bash "$DIR/sessao_guard.sh" >/dev/null 2>&1
grep -q "GUARD_PAR_VIVO node=302 gw=301" "$T/log_c" && ok "c: node filho do python => casa e PAR_VIVO" || bad "c: topologia inversa"

# ---- (d) gw fora da arvore do node => candidato orfao, NUNCA skip silencioso
cat >"$T/ps_d" <<'PSEOF'
u 401 1 S ? x node --expose-gc ui-tui/dist/entry.js
u 402 999 S ? x python3 -m tui_gateway.entry
PSEOF
GUARD_PS_CMD="cat $T/ps_d" GUARD_LOG="$T/log_d" GUARD_DRY_RUN=1 bash "$DIR/sessao_guard.sh" >/dev/null 2>&1
grep -q "GUARD_ORFAO_CANDIDATO node=401 gw= causa=GW_FORA_ARVORE" "$T/log_d" && ok "d: gw fora da arvore => candidato orfao" || bad "d: candidato orfao node"
grep -q "GUARD_ORFAO_CANDIDATO node= gw=402 causa=NODE_FORA_ARVORE" "$T/log_d" && ok "d: node fora da arvore => candidato orfao" || bad "d: candidato orfao gw"
! grep -q "GUARD_PAR_OK node=401 gw=" "$T/log_d" && ok "d: sem GUARD_PAR_OK falso-positivo" || bad "d: skip silencioso (regressao do 01)"

# ---- (e) fail-open preservado
GUARD_PS_CMD="false" GUARD_LOG="$T/log_e" bash "$DIR/sessao_guard.sh" >/dev/null 2>&1
grep -q "GUARD_FAIL_OPEN" "$T/log_e" && ok "e: fail-open em erro de leitura" || bad "e: fail-open"

echo "RESUMO: $FAIL falhas"
exit $FAIL
