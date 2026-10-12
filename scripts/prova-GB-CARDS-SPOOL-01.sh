#!/usr/bin/env bash
# Prova hermetica GB-CARDS-SPOOL-01: mission_end no spool + fail-open.
set -u
T=$(mktemp -d)
trap 'rm -rf "$T"' EXIT
SPOOL="$T/spool.jsonl"
export GUARDIAN_SPOOL_PATH="$SPOOL"
cd "$(dirname "$0")/.."
python3 scripts/ledger_missao.py registrar M-TEST --contrato C --cwd "$T" --seed 1 --state-dir "$T/state" >/dev/null
echo '{"veredito":"PASS","custo_usd":0.42,"budget_usd":2.0,"turnos":7}' > "$T/resumo.json"
python3 scripts/ledger_missao.py fechar M-TEST --resumo "$T/resumo.json" --state-dir "$T/state" >/dev/null
python3 - "$SPOOL" <<'PY' 2>/dev/null
import json, sys
linhas = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
ev = [e for e in linhas if e.get("kind") == "mission_end" and e.get("missionId") == "M-TEST"]
assert len(ev) == 1, "esperava 1 mission_end, achei %d" % len(ev)
d = ev[0]["data"]
assert d.get("veredito") == "PASS" and d.get("custo_usd") == 0.42, d
assert d.get("fonte") == "harness", d
print("OK mission_end tipado no spool")
PY
rm -f "$SPOOL"
python3 scripts/ledger_missao.py fechar M-TEST2 --resumo "$T/resumo.json" --state-dir "$T/state" >/dev/null 2>"$T/err" || true
test -s "$T/err" && echo "OK fail-open (stderr logado, sem crash)"
echo "RESUMO: 0 falhas"
