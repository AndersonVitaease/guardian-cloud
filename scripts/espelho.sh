#!/usr/bin/env bash
# espelho.sh — despacho de agente nosso com espelho ao vivo no herdr.
# Uso: espelho.sh <ID> <arquivo-prompt> [--profile despachante]
set -euo pipefail

die() {
  local code="$1"; shift
  printf '{"ok":false,"error":"%s","detail":"%s"}\n' "$code" "$*"
  exit 1
}

ID="${1:-}"; PROMPT_FILE="${2:-}"; shift 2 2>/dev/null || true
PROFILE="despachante"
while [ $# -gt 0 ]; do
  case "$1" in
    --profile) PROFILE="${2:-}"; shift 2 ;;
    *) shift ;;
  esac
done

[ -n "$ID" ] || die "TAB_CREATE_FAILED" "ID ausente"
[ -n "$PROMPT_FILE" ] || die "TAB_CREATE_FAILED" "arquivo-prompt ausente"
[ -f "$PROMPT_FILE" ] || die "TAB_CREATE_FAILED" "arquivo-prompt nao encontrado: $PROMPT_FILE"
[ -n "$PROFILE" ] || die "TAB_CREATE_FAILED" "perfil ausente"

START_MS=$(date +%s%3N)

# 1. Criar aba no herdr
TAB_JSON=$(herdr tab create --label "MISSAO:${ID}" --cwd /home/worker 2>/dev/null) \
  || die "TAB_CREATE_FAILED" "herdr tab create falhou para ${ID}"
PARSED=$(PROMPT_JSON="$TAB_JSON" python3 /home/worker/harness-s2/scripts/_espelho_parse.py create 2>/dev/null) \
  || die "TAB_CREATE_FAILED" "JSON da aba invalido"
TAB_ID="${PARSED%%|*}"; WS_ID="${PARSED##*|}"
[ -n "$TAB_ID" ] && [ -n "$WS_ID" ] || die "TAB_CREATE_FAILED" "nao foi possivel extrair tab/workspace"

# 2. Descobrir pane_id da aba nova
PANE_JSON=$(herdr pane list --workspace "$WS_ID" 2>/dev/null) \
  || { herdr tab close "$TAB_ID" >/dev/null 2>&1 || true; die "TAB_CREATE_FAILED" "herdr pane list falhou"; }
PANE_ID=$(PANE_JSON="$PANE_JSON" TAB_ID="$TAB_ID" python3 /home/worker/harness-s2/scripts/_espelho_parse.py pane 2>/dev/null) \
  || { herdr tab close "$TAB_ID" >/dev/null 2>&1 || true; die "TAB_CREATE_FAILED" "pane_id nao encontrado"; }
[ -n "$PANE_ID" ] || { herdr tab close "$TAB_ID" >/dev/null 2>&1 || true; die "TAB_CREATE_FAILED" "pane_id vazio"; }

# 3. Montar comando do espelho (roda como worker; sudo apenas se root)
PROMPT_TEXT=$(cat "$PROMPT_FILE")
if [ "$(id -u)" = "0" ]; then
  CMD="sudo -u worker env HOME=/home/worker /home/worker/bin/hermes chat -q --profile ${PROFILE} \"${PROMPT_TEXT}\"; echo ESPELHO-EXIT-\$?"
else
  CMD="env HOME=/home/worker /home/worker/bin/hermes chat -q --profile ${PROFILE} \"${PROMPT_TEXT}\"; echo ESPELHO-EXIT-\$?"
fi

# 4. Injetar no pane e registrar espelho ao vivo
herdr pane send-text "$PANE_ID" "$CMD" >/dev/null 2>&1 || die "SEND_TEXT_FAILED" "falha ao enviar texto"
herdr pane send-keys "$PANE_ID" Return >/dev/null 2>&1 || true

STATE_FILE="$(cd "$(dirname "$PROMPT_FILE")" && pwd)/${ID}.espelho.json"
printf '{"id":"%s","tab_id":"%s","pane_id":"%s","workspace_id":"%s","status":"running","started_at":"%s"}\n' \
  "$ID" "$TAB_ID" "$PANE_ID" "$WS_ID" "$(date +%Y-%m-%dT%H:%M:%S%z)" > "$STATE_FILE"

# Liveness honesta: espera o marcador de fim (timeout 2h)
# Regex exige digito para nao casar com o proprio comando ecoado (ESPELHO-EXIT-$?)
if ! herdr pane wait-output "$PANE_ID" --regex 'ESPELHO-EXIT-[0-9]+' --timeout 7200000 >/dev/null 2>&1; then
  herdr tab close "$TAB_ID" >/dev/null 2>&1 || true
  die "WAIT_TIMEOUT" "ESPELHO-EXIT- nao apareceu em 7200000 ms"
fi

# 5. Extrair codigo de saida do pane
READ_OUT=$(herdr pane read "$PANE_ID" 2>/dev/null || true)
EXIT_CODE=$(printf '%s' "$READ_OUT" | grep -o 'ESPELHO-EXIT-[0-9]*' | tail -1 | cut -d- -f3)
[ -n "$EXIT_CODE" ] || EXIT_CODE=1
if [ "$EXIT_CODE" = "0" ]; then VEREDITO="PASS"; else VEREDITO="FAIL"; fi

herdr tab close "$TAB_ID" >/dev/null 2>&1 || true

# Notificar Guardian (nao quebra o fluxo se falhar)
NOTIFY_STATUS="skipped"
ENV_FILE="/home/worker/guardian-app/.env"
if [ -f "$ENV_FILE" ]; then
  TOKEN=$(grep -E '^NOTIFY_TOKEN=' "$ENV_FILE" | cut -d= -f2- || true)
else
  TOKEN=""
fi
MS=$(($(date +%s%3N) - START_MS))
PAYLOAD=$(printf '{"missionId":"%s","veredito":"%s","custoUsd":null,"ms":%s,"link":"herdr:MISSAO:%s"}' \
  "$ID" "$VEREDITO" "$MS" "$ID")
if [ -n "${TOKEN:-}" ]; then
  HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8140/api/notify \
    -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" -d "$PAYLOAD" || true)
else
  HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8140/api/notify \
    -H "Content-Type: application/json" -d "$PAYLOAD" || true)
fi
case "$HTTP_CODE" in
  200|201|202) NOTIFY_STATUS="sent" ;;
  401) NOTIFY_STATUS="NOTIFY_401" ;;
  *) NOTIFY_STATUS="NOTIFY_${HTTP_CODE:-ERROR}" ;;
esac
# NOTIFY_* nao quebra o fluxo: apenas refletido no JSON final.

# 6. Saida JSON (1 linha)
printf '{"ok":true,"id":"%s","tab_id":"%s","pane_id":"%s","veredito":"%s","ms":%s,"notify":"%s"}\n' \
  "$ID" "$TAB_ID" "$PANE_ID" "$VEREDITO" "$MS" "$NOTIFY_STATUS"

# Atualiza espelho final
printf '{"id":"%s","tab_id":"%s","pane_id":"%s","status":"done","veredito":"%s","ms":%s,"notify":"%s"}\n' \
  "$ID" "$TAB_ID" "$PANE_ID" "$VEREDITO" "$MS" "$NOTIFY_STATUS" > "$STATE_FILE"
