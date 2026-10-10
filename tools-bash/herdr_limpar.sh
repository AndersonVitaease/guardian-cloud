#!/usr/bin/env bash
# herdr_limpar.sh — limpa abas herdr de runs mortas (RD-ROUTER-ROTA-01).
# Lista abas via `herdr tab list`, cruza com runs ativas do runs_status.sh e
# FECHARIA cada aba cujo label comeca em RUN:/MISSION:/AGENTE: e cujo
# missionId (trecho entre ':' e '#') NAO esta entre as ativas.
# PADRAO DRY-RUN: lista as mortas sem fechar. Com --apply fecha de verdade
# (`herdr tab close <id>`), re conferindo runs_status imediatamente antes de
# cada fechamento. NUNCA fecha a aba de label 1 nem aba de run ativa.
# Saida: 1 linha JSON {ok,tool:herdr_limpar,dry_run,antes:[labels],
#                      fechadas:[{tab,label}],mantidas:[labels],ms}
# Env para teste hermetico: HERDR_BIN (binario do herdr) e RUNS_STATUS_BIN.
set -u
T0=$(date +%s%N)
LIB="$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
[ -r "$LIB" ] || { printf '{"ok":false,"tool":"herdr_limpar","error":"LIB_MISSING"}\n'; exit 0; }
. "$LIB"

APPLY=0
for _a in "$@"; do
  [ "$_a" = "--apply" ] && APPLY=1
done

HERDR_BIN="${HERDR_BIN:-herdr}"
RUNS_STATUS_BIN="${RUNS_STATUS_BIN:-/opt/mission-events/tools-bash/runs_status.sh}"

ACTIVE_JSON=$(RUNS_STATUS_BIN="$RUNS_STATUS_BIN" APPLY="$APPLY" python3 - "$RUNS_STATUS_BIN" <<'PY'
import json, subprocess, sys
rsb = sys.argv[1]
try:
    raw = subprocess.run([rsb], capture_output=True, text=True, timeout=30).stdout.strip()
    d = json.loads(raw.splitlines()[0])
except Exception:
    sys.exit(3)
if not d.get("ok"):
    sys.exit(4)
act = sorted(r.get("missionId", "") for r in d.get("runs", []) if r.get("active"))
print(json.dumps(act))
PY
)
RC=$?
[ $RC -ne 0 ] && tb_fail herdr_limpar "RUNS_STATUS_FALHOU" "$T0"
export ACTIVE_JSON

export HERDR_BIN APPLY T0
TB_JSON=$(python3 <<'PY'
import json, os, subprocess, sys, time
herdr = os.environ["HERDR_BIN"]
apply_mode = os.environ["APPLY"] == "1"
t0 = int(os.environ["T0"])
active = set(json.loads(os.environ["ACTIVE_JSON"]))
try:
    raw = subprocess.run([herdr, "tab", "list"], capture_output=True, text=True, timeout=30).stdout.strip()
    d = json.loads(raw)
except Exception:
    print(json.dumps({"error": "HERDR_FALHOU"}))
    sys.exit(0)
tabs = (d.get("result") or {}).get("tabs") or []
antes = [t.get("label", "") for t in tabs]

def mid_of(label):
    if ":" not in label:
        return None
    mid = label.split(":", 1)[1]
    if "#" in mid:
        mid = mid.split("#", 1)[0]
    return mid or None

fechadas, mortas, mantidas = [], [], []
for t in tabs:
    tab_id = t.get("tab_id", "")
    label = t.get("label", "")
    mid = mid_of(label)
    cand = label.split(":", 1)[0] in ("RUN", "MISSION", "AGENTE") and mid is not None
    if label == "1" or not cand or mid in active:
        mantidas.append(label)
        continue
    mortas.append((tab_id, label))
    if not apply_mode:
        continue
    # reconfere runs_status imediatamente antes de fechar
    try:
        raw2 = subprocess.run([os.environ["RUNS_STATUS_BIN"]], capture_output=True,
                              text=True, timeout=30).stdout.strip()
        d2 = json.loads(raw2)
        if not d2.get("ok"):
            act2 = None
        else:
            act2 = set(r.get("missionId", "") for r in d2.get("runs", []) if r.get("active"))
    except Exception:
        act2 = None
    if act2 is None or mid in act2:
        mantidas.append(label)
        continue
    try:
        c = subprocess.run([herdr, "tab", "close", tab_id], capture_output=True,
                           text=True, timeout=30)
        ok_close = c.returncode == 0
    except Exception:
        ok_close = False
    if ok_close:
        fechadas.append({"tab": tab_id, "label": label})
    else:
        mantidas.append(label)

out = {"ok": True, "tool": "herdr_limpar", "dry_run": not apply_mode,
       "antes": antes,
       "fechadas": fechadas if apply_mode else [],
       "mortas": [{"tab": t, "label": l} for t, l in mortas] if not apply_mode else [],
       "mantidas": mantidas,
       "ms": max(1, int((time.time_ns() - t0) / 1e6))}
print(json.dumps(out, ensure_ascii=False))
PY
)
if [ -n "$(printf '%s' "$TB_JSON" | python3 -c 'import json,sys;d=json.loads(sys.stdin.read().splitlines()[0]);print("e" if d.get("error") else "")' 2>/dev/null)" ]; then
  tb_fail herdr_limpar "HERDR_FALHOU" "$T0"
fi
tb_emit herdr_limpar "$TB_JSON" "$T0"