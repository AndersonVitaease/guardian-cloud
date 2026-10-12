#!/bin/bash
# MISSAO-FECHAR-TIMEOUT-01: fecho robusto de missao (ExecStopPost) com TIMEOUT por step.
# Uso: fechar_missao.sh {id}
#
# Bug curado (11/09/2026 ~09:07 BRT): o --apply do fecho pendurou 58min pos-merge.
# Causa: step() rodava cada comando sem teto de tempo (tab_reap.sh --apply chama
# "herdr tab list/close" via command substitution/subprocess SEM timeout interno)
# e sem resultado tipado — o fecho podia rodar para sempre sem evidencia.
#
# Agora: cada step (ledger, mirror, tab_reap, vigia_chat) roda em sessao propria
# (setsid) vigiada por watchdog: se exceder FECHAR_STEP_TIMEOUT (default 240s,
# override por env), o grupo inteiro leva TERM (e KILL apos FECHAR_KILL_WAIT,
# default 10s). Step que estoura timeout fica tipado TIMEOUT_STEP — SEM retry
# (retry replicaria o pendurado) — os steps restantes ficam PULADO_TIMEOUT e o
# fecho ABORTA com ok:false. Nao existe mais caminho de loop infinito.
#
# Resultado tipado: /tmp/fechar_missao-{id}.steps.json
#   {ok, status: ok|falha_parcial|timeout_step, timeout_step_s, duracao_s,
#    steps: [{step, cmd, status: OK|FALHA|TIMEOUT_STEP, rc, timeout_excedido,
#             tentativas, duracao_s}], steps_pulados: [...], log}
# Exit tipado: 0 = ok | falha_parcial (fail-open preservado do DESP-FECHO-ROBUSTO-01;
#              o JSON carrega ok:false e o status do step que falhou)
#              2 = timeout_step (abortado, sem rodar os steps restantes)
#              0 sem-id (legacy: arg ausente so registra FAIL ARG)
# Prova hermetica: FECHAR_FAKE=<dir> faz cada step rodar <dir>/<step>.sh se
# executavel (usado por scripts/prova-fechar-timeout-01.sh; sem isso, comandos
# reais inalterados).
ID="${1:-}"
if [ -z "$ID" ]; then
  echo "[$(date '+%F %T')] FAIL ARG id ausente" >> /tmp/fechar_missao-.log
  exit 0
fi
LOG="/tmp/fechar_missao-${ID}.log"
STEPS_JSON="/tmp/fechar_missao-${ID}.steps.json"
STEP_TIMEOUT="${FECHAR_STEP_TIMEOUT:-240}"
KILL_WAIT="${FECHAR_KILL_WAIT:-10}"
case "$STEP_TIMEOUT" in ''|*[!0-9]*) STEP_TIMEOUT=240 ;; esac
case "$KILL_WAIT" in ''|*[!0-9]*) KILL_WAIT=10 ;; esac
[ "$STEP_TIMEOUT" -lt 1 ] && STEP_TIMEOUT=1
[ "$KILL_WAIT" -lt 1 ] && KILL_WAIT=1
FAKE="${FECHAR_FAKE:-}"
set +e
touch "$LOG"
log(){ echo "[$(date '+%F %T')] $*" >> "$LOG"; }

TSV="$(mktemp "/tmp/fechar_missao-${ID}.tsv.XXXXXX")"
STATE="$(mktemp -d "/tmp/fechar_missao-${ID}.state.XXXXXX")"
INICIO_ISO="$(date '+%FT%T%:z')"
INICIO_EPOCH="$(date +%s)"
ABORT=0
trap 'rm -rf "$STATE" "$TSV" 2>/dev/null' EXIT
trap 'ABORT=1; emitir_json timeout_step 0; log "FIM ${ID} status=timeout_step (sinal)"; exit 2' INT TERM

# emitir_json <status_final> <ok:1|0>: monta steps.json tipado a partir do TSV.
emitir_json(){
  local status_final="$1" ok_final="$2"
  FIM_ISO="$(date '+%FT%T%:z')"
  TOTAL_DUR=$(( $(date +%s) - INICIO_EPOCH ))
  TSV="$TSV" STEPS_JSON="$STEPS_JSON" JID="$ID" LOGP="$LOG" \
  TMS="$STEP_TIMEOUT" INI="$INICIO_ISO" FIM="$FIM_ISO" DUR="$TOTAL_DUR" \
  ABRT="$ABORT" OKF="$ok_final" STF="$status_final" \
  python3 - <<'PY'
import json, os
linhas = []
try:
    with open(os.environ["TSV"], encoding="utf-8") as f:
        for l in f:
            p = l.rstrip("\n").split("\t")
            while len(p) < 7:
                p.append("")
            linhas.append(p)
except OSError:
    pass
steps, pulados = [], []
for nome, cmd, status, rc, to, tent, dur in linhas:
    e = {
        "step": nome,
        "cmd": cmd,
        "status": status,
        "rc": int(rc) if rc.isdigit() else None,
        "timeout_excedido": to == "1",
        "tentativas": int(tent) if tent.isdigit() else 0,
        "duracao_s": int(dur) if dur.isdigit() else 0,
    }
    if status == "PULADO_TIMEOUT":
        pulados.append(e)
    else:
        steps.append(e)
out = {
    "id": os.environ["JID"],
    "fecho": "MISSAO-FECHAR-TIMEOUT-01",
    "ok": os.environ["OKF"] == "1",
    "status": os.environ["STF"],
    "timeout_step_s": int(os.environ["TMS"]),
    "inicio": os.environ["INI"],
    "fim": os.environ["FIM"],
    "duracao_s": int(os.environ["DUR"]),
    "abortado_timeout": os.environ["ABRT"] == "1",
    "steps": steps,
    "steps_pulados": pulados,
    "log": os.environ["LOGP"],
}
with open(os.environ["STEPS_JSON"], "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
PY
}

# run_step <nome> <cmd...>: timeout por step + resultado tipado.
# Falha comum: 2 tentativas (comportamento legado preservado).
# Timeout: SEM retry, tipa TIMEOUT_STEP, aborta o fecho (ABORT=1).
run_step(){
  local nome="$1"; shift
  if [ "$ABORT" = "1" ]; then
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$nome" "$*" "PULADO_TIMEOUT" "-" 0 0 0 >> "$TSV"
    return 2
  fi
  local flag="$STATE/to-$nome.flag"
  local tent rc=1 dur=0 t0 t1 to=0 pid sup prazo
  rm -f "$flag"
  for tent in 1 2; do
    t0=$(date +%s)
    prazo=$((t0 + STEP_TIMEOUT))
    setsid "$@" >>"$LOG" 2>&1 &
    pid=$!
    # watchdog: no prazo grava flag, manda TERM no grupo; KILL apos KILL_WAIT.
    # stdout/stderr -> /dev/null: sleep residual NAO pode segurar pipe de caller
    # (command substitution esperaria EOF de todos os fds herdados).
    ( while kill -0 "$pid" 2>/dev/null; do
        if [ "$(date +%s)" -ge "$prazo" ]; then
          : > "$flag"; kill -TERM -- -"$pid" 2>/dev/null
          sleep "$KILL_WAIT"; kill -KILL -- -"$pid" 2>/dev/null
          break
        fi
        sleep 1
      done ) >/dev/null 2>&1 &
    sup=$!
    wait "$pid"; rc=$?
    t1=$(date +%s); dur=$((t1 - t0))
    kill -KILL -- -"$pid" 2>/dev/null  # mop-up de netos sobreviventes ao TERM
    kill "$sup" 2>/dev/null; wait "$sup" 2>/dev/null
    if [ -f "$flag" ]; then
      # conservador: flag so existe se o prazo estourou (mesmo que rc==0)
      to=1
      log "TIMEOUT_STEP ${nome} timeout=${STEP_TIMEOUT}s dur=${dur}s (abortado, sem retry)"
      printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$nome" "$*" "TIMEOUT_STEP" "$rc" 1 "$tent" "$dur" >> "$TSV"
      ABORT=1
      return 2
    fi
    if [ $rc -eq 0 ]; then
      log "OK ${nome} (tentativa ${tent}, ${dur}s)"
      printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$nome" "$*" "OK" 0 0 "$tent" "$dur" >> "$TSV"
      return 0
    fi
    log "FAIL ${nome} rc=${rc} (tentativa ${tent}, ${dur}s)"
  done
  log "FAIL ${nome} (esgotado)"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$nome" "$*" "FALHA" "$rc" 0 "$tent" "$dur" >> "$TSV"
  return 1
}

# fake_step <nome> <cmd...>: override hermetico de prova (FECHAR_FAKE), sem eval.
fake_step(){
  local nome="$1"; shift
  if [ -n "$FAKE" ] && [ -x "$FAKE/${nome}.sh" ]; then
    run_step "$nome" /bin/bash "$FAKE/${nome}.sh" "$ID"
  else
    run_step "$nome" "$@"
  fi
}

fake_step ledger_fechar /usr/bin/python3 /home/worker/harness-s2/scripts/ledger_missao.py fechar "$ID" --resumo "/tmp/resumo-${ID}.json"
fake_step mirror_fechar /usr/bin/python3 /home/worker/harness-s2/scripts/fechar_mirror.py "$ID" --resumo "/tmp/resumo-${ID}.json"
fake_step tab_reap /usr/bin/bash /opt/mission-events/tools-bash/tab_reap.sh --apply
fake_step vigia_chat /home/worker/harness-s2/scripts/vigia_chat.sh "$ID" --send

TOTAL_DUR=$(( $(date +%s) - INICIO_EPOCH ))
if [ "$ABORT" = "1" ]; then
  emitir_json timeout_step 0
  log "FIM ${ID} status=timeout_step ok=false dur=${TOTAL_DUR}s"
  exit 2
fi
if grep -q "$(printf '\t')FALHA$(printf '\t')" "$TSV" 2>/dev/null; then
  emitir_json falha_parcial 0
  log "FIM ${ID} status=falha_parcial ok=false dur=${TOTAL_DUR}s (fail-open, exit 0)"
  exit 0
fi
emitir_json ok 1
log "FIM ${ID} status=ok ok=true dur=${TOTAL_DUR}s"
exit 0
