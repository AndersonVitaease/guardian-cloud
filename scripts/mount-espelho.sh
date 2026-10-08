#!/usr/bin/env bash
set -euo pipefail
# mount-espelho.sh <runs_glob> <seed> [label]
# Espera run dir com seed<seed> e monta espelho herdr (tab + pane tail).

RUNS_GLOB="${1:?uso: mount-espelho.sh <runs_glob> <seed> [label]}"
SEED="${2:?uso: mount-espelho.sh <runs_glob> <seed> [label]}"
LABEL="${3:-ESPELHO}"

# 1. Loop de espera: até 60s (sleep 2) por run dir contendo seed<seed>
RUN_DIR=""
for _ in $(seq 1 30); do
  RUN_DIR="$(ls -dt ${RUNS_GLOB} 2>/dev/null | grep -- "seed${SEED}" | head -1 || true)"
  if [[ -n "${RUN_DIR}" ]]; then
    break
  fi
  RUN_DIR=""
  sleep 2
done
if [[ -z "${RUN_DIR}" ]]; then
  echo "ERRO: nenhum run dir com seed${SEED} em ${RUNS_GLOB} após 60s" >&2
  exit 1
fi
echo "RUN_DIR=${RUN_DIR}"

# 2. Cria tab e extrai pane id do JSON
TAB_JSON="$(herdr tab create --label "RUN:${LABEL}#s${SEED}")"
PANE_ID="$(printf '%s' "${TAB_JSON}" | python3 -c "import json,sys;print(json.load(sys.stdin)['result']['root_pane']['pane_id'])")"

# 3. Monta pane tail
herdr pane run "${PANE_ID}" "tail -n 15 -F ${RUN_DIR}/harness-pane.log"

echo "${PANE_ID}"