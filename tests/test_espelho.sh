#!/usr/bin/env bash
# test_espelho.sh — teste hermetico do espelho.sh no herdr real.
# Cria aba de teste, envia "echo ESPELHO-EXIT-0", espera, fecha a aba.
set -uo pipefail

FAILS=0
TS=$(date +%Y%m%d%H%M%S)
LABEL="TESTE-ESPELHO-${TS}"
SCRATCH="$(cd "$(dirname "$0")" && pwd)/fixtures"
mkdir -p "$SCRATCH"

check() {
  if [ "$1" = "0" ]; then
    echo "OK: $2"
  else
    echo "FALHA: $2"
    FAILS=$((FAILS + 1))
  fi
}

# 1. Criar aba de teste
TAB_JSON=$(herdr tab create --label "$LABEL" --cwd /home/worker 2>/dev/null)
check "$?" "herdr tab create executou"
TAB_ID=$(printf '%s' "$TAB_JSON" | PROMPT_JSON="$TAB_JSON" python3 /home/worker/harness-s2/scripts/_espelho_parse.py create 2>/dev/null | cut -d'|' -f1)
[ -n "$TAB_ID" ] || { echo "FALHA: tab_id nao obtido"; echo "RESUMO: 1 falhas"; exit 1; }
echo "OK: tab criada ($TAB_ID)"

# 2. Descobrir pane_id
WS_ID=$(printf '%s' "$TAB_JSON" | PROMPT_JSON="$TAB_JSON" python3 /home/worker/harness-s2/scripts/_espelho_parse.py create 2>/dev/null | cut -d'|' -f2)
PANE_JSON=$(herdr pane list --workspace "$WS_ID" 2>/dev/null)
PANE_ID=$(PANE_JSON="$PANE_JSON" TAB_ID="$TAB_ID" python3 /home/worker/harness-s2/scripts/_espelho_parse.py pane 2>/dev/null)
check "$([ -n "$PANE_ID" ] && echo 0 || echo 1)" "pane_id descoberto ($PANE_ID)"

# 3. Enviar texto e aguardar marcador
herdr pane send-text "$PANE_ID" 'echo ESPELHO-EXIT-0' >/dev/null 2>&1
herdr pane send-keys "$PANE_ID" Return >/dev/null 2>&1
check "$?" "send-text/send-keys executou"

if herdr pane wait-output "$PANE_ID" --regex 'ESPELHO-EXIT-[0-9]+' --timeout 30000 >/dev/null 2>&1; then
  check 0 "wait-output verde (ESPELHO-EXIT-)"
else
  check 1 "wait-output verde (ESPELHO-EXIT-)"
fi

# 4. Ler saida e extrair codigo
READ_OUT=$(herdr pane read "$PANE_ID" 2>/dev/null || true)
EXIT_CODE=$(printf '%s' "$READ_OUT" | grep -o 'ESPELHO-EXIT-[0-9]*' | tail -1 | cut -d- -f3)
check "$([ "$EXIT_CODE" = "0" ] && echo 0 || echo 1)" "codigo de saida 0 observado (obtido: ${EXIT_CODE:-?})"

# 5. Fechar a aba
herdr tab close "$TAB_ID" >/dev/null 2>&1
check "$?" "aba fechada"

# 6. Provar JSON ok:true via espelho.sh com prompt trivial
PROMPT_FILE="$SCRATCH/prompt-${TS}.txt"
printf 'echo pronto' > "$PROMPT_FILE"
OUT=$(bash /home/worker/harness-s2/scripts/espelho.sh "TESTE-ESPELHO-${TS}" "$PROMPT_FILE" 2>/dev/null || true)
check "$(printf '%s' "$OUT" | grep -q '"ok":true' && echo 0 || echo 1)" "espelho.sh produziu JSON ok:true"

if [ "$FAILS" = "0" ]; then
  echo "RESUMO: 0 falhas"
else
  echo "RESUMO: ${FAILS} falhas"
fi
exit "$([ "$FAILS" = "0" ] && echo 0 || echo 1)"
