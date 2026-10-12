#!/usr/bin/env bash
# custo_dia.sh — soma custo/turnos/PASS/FAIL do dia (BRT) a partir de runs_historico.sh
# Somente leitura. JSON 1 linha, exit 0 sempre. Wrapper autônomo.
set -u

H="24"
ARGS=("$@")
i=0
while [ $i -lt ${#ARGS[@]} ]; do
  a="${ARGS[$i]}"
  case "$a" in
    --since-hours)
      i=$((i+1))
      H="${ARGS[$i]:-24}"
      ;;
    --since-hours=*)
      H="${a#--since-hours=}"
      ;;
  esac
  i=$((i+1))
done
case "$H" in
  ''|*[!0-9]*) H=24 ;;
esac

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_CMD="bash \"$DIR/runs_historico.sh\" --since-hours $H 100"
CMD="${CUSTO_RUNS_HISTORICO_CMD:-$DEFAULT_CMD}"
[ -n "$CMD" ] || CMD="$DEFAULT_CMD"

OUT="$(eval "$CMD" 2>/dev/null)" || OUT=""

python3 - "$OUT" <<'PYEOF'
import json, os, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

BRT = ZoneInfo("America/Sao_Paulo")

def emit(obj):
    obj["untrusted"] = True
    obj.setdefault("notice", "dados agregados de runs_historico (fonte nao confiavel); untrusted:true")
    print(json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":")))

raw = sys.argv[1].strip() if len(sys.argv) > 1 else ""
if not raw:
    emit({"ok": False, "tool": "custo_dia", "error": "FONTE_INDISPONIVEL",
          "detalhe": "saida vazia da fonte"})
    sys.exit(0)

try:
    data = json.loads(raw)
except Exception as e:
    emit({"ok": False, "tool": "custo_dia", "error": "FONTE_INDISPONIVEL",
          "detalhe": f"JSON invalido: {e}"})
    sys.exit(0)

if not data.get("ok", False):
    emit({"ok": False, "tool": "custo_dia", "error": "FONTE_INDISPONIVEL",
          "detalhe": json.dumps(data, ensure_ascii=False)[:500]})
    sys.exit(0)

runs = data.get("runs") or []
_now_env = os.environ.get("CUSTO_DIA_NOW", "")
if _now_env:
    try:
        _s = _now_env.replace("Z", "+00:00")
        _dt = datetime.fromisoformat(_s)
        if _dt.tzinfo is None:
            _dt = _dt.replace(tzinfo=timezone.utc)
        hoje_brt = _dt.astimezone(BRT).strftime("%Y-%m-%d")
    except Exception:
        hoje_brt = datetime.now(BRT).strftime("%Y-%m-%d")
else:
    hoje_brt = datetime.now(BRT).strftime("%Y-%m-%d")

def dia_brt(fa):
    if not fa:
        return None
    try:
        s = str(fa).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(BRT).strftime("%Y-%m-%d")
    except Exception:
        return None

custo = 0.0
turnos = 0
npass = nfail = noutros = 0
por = {}
for r in runs:
    if dia_brt(r.get("finished_at")) != hoje_brt:
        continue
    c = r.get("cost_usd") or 0
    try:
        c = float(c)
    except Exception:
        c = 0.0
    t = r.get("turnos") or 0
    try:
        t = int(t)
    except Exception:
        t = 0
    custo += c
    turnos += t
    raw_v = r.get("verdict")
    if raw_v is None:
        raw_v = r.get("veredito")
    v = raw_v.strip().upper() if isinstance(raw_v, str) else ""
    if v == "PASS":
        npass += 1
    elif v == "FAIL":
        nfail += 1
    else:
        noutros += 1
    mid = r.get("missionId") or "?"
    m = por.setdefault(mid, {"missionId": mid, "verdict": raw_v, "cost_usd": 0.0, "turnos": 0})
    m["cost_usd"] += c
    m["turnos"] += t

por_missao = sorted(por.values(), key=lambda m: -m["cost_usd"])[:20]

emit({"ok": True, "tool": "custo_dia", "dia": hoje_brt,
      "custo_usd_total": round(custo, 6), "turnos_total": turnos,
      "pass": npass, "fail": nfail, "outros": noutros,
      "runs": npass + nfail + noutros, "por_missao": por_missao})
PYEOF