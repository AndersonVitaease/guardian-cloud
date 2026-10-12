#!/usr/bin/env bash
# GB-OFFICE-VIDA-02: prova E2E contra office REAL em porta efemera.
# Nunca toca a 8113 de producao. Padrao de aceite da ponte:
#   1) espelho fake + sessao.log com 3 linhas -> --once ->
#      GET /state: agente presente, status working/typing (NUNCA idle),
#      tool preenchido, activity/preview visivel.
#   2) rename pousado -> --once -> agente SAI do /state (gone/ausente).
set -euo pipefail

REPO_OFFICE="/home/worker/agent-office"
WT="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d /tmp/prova-gbofficevida02.XXXXXX)"
PORT="$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')"
MID="ag-prova-vida02"
cleanup() { kill "$OFFICE_PID" 2>/dev/null || true; wait "$OFFICE_PID" 2>/dev/null || true; rm -rf "$TMP"; }
trap cleanup EXIT

# office REAL de teste: HERMES_HOME tempdir, porta efemera
cd "$REPO_OFFICE"
HERMES_HOME="$TMP/home" python3 run.py --port "$PORT" >/dev/null 2>&1 &
OFFICE_PID=$!
cd "$WT"
for i in $(seq 1 50); do
  if curl -sf "http://127.0.0.1:$PORT/state" >/dev/null 2>&1; then break; fi
  sleep 0.2
done
curl -sf "http://127.0.0.1:$PORT/state" >/dev/null   # office de teste no ar

# espelho fake + sessao.log com 3 linhas de tipos diferentes
D="$TMP/ag-prova"; mkdir -p "$D"
printf '%s\n' \
  '[12/10 13:40 BRT] turno 3 | Read | 0ms | $0.01 | OK | relatorio.md' \
  '[12/10 13:41 BRT] turno 4 | Bash | 0ms | $0.02 | ERRO | prova.sh' \
  '[12/10 13:42 BRT] turno 5 | Edit | 0ms | $0.03 | OK | ponte.py' > "$D/sessao.log"
printf '{"id":"%s","status":"running"}\n' "$MID" > "$D/$MID.espelho.json"

run_ponte() {
  HERMES_HOME="$TMP/home" AGENT_OFFICE_PORT="$PORT" \
  ESPELHO_DIRS="$D" PONTE_STATE_FILE="$TMP/estado.json" \
  python3 ponte_office.py --once
}

state() { curl -sf "http://127.0.0.1:$PORT/state"; }

echo "== ciclo 1: atividade nova =="
run_ponte
S1="$(state)"
AG1="$(printf '%s' "$S1" | python3 -c '
import json,sys
st=json.load(sys.stdin)
a=[x for x in st.get("agents",[]) if x.get("id")==sys.argv[1]]
print(json.dumps(a[0] if a else {}))' "$MID")"
echo "agente apos ciclo 1: $AG1"
printf '%s' "$AG1" | python3 -c '
import json,sys
a=json.load(sys.stdin)
assert a, "FALHA: agente ausente do /state apos tool_start"
assert a["status"] in ("working","typing","thinking"), "FALHA: status %r (idle!) logo apos tool_start" % a["status"]
assert a.get("tool"), f"FALHA: tool vazio: {a}"
assert a.get("activity") or a.get("detail"), f"FALHA: sem activity/preview: {a}"
print("OK ciclo 1: status=%s tool=%s" % (a["status"], a.get("tool")))'

echo "== ciclo 2: sem atividade nova, janela curta => nada sobrescreve =="
run_ponte
S2="$(state)"
printf '%s' "$S2" | python3 -c '
import json,sys
st=json.load(sys.stdin)
a=[x for x in st.get("agents",[]) if x.get("id")==sys.argv[1]]
assert a, "FALHA: agente sumiu sem pousar"
assert a[0]["status"] in ("working","typing","thinking"), "FALHA: idle no mesmo ciclo de atividade: %r" % a[0]
print("OK ciclo 2: status=%s" % a[0]["status"])' "$MID"

echo "== ciclo 2b: sem atividade nova na janela de pausa => session_idle =="
# pause_interval() tem piso de 1.0s — espera a janela vencer de verdade
sleep 1.5
HERMES_HOME="$TMP/home" AGENT_OFFICE_PORT="$PORT" \
ESPELHO_DIRS="$D" PONTE_STATE_FILE="$TMP/estado.json" \
PONTE_PAUSE_INTERVAL=0 python3 ponte_office.py --once
S2b="$(state)"
printf '%s' "$S2b" | python3 -c '
import json,sys
st=json.load(sys.stdin)
a=[x for x in st.get("agents",[]) if x.get("id")==sys.argv[1]]
assert a, "FALHA: agente sumiu sem pousar"
assert a[0]["status"] in ("idle","paused","break"), "FALHA: esperado idle apos janela de pausa, got %r" % a[0]["status"]
print("OK ciclo 2b: status=%s (pausa desejada)" % a[0]["status"])' "$MID"

echo "== ciclo 3: pousado => agente SAI do /state =="
mv "$D/$MID.espelho.json" "$D/$MID.espelho.pousado.json"
run_ponte
S3="$(state)"
printf '%s' "$S3" | python3 -c '
import json,sys
st=json.load(sys.stdin)
a=[x for x in st.get("agents",[]) if x.get("id")==sys.argv[1]]
assert not a or a[0].get("status") in ("gone","done"), f"FALHA: pousado ainda na sala: {a}"
print("OK ciclo 3: pousado fora do piso (gone/ausente)")' "$MID"

echo "PROVA E2E GB-OFFICE-VIDA-02: PASS"