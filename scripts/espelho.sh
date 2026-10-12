#!/usr/bin/env bash
# espelho.sh — despacho de agente nosso com espelho ao vivo no herdr.
# ESPELHO-02: falso-match curado (marcador aleatorio por run, invisivel no eco),
# notify com token de /home/worker/guardian-app/.env (ou falha tipada),
# streamer filtrado com cores (subcomando --filtro-stream).
# Uso: espelho.sh <ID> <arquivo-prompt> [--profile despachante]
#      espelho.sh --filtro-stream                (stdin -> stdout filtrado/colore)
#      espelho.sh --token-de <env-file>          (imprime token ou nada; nunca logar)
#      espelho.sh --notificar <ID> <veredito> <ms> <env-file>
set -euo pipefail

die() {
  local code="$1"; shift
  printf '{"ok":false,"error":"%s","detail":"%s"}\n' "$code" "$*"
  exit 1
}

# ==== streamer filtrado (ESPELHO-02, pedido do operator) ====
# Destaca APENAS: fala/decisao do agente (blocos Hermes), patches escritos,
# provas OK/FAIL e veredito. Oculta lixo repetido de terminal
# ("preparing terminal", "$ true 0.0s"). Cores: verde=prova OK/RESUMO 0 falhas/
# veredito PASS; vermelho=FAIL/erro/RESUMO com falhas; amarelo=patch/commit.
espelho__filtro() {
  awk '
    {
      # lixo de terminal: descarta
      if ($0 ~ /preparing terminal/) next
      if ($0 ~ /\$ true .*0\.0s/) next

      # veredito: PASS verde / FAIL vermelho (prioridade maxima)
      if ($0 ~ /VEREDITO PASS/) { printf "\033[32m%s\033[0m\n", $0; fflush(); next }
      if ($0 ~ /VEREDITO FAIL/) { printf "\033[31m%s\033[0m\n", $0; fflush(); next }
      # amarelo: patch escrito / commit
      if ($0 ~ /\| (Write|Edit|Patch) \||patch|git (add|commit)|\.diff/) {
        printf "\033[33m%s\033[0m\n", $0; fflush(); next
      }
      # verde: prova OK / RESUMO 0 falhas
      if ($0 ~ /RESUMO: 0 falhas/ || $0 ~ /OK: / || $0 ~ /prova.*[Oo][Kk]/ || $0 ~ /[Oo][Kk].*prova/) {
        printf "\033[32m%s\033[0m\n", $0; fflush(); next
      }
      # vermelho: erro / RESUMO com falhas
      if ($0 ~ /RESUMO: [1-9][0-9]* falha/ || $0 ~ /FAIL|FALHA|ERRO/) {
        printf "\033[31m%s\033[0m\n", $0; fflush(); next
      }
      # fala/decisao do agente (blocos Hermes) e marco de inicio
      if ($0 ~ /Hermes[>:]/ || $0 ~ /^\[.{1,20}BRT\] IN/) {
        printf "%s\n", $0; fflush(); next
      }
      # todo o resto: descarta
    }
  '
}

# ==== token de servico (ESPELHO-02) ====
# Le token de /home/worker/guardian-app/.env (GUARDIAN_NOTIFY_TOKEN ou ADMIN_TOKEN).
# NUNCA imprime o valor em log: quem chama decide o que fazer com stdout.
espelho__token_de() {
  local env_file="${1:-}"
  [ -f "$env_file" ] || { printf ''; return 0; }
  local tok=""
  tok=$(grep -E '^(GUARDIAN_NOTIFY_TOKEN|ADMIN_TOKEN)=' "$env_file" | head -1 | cut -d= -f2- | tr -d '"'\''' || true)
  printf '%s' "$tok"
}

# ==== notify (ESPELHO-02) ====
# Sem token -> falha tipada NOTIFY_SEM_TOKEN e NAO tenta POST.
# Com token -> POST com header X-Notify-Token (formato do Guardian).
# Imprime apenas o status (nunca o token).
espelho__notificar() {
  local id="$1" veredito="$2" ms="$3" env_file="$4"
  local token status http_code payload
  token=$(espelho__token_de "$env_file")
  if [ -z "$token" ]; then
    printf 'NOTIFY_SEM_TOKEN'
    return 0
  fi
  # GB-NOTIFY-NOME-01: titulo legivel = o proprio ID da missao
  payload=$(printf '{"missionId":"%s","veredito":"%s","custoUsd":null,"ms":%s,"link":"herdr:MISSAO:%s","titulo":"%s"}' \
    "$id" "$veredito" "$ms" "$id" "$id")
  http_code=$(curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8140/api/notify \
    -H 'Content-Type: application/json' -H "X-Notify-Token: $token" -d "$payload" || true)
  case "$http_code" in
    200|201|202) status="sent" ;;
    401) status="NOTIFY_401" ;;
    '') status="NOTIFY_ERROR" ;;
    *) status="NOTIFY_${http_code}" ;;
  esac
  printf '%s' "$status"
}

# ==== subcomandos ====
case "${1:-}" in
  --filtro-stream) espelho__filtro; exit 0 ;;
  --token-de) espelho__token_de "${2:-}"; echo; exit 0 ;;
  --notificar) espelho__notificar "${2:-}" "${3:-}" "${4:-0}" "${5:-}"; echo; exit 0 ;;
esac

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
# ESPELHO-02 (cura do falso-match): marcador aleatorio POR RUN e invisivel no eco.
# O comando injetado escreve echo "ESPELHO""-EXIT-<rand>-$?" — a string com aspas
# duplas vazias NAO casa a regex do marcador (o eco do comando nunca vira veredito);
# na execucao o shell concatena e imprime ESPELHO-EXIT-<rand>-<codigo>.
RAND="$(date +%s%3N)${RANDOM}"
PROMPT_TEXT=$(cat "$PROMPT_FILE")
if [ "$(id -u)" = "0" ]; then
  CMD="sudo -u worker env HOME=/home/worker /home/worker/bin/hermes chat -q --profile ${PROFILE} \"${PROMPT_TEXT}\"; echo \"ESPELHO\"\"-EXIT-${RAND}-\$?\""
else
  CMD="env HOME=/home/worker /home/worker/bin/hermes chat -q --profile ${PROFILE} \"${PROMPT_TEXT}\"; echo \"ESPELHO\"\"-EXIT-${RAND}-\$?\""
fi

# 4. Injetar no pane e registrar espelho ao vivo
herdr pane send-text "$PANE_ID" "$CMD" >/dev/null 2>&1 || die "SEND_TEXT_FAILED" "falha ao enviar texto"
herdr pane send-keys "$PANE_ID" Return >/dev/null 2>&1 || true

STATE_FILE="$(cd "$(dirname "$PROMPT_FILE")" && pwd)/${ID}.espelho.json"
printf '{"id":"%s","tab_id":"%s","pane_id":"%s","workspace_id":"%s","status":"running","started_at":"%s"}\n' \
  "$ID" "$TAB_ID" "$PANE_ID" "$WS_ID" "$(date +%Y-%m-%dT%H:%M:%S%z)" > "$STATE_FILE"

# Liveness honesta: espera o marcador aleatorio DESTA run (timeout 2h).
# O eco do comando nao casa (tem aspas entre ESPELHO e -EXIT-), e o valor
# aleatorio isola runs concurrentes/antigas do mesmo pane.
MARKER_RE="ESPELHO-EXIT-${RAND}-[0-9]+"
if ! herdr pane wait-output "$PANE_ID" --regex "$MARKER_RE" --timeout 7200000 >/dev/null 2>&1; then
  herdr tab close "$TAB_ID" >/dev/null 2>&1 || true
  die "WAIT_TIMEOUT" "marcador da run nao apareceu em 7200000 ms"
fi

# 5. Extrair codigo de saida do pane (somente marcador desta run)
READ_OUT=$(herdr pane read "$PANE_ID" 2>/dev/null || true)
MATCH=$(printf '%s' "$READ_OUT" | grep -o "ESPELHO-EXIT-${RAND}-[0-9]*" | tail -1 || true)
EXIT_CODE="${MATCH##*-}"
[ -n "$EXIT_CODE" ] || EXIT_CODE=1
if [ "$EXIT_CODE" = "0" ]; then VEREDITO="PASS"; else VEREDITO="FAIL"; fi

herdr tab close "$TAB_ID" >/dev/null 2>&1 || true

# Notificar Guardian (nao quebra o fluxo se falhar)
MS=$(($(date +%s%3N) - START_MS))
NOTIFY_STATUS=$(espelho__notificar "$ID" "$VEREDITO" "$MS" "/home/worker/guardian-app/.env")

# 6. Saida JSON (1 linha)
printf '{"ok":true,"id":"%s","tab_id":"%s","pane_id":"%s","veredito":"%s","ms":%s,"notify":"%s"}\n' \
  "$ID" "$TAB_ID" "$PANE_ID" "$VEREDITO" "$MS" "$NOTIFY_STATUS"

# Atualiza espelho final
printf '{"id":"%s","tab_id":"%s","pane_id":"%s","status":"done","veredito":"%s","ms":%s,"notify":"%s"}\n' \
  "$ID" "$TAB_ID" "$PANE_ID" "$VEREDITO" "$MS" "$NOTIFY_STATUS" > "$STATE_FILE"
