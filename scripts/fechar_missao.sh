#!/bin/bash
# DESP-FECHO-ROBUSTO-01: fecho robusto de missao (ExecStopPost). Uso: fechar_missao.sh {id}
ID="${1:-}"
LOG="/tmp/fechar_missao-${ID}.log"
set +e
touch "$LOG"
log(){ echo "[$(date '+%F %T')] $*" >> "$LOG"; }
step(){ # step <nome> <cmd...> : independente, 2 tentativas
  local nome="$1"; shift
  local tent rc=1
  for tent in 1 2; do
    "$@" >>"$LOG" 2>&1
    rc=$?
    if [ $rc -eq 0 ]; then log "OK ${nome} (tentativa ${tent})"; return 0; fi
    log "FAIL ${nome} rc=${rc} (tentativa ${tent})"
  done
  log "FAIL ${nome} (esgotado)"
  return 1
}
if [ -z "$ID" ]; then log "FAIL ARG id ausente"; exit 0; fi
step ledger_fechar /usr/bin/python3 /home/worker/harness-s2/scripts/ledger_missao.py fechar "$ID" --resumo "/tmp/resumo-${ID}.json"
step tab_reap /usr/bin/bash /opt/mission-events/tools-bash/tab_reap.sh --apply
step vigia_chat /home/worker/harness-s2/scripts/vigia_chat.sh "$ID" --send
log "FIM ${ID}"
exit 0
