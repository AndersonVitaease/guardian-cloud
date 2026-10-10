#!/usr/bin/env bash
# RUN-STREAM-01: streamer do filme da run (snapshot/--follow), 0 LLM
# run_stream.sh <ID|run-dir> [--follow] [N] - filme da run no herdr (0 LLM).
# Sem --follow: snapshot das ultimas N linhas de evento (default 15), uma linha
# por turno: [HH:MM:SS BRT] turno K | ROTULO | $custo | ok=X/Y (+ VEREDITO).
# Com --follow: tail -n 0 -f no harness-trail.jsonl com o mesmo filtro; termina
# sozinho ao imprimir a linha VEREDITO (nunca daemon eterno, sem loop de sleep).
# Filtra ruido: so eventos de estado; tool_calls e conteudo NUNCA saem.
# RUN-STREAM-01C: resolver missionId escolhe run dir MAIS RECENTE por mtime
# entre tentativa-*/run-* (preferindo trail sem VEREDITO; ledger cwd pode estar
# stale); linha VEREDITO sai limpa (usd=X.XXX, extrai 'usd' de dict de custo);
# custo acumulado soma o campo REAL de custo dos eventos da janela.
# Erros tipados: INVALID_MISSION_ID | RUN_DIR_NAO_ENCONTRADO | SEM_TRAIL | BAD_ARGS | INVALID_N.
# exit 0 sempre; tb_audit UMA vez (snapshot usa tb_join).
set -u
start=$(date +%s%N)
ARGS=("$@")

# ---- lib opcional (instalada em /opt pelo supervisor); fallback local ----
TB_LIB="$(dirname "${BASH_SOURCE[0]}")/../tools-bash/_lib.sh"
if [ -f /opt/mission-events/tools-bash/_lib.sh ]; then
  source /opt/mission-events/tools-bash/_lib.sh
elif [ -f "$TB_LIB" ]; then
  source "$TB_LIB"
fi
if ! command -v tb_audit >/dev/null 2>&1; then
  tb_join(){ local IFS=$'\x1f'; printf '%s' "$*"; }
  tb_audit(){ return 0; }
  tb_fail(){ local t="$1" e="$2" s="$3"; shift 3
    tb_audit "$t" "$(tb_join "$@")" 0 "$e" "$s" || :
    printf '{"ok":false,"tool":"%s","error":"%s"}\n' "$t" "$e"; exit 0; }
fi

fail(){ local e="$1"; tb_fail run_stream "$e" "$start" "${ARGS[@]}"; }

# ---- parse de args ----
arg=""; follow=0; n=""; nargs=0
for a in "$@"; do
  case "$a" in
    --follow) follow=1 ;;
    [0-9]*) [ -z "$n" ] || fail BAD_ARGS; n="$a" ;;
    *)
      [ -z "$arg" ] || fail BAD_ARGS
      arg="$a"
      ;;
  esac
done
[ -n "$arg" ] || fail BAD_ARGS
[ "$nargs" -le 1 ] || fail BAD_ARGS
case "$n" in '') n=15 ;; *[!0-9]*) fail INVALID_N ;; esac
[ "$n" -ge 1 ] && [ "$n" -le 1000 ] || fail INVALID_N

# ---- resolucao do run_dir: caminho direto OU missionId ----
run_dir="$arg"
case "$arg" in
  *[!A-Za-z0-9._/-]*) fail INVALID_MISSION_ID ;;
esac
case "$arg" in
  */*) ;;
  *)
    case "$arg" in
      ''|*[!A-Za-z0-9._-]*) fail INVALID_MISSION_ID ;;
    esac
    # RUN-STREAM-01C: raiz de runs overridavel (testes hermeticos)
    RUNS_GLOB="${RUN_STREAM_RUN_GLOB:-/home/worker/wt-*/runs}"
    # 1) run dir MAIS RECENTE por mtime entre tentativa-*/run-* do mission dir;
    #    se o mais recente ja tem VEREDITO no trail, prefere um mais novo sem
    #    veredito (run ativo); fallback = o mais recente com veredito.
    run_dir=""
    for d in $(ls -dt ${RUNS_GLOB}/"$arg"/tentativa-*/run-* 2>/dev/null); do
      [ -d "$d" ] || continue
      t="$d/harness-trail.jsonl"
      [ -f "$t" ] || continue
      if grep -q '"veredito"' "$t" 2>/dev/null; then
        [ -n "$run_dir" ] || run_dir="$d"   # fallback: mais novo com veredito
      else
        run_dir="$d"
        break
      fi
    done
    # 2) fallback: ledger do state mirror (cwd registrado)
    if [ -z "$run_dir" ]; then
      sd="$(tb_state_dir 2>/dev/null || printf '/opt/mission-events/mission-state-mirror')"
      led="$sd/$arg.json"
      if [ -f "$led" ]; then
        run_dir="$(python3 -c '
import json,sys
try:
    d=json.load(open(sys.argv[1]))
    c=d.get("cwd")
    print(c if isinstance(c,str) else "")
except Exception:
    print("")
' "$led" 2>/dev/null)"
      fi
    fi
    ;;
esac
[ -n "$run_dir" ] || fail RUN_DIR_NAO_ENCONTRADO
[ -d "$run_dir" ] || fail RUN_DIR_NAO_ENCONTRADO

trail="$run_dir/harness-trail.jsonl"
[ -f "$trail" ] || fail SEM_TRAIL

# ---- filtro de eventos (python): formata 1 linha por turno + VEREDITO ----
FILTER='
import json, sys
mode = sys.argv[1]
n = int(sys.argv[2])
from datetime import datetime, timedelta, timezone
BRT = timezone(timedelta(hours=-3))
def brt(ts):
    try:
        t = ts.replace("Z", "+00:00")
        return datetime.fromisoformat(t).astimezone(BRT).strftime("%H:%M:%S")
    except Exception:
        return "??:??:??"
def custo_usd(obj):
    # RUN-STREAM-01C: campo real de custo; dict interno ({"calls":..,"usd":..})
    # contribui apenas com o valor de "usd".
    c = obj.get("custo_usd", obj.get("custo", 0))
    if isinstance(c, dict):
        c = c.get("usd", 0)
    try:
        return float(c)
    except Exception:
        return 0.0
out = []     # linhas formatadas
custos = []  # custo real de cada linha de turno (paralelo a out)
ver = None
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        obj = json.loads(line)
    except Exception:
        continue
    if not isinstance(obj, dict):
        continue
    # veredito: linha final — sai LIMPO (usd=X.XXX), sem vazar dict interno
    if obj.get("veredito") or obj.get("tool") in ("_veredito", "veredito") \
       or obj.get("evento") == "veredito":
        motivo = obj.get("motivo") or obj.get("reason") or "?"
        turnos = obj.get("turnos", obj.get("turno", "?"))
        ver = "[%s BRT] VEREDITO | %s | turnos=%s | usd=%.3f" % (
            brt(obj.get("ts", "")), motivo, turnos, custo_usd(obj))
        break
    # evento de estado: precisa turno + rotulo (rotulo/label/evento)
    rotulo = obj.get("rotulo") or obj.get("label") or obj.get("evento")
    if "turno" not in obj or not rotulo or rotulo in ("llm", "Bash", "Read",
                                                      "Write", "Edit"):
        continue
    if "input" in obj or "content" in obj or "output" in obj:
        continue  # tool_call/conteudo: nunca sai
    stops = obj.get("stops", obj.get("stops_ok"))
    okx = "?"
    if isinstance(stops, (list, tuple)):
        okx = "%d/%d" % (sum(1 for s in stops if s), len(stops))
    elif isinstance(stops, dict):
        okx = "%s/%s" % (stops.get("ok", "?"), stops.get("total", "?"))
    elif isinstance(stops, str) and "/" in stops:
        okx = stops
    c = custo_usd(obj)
    out.append("[%s BRT] turno %s | %s | $%s | ok=%s" %
               (brt(obj.get("ts", "")), obj.get("turno"), rotulo, c, okx))
    custos.append(c)
if mode == "snapshot":
    out = out[-n:]
    custos = custos[-n:]
if ver:
    out.append(ver)
for l in out:
    print(l)
# custo acumulado (janela): soma do campo REAL de custo dos eventos da janela
print("custo acumulado (janela): $%.6f" % sum(custos))
'
emit_events(){ python3 -c "$FILTER" "$1" "$n"; }

if [ "$follow" -eq 0 ]; then
  OUT="$(emit_events snapshot < "$trail")"
  tb_audit run_stream "$(tb_join "${ARGS[@]}")" 1 "null" "$start" || :
  printf '%s\n' "$OUT"
  exit 0
fi

# ---- follow: tail -n 0 -f via FIFO; termina ao imprimir VEREDITO ----
FIFO="$(mktemp -u /tmp/run_stream_fifo.XXXXXX)"
mkfifo "$FIFO" || fail SEM_TRAIL
tail -n 0 -f "$trail" > "$FIFO" &
TPID=$!
trap 'kill "$TPID" 2>/dev/null; rm -f "$FIFO"' EXIT
emit_events follow < "$FIFO"
kill "$TPID" 2>/dev/null
tb_audit run_stream "$(tb_join "${ARGS[@]}")" 1 "null" "$start" || :
exit 0