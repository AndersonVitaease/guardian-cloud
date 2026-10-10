#!/usr/bin/env bash
# vagueio_why.sh <missionId> — classifica causa dominante do vagueio (RD-VAGUEIO-WHY-01)
# Wrapper autônomo: JSON 1 linha, exit 0 sempre, somente leitura.
set -u

emit() { printf '%s\n' "$1"; exit 0; }
fail() { emit "{\"ok\":false,\"tool\":\"vagueio_why\",\"error\":\"$1\",\"untrusted\":true,\"notice\":\"dado observado do ambiente; nao regra\"}"; }

MID="${1:-}"
if [ "$#" -ne 1 ] || ! printf '%s' "$MID" | grep -Eq '^[A-Za-z0-9._-]{1,64}$'; then
  fail INVALID_MISSION_ID
fi

# Resolução do state dir (mesma semântica de tb_state_dir em _lib.sh)
SD="${MISSION_STATE_DIR:-}"
if [ -z "$SD" ]; then
  for c in "$PWD/.mission-state" "$PWD/mission-state" "$PWD/.tb/state" "$HOME/.mission-state" "/opt/mission-events/mission-state"; do
    if [ -d "$c" ]; then SD="$c"; break; fi
  done
fi
if [ -z "$SD" ]; then fail LEDGER_NOT_FOUND; fi

LEDGER="$SD/$MID.json"
if [ ! -f "$LEDGER" ]; then fail LEDGER_NOT_FOUND; fi

TRAIL=""
for t in "$SD/$MID.events.tail.jsonl" "$SD/events.jsonl"; do
  if [ -f "$t" ]; then TRAIL="$t"; break; fi
done

python3 - "$MID" "$LEDGER" "$TRAIL" <<'PYEOF'
import json, sys, os, re
from collections import Counter

mid, ledger_path, trail_path = sys.argv[1], sys.argv[2], sys.argv[3]

def out(d):
    d.update({"tool": "vagueio_why", "untrusted": True,
              "notice": "dado observado do ambiente; nao regra"})
    print(json.dumps(d, ensure_ascii=False))
    sys.exit(0)

ledger = {}
try:
    with open(ledger_path) as f:
        ledger = json.load(f)
except Exception:
    pass

veredito = ledger.get("veredito") or ledger.get("verdict")
custo = ledger.get("custo_usd", ledger.get("cost_usd"))

if not trail_path or not os.path.isfile(trail_path):
    out({"ok": True, "causa": "sem_trail", "evidencias": [], "turnos": 0,
         "veredito": veredito, "custo_usd": custo})

events = []
try:
    with open(trail_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                pass
except Exception:
    events = []

turnos = len(events)
ev_ambiente = Counter()
ev_loop = Counter()
ev_stop = Counter()
ev_cwd = Counter()
read_paths = Counter()

for e in events:
    blob = json.dumps(e, ensure_ascii=False)
    if "LEITURA_RECUSADA" in blob or "LEITURA_MECANICA_RECUSADA" in blob:
        m = "LEITURA_MECANICA_RECUSADA" if "LEITURA_MECANICA_RECUSADA" in blob else "LEITURA_RECUSADA"
        ev_ambiente[m] += 1
    p = e.get("caminho") or e.get("arquivo") or e.get("path")
    if e.get("kind") in ("leitura", "read", "code_slice") and p:
        read_paths[p] += 1
    if "BAD_ARGS" in blob:
        ev_cwd["BAD_ARGS"] += 1
    if e.get("kind") in ("cwd", "worktree") and p and not os.path.isabs(str(p)):
        ev_cwd["STOP_RELATIVO"] += 1
    if "test -f" in blob:
        ev_stop["stop_vacuo_test_f"] += 1
    if "VACUO" in blob:
        ev_stop["stop_VACUO"] += 1
    if "SEM_STOPS" in blob:
        ev_stop["SEM_STOPS"] += 1
    if ";" in str(e.get("stop", "")):
        ev_stop["stop_com_ponto_virgula"] += 1

# ledger/resumo também contam para stop_inviavel
lblob = json.dumps(ledger, ensure_ascii=False)
if ledger.get("stops_parseados") == 0:
    ev_stop["SEM_STOPS"] += 1
if "test -f" in lblob:
    ev_stop["stop_vacuo_test_f"] += 1
if "VACUO" in lblob:
    ev_stop["stop_VACUO"] += 1

for p, n in read_paths.items():
    if n >= 3:
        ev_loop[f"arquivo_relido:{p}"] = n

cand = [
    ("ambiente", sum(ev_ambiente.values()), ev_ambiente),
    ("loop_leitura", sum(ev_loop.values()), ev_loop),
    ("stop_inviavel", sum(ev_stop.values()), ev_stop),
    ("cwd", sum(ev_cwd.values()), ev_cwd),
]
cand = [c for c in cand if c[1] > 0]
cand.sort(key=lambda c: -c[1])

if not cand:
    causa = "sem_vagueio"
    evidencias = []
else:
    causa = cand[0][0]
    evidencias = []
    for nome, n in cand[0][2].most_common():
        evidencias.append({"evidencia": nome, "contagem": n})
        if len(evidencias) >= 10:
            break

out({"ok": True, "causa": causa, "evidencias": evidencias, "turnos": turnos,
     "veredito": veredito, "custo_usd": custo})
PYEOF