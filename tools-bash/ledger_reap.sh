#!/usr/bin/env bash
# ledger_reap.sh — RD-ROUTER-BRIEFING-01
# Lista/fecha ledgers fantasma (status nao terminal, sem unit ativa).
# Wrapper AUTONOMO: nao faz source de _lib.sh; reimplementa emit/fail inline.
# JSON de 1 linha, exit 0 sempre, falha tipada, untrusted:true, notice.
set -u

APPLY=0
N=50
for a in "$@"; do
  case "$a" in
    --apply) APPLY=1 ;;
    [0-9]*) N="$a" ;;
  esac
done

emit(){ printf '%s\n' "$1"; exit 0; }
fail(){ printf '%s\n' "$1"; exit 0; }

# Resolucao de state_dir — MESMA de tools-bash/_lib.sh:16
STATE_DIR=""
if [ -n "${MISSION_STATE_DIR:-}" ]; then
  STATE_DIR="$MISSION_STATE_DIR"
elif [ -r /root/.hermes/mission-state ] && [ -x /root/.hermes/mission-state ]; then
  STATE_DIR="/root/.hermes/mission-state"
else
  STATE_DIR="/opt/mission-events/mission-state-mirror"
fi

UNITS_CMD="${LEDGER_REAP_UNITS_CMD:-systemctl list-units 'harness-*' --all --no-legend}"
LEDGER_SCRIPT="${LEDGER_REAP_LEDGER_SCRIPT:-/home/worker/harness-s2/scripts/ledger_missao.py}"

# Fail-safe: consulta de units falhou -> SYSTEMCTL_FAILED, nao fecha nada
if ! UNITS_OUT="$($UNITS_CMD 2>/dev/null)"; then
  fail '{"tool":"ledger_reap","ok":false,"error":"SYSTEMCTL_FAILED","untrusted":true,"notice":"consulta de units indisponivel; nada foi fechado"}'
fi

export LEDGER_REAP_STATE_DIR="$STATE_DIR" LEDGER_REAP_UNITS="$UNITS_OUT" \
       LEDGER_REAP_APPLY="$APPLY" LEDGER_REAP_N="$N" LEDGER_REAP_SCRIPT="$LEDGER_SCRIPT"

python3 - <<'PYEOF'
import datetime, glob, json, os, subprocess, sys, tempfile

STATE = os.environ["LEDGER_REAP_STATE_DIR"]
UNITS = os.environ.get("LEDGER_REAP_UNITS", "")
APPLY = os.environ["LEDGER_REAP_APPLY"] == "1"
N = int(os.environ["LEDGER_REAP_N"])
LEDGER_SCRIPT = os.environ["LEDGER_REAP_SCRIPT"]
TERMINAIS = ("closed", "failed", "cancelled", "delivered")

def emit(obj):
    obj.setdefault("tool", "ledger_reap")
    obj.setdefault("untrusted", True)
    obj.setdefault("notice", "dados de state_dir nao confiaveis; dry-run nao muta nada")
    print(json.dumps(obj, ensure_ascii=False))
    sys.exit(0)

units_ativos = set()
for line in UNITS.splitlines():
    parts = line.split()
    if parts:
        units_ativos.add(parts[0].strip())

def unit_ativa(mid):
    return any(u.startswith("harness-%s-s" % mid) for u in units_ativos)

def idade(ts):
    try:
        t = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds()
    except Exception:
        return None

itens, resultados = [], []
for path in sorted(glob.glob(os.path.join(STATE, "*.json")))[:N]:
    if os.path.basename(path).startswith("resumo-"):
        continue
    try:
        with open(path, encoding="utf-8") as f:
            led = json.load(f)
    except Exception:
        continue
    mid = led.get("missionId") or os.path.basename(path)[:-5]
    status = led.get("status")
    if status in TERMINAIS:
        continue
    if unit_ativa(mid):
        continue
    itens.append({
        "missionId": mid, "status": status,
        "custo_usd": led.get("custo_usd") or led.get("custo"),
        "idade": idade(led.get("ts_inicio") or led.get("ts")),
    })

if not APPLY:
    emit({"ok": True, "dry_run": True, "itens": itens,
          "notice": "dry-run: nenhum ledger foi alterado"})

for it in itens:
    mid = it["missionId"]
    path = os.path.join(STATE, "%s.json" % mid)
    resumo = os.path.join(STATE, "resumo-%s.json" % mid)
    try:
        if os.path.exists(resumo):
            r = subprocess.run(
                [sys.executable, LEDGER_SCRIPT, "fechar", mid,
                 "--resumo", "/tmp/resumo-%s.json" % mid],
                capture_output=True, text=True)
            resultados.append({"missionId": mid, "acao": "fechar_script",
                               "ok": r.returncode == 0,
                               "stderr": r.stderr[-200:] or None})
        else:
            with open(path, encoding="utf-8") as f:
                led = json.load(f)
            led["status"] = "failed"
            led["motivo"] = "fantasma_sem_unit"
            fd, tmp = tempfile.mkstemp(dir=STATE)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(led, f, ensure_ascii=False)
            os.replace(tmp, path)
            resultados.append({"missionId": mid, "acao": "marcar_failed",
                               "ok": True})
    except Exception as e:
        resultados.append({"missionId": mid, "acao": "erro", "ok": False,
                           "erro": str(e)})

emit({"ok": True, "dry_run": False, "itens": itens, "resultados": resultados,
      "notice": "apply: ledgers fantasmas fechados/marcados"})
PYEOF