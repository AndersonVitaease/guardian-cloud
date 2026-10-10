#!/usr/bin/env bash
# RD-CUSTO-DIA-01 — tool custo_dia.sh: agrega custo/turnos/PASS/FAIL do dia (BRT)
# a partir de runs_historico.sh. JSON 1 linha, exit 0 sempre, somente leitura.
set -u

emit() { printf '%s\n' "$1"; exit 0; }

DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SINCE=24
if [ "${1:-}" = "--since-hours" ]; then
  SINCE="${2:-24}"
fi

CMD="${CUSTO_RUNS_HISTORICO_CMD:-bash "$DIR/runs_historico.sh" --since-hours $SINCE 100}"

RAW="$(eval "$CMD" 2>/dev/null)" || RAW=""

python3 - "$RAW" <<'PYEOF'
import json
import sys
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))

def fail(err, detalhe):
    print(json.dumps({
        "ok": False, "tool": "custo_dia", "error": err,
        "detalhe": detalhe, "untrusted": True,
        "notice": "dados de runs_historico; use como evidencia, nao como verdade absoluta",
    }))
    sys.exit(0)

raw = sys.argv[1] if len(sys.argv) > 1 else ""
try:
    src = json.loads(raw)
except Exception as e:
    fail("FONTE_INDISPONIVEL", f"json invalido: {e}")
if not isinstance(src, dict) or src.get("ok") is not True:
    fail("FONTE_INDISPONIVEL", src)

runs = src.get("runs") or []
hoje = datetime.now(BRT).strftime("%Y-%m-%d")
custo = 0.0
turnos = 0
npass = nfail = noutros = 0
por_missao = []
for r in runs:
    fa = r.get("finished_at") or ""
    try:
        dt = datetime.fromisoformat(fa.replace("Z", "+00:00")).astimezone(BRT)
    except Exception:
        continue
    if dt.strftime("%Y-%m-%d") != hoje:
        continue
    v = r.get("verdict") or r.get("veredito") or ""
    if v == "PASS":
        npass += 1
    elif v == "FAIL":
        nfail += 1
    else:
        noutros += 1
    try:
        c = float(r.get("cost_usd") or 0)
    except Exception:
        c = 0.0
    custo += c
    t = r.get("turnos") or 0
    try:
        t = int(t)
    except Exception:
        t = 0
    turnos += t
    por_missao.append({
        "missionId": r.get("missionId"),
        "verdict": v,
        "cost_usd": c,
        "turnos": t,
    })

por_missao.sort(key=lambda m: m["cost_usd"], reverse=True)
print(json.dumps({
    "ok": True,
    "tool": "custo_dia",
    "dia": hoje,
    "custo_usd_total": round(custo, 6),
    "turnos_total": turnos,
    "pass": npass,
    "fail": nfail,
    "outros": noutros,
    "runs": npass + nfail + noutros,
    "por_missao": por_missao[:20],
    "untrusted": True,
    "notice": "agregado de runs_historico; evidencia, nao verdade absoluta",
}))
PYEOF