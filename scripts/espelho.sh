#!/usr/bin/env bash
# espelho.sh — despacho de agente nosso com espelho ao vivo no herdr.
# ESPELHO-02: falso-match curado (marcador aleatorio por run, invisivel no eco),
# notify com token de /home/worker/guardian-app/.env (ou falha tipada),
# streamer filtrado com cores (subcomando --filtro-stream).
# ESPELHO-02B: eco/falha do agente NAO vira veredito ok:true — veredito FAIL ou
# marcador ausente sai como recusa tipada (ok:false + motivo); notify tipado
# aparece em TODO JSON final (inclusive die: NOTIFY_SEM_TOKEN sem POST) e o
# fluxo segue; env-file e binario do agente sobrescreviveis (ESPELHO_ENV_FILE,
# ESPELHO_HERMES_BIN) para prova hermetica.
# Uso: espelho.sh <ID> <arquivo-prompt> [--profile despachante]
#      espelho.sh --filtro-stream                (stdin -> stdout filtrado/colore)
#      espelho.sh --token-de <env-file>          (imprime token ou nada; nunca logar)
#      espelho.sh --notificar <ID> <veredito> <ms> <env-file>
set -euo pipefail

# Env-file do Guardian e binario do agente: sobrescreviveis para prova hermetica.
ENV_FILE_DEFAULT="${ESPELHO_ENV_FILE:-/home/worker/guardian-app/.env}"
HERMES_BIN="${ESPELHO_HERMES_BIN:-/home/worker/bin/hermes}"
CUSTO_BIN="${ESPELHO_CUSTO_BIN:-/home/worker/harness-s2/scripts/custo_sessoes.sh}"
CHAT_TIMEOUT="${ESPELHO_CHAT_TIMEOUT:-3600}"

die() {
  local code="$1"; shift
  # ESPELHO-02B: JSON de erro tambem traz notify tipado (nunca POSTA no die:
  # sem veredito nao ha o que notificar; sem token a falha fica explicita).
  local notify_die
  if [ -z "$(espelho__token_de "$ENV_FILE_DEFAULT")" ]; then
    notify_die="NOTIFY_SEM_TOKEN"
  else
    notify_die="NOTIFY_NAO_APLICADO"
  fi
  printf '{"ok":false,"error":"%s","detail":"%s","notify":"%s"}\n' "$code" "$*" "$notify_die"
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

# ==== custo real (MOPS-CUSTO-REAL-01) ====
# No pouso, descobre o session_id da sessao despachada (o hermes chat -q imprime
# "Session: <id>" no fim do log do pane), consulta o custo EXATO no state.db via
# custo_sessoes.sh e grava no .espelho.json (campo custo_usd + session_id).
# Regeneracao com retry: o uso da sessao pode pousar no db poucos segundos
# depois do marcador de EXIT. Imprime o custo (numero) ou vazio se indisponivel.
espelho__custo_registrar() {
  local id="$1" log_file="$2" json_file="$3" sess="" out="" custo="" i
  sess=$(grep -oE 'Session: [0-9]{8}_[0-9]{6}[_:][A-Za-z0-9]+' "$log_file" 2>/dev/null | tail -1 | cut -d' ' -f2 || true)
  [ -n "$sess" ] || { espelho__json_custo "$json_file" "" ""; printf ''; return 0; }
  for i in 1 2 3 4 5 6; do
    out=$("$CUSTO_BIN" --sessao "$sess" 2>/dev/null || true)
    if printf '%s' "$out" | grep -q '"ok":true'; then break; fi
    out=""
    [ "$i" = 6 ] || sleep 2
  done
  if [ -n "$out" ]; then
    custo=$(CUSTO_JSON="$out" python3 - <<'PYEOF'
import json, os
try:
    print(json.loads(os.environ["CUSTO_JSON"]).get("custo_usd", ""))
except Exception:
    pass
PYEOF
)
  fi
  espelho__json_custo "$json_file" "$sess" "$custo"
  printf '%s' "$custo"
}

# Grava session_id e custo_usd (null se indisponivel) no .espelho.json.
espelho__json_custo() {
  ESP_JSON_FILE="$1" ESP_SESSAO="$2" ESP_CUSTO="$3" python3 - <<'PYEOF'
import json, os
path = os.environ["ESP_JSON_FILE"]
try:
    with open(path) as fh:
        data = json.load(fh)
except Exception:
    data = {}
data["session_id"] = os.environ["ESP_SESSAO"] or None
custo = os.environ["ESP_CUSTO"]
data["custo_usd"] = float(custo) if custo else None
try:
    with open(path, "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
        fh.write("\n")
except Exception:
    pass
PYEOF
}

# ==== notify (ESPELHO-02) ====
# Sem token -> falha tipada NOTIFY_SEM_TOKEN e NAO tenta POST.
# Com token -> POST com header X-Notify-Token (formato do Guardian).
# Imprime apenas o status (nunca o token).
espelho__notificar() {
  local id="$1" veredito="$2" ms="$3" env_file="$4" custo_usd="${5:-}"
  local token status http_code payload
  # MOPS-CUSTO-REAL-01: custoUsd real (quando descoberto no pouso); senao null.
  local custo_json="null"
  case "$custo_usd" in
    ''|*[!0-9.]*) custo_json="null" ;;
    *) custo_json="$custo_usd" ;;
  esac
  token=$(espelho__token_de "$env_file")
  if [ -z "$token" ]; then
    printf 'NOTIFY_SEM_TOKEN'
    return 0
  fi
  # GB-NOTIFY-NOME-01: titulo legivel = o proprio ID da missao
  payload=$(printf '{"missionId":"%s","veredito":"%s","custoUsd":%s,"ms":%s,"link":"herdr:MISSAO:%s","titulo":"%s"}' \
    "$id" "$veredito" "$custo_json" "$ms" "$id" "$id")
  http_code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:${GUARDIAN_PORT:-8140}/api/notify" \
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
  # GB-STREAM-PTBR-01: filtro do streamer com labels traduzidas para PT-BR.
  # Uso nos panes de MISSAO:  tail -f sessao.log | espelho.sh --filtro-ptbr
  --filtro-ptbr) espelho__filtro | python3 "$(dirname "$0")/_espelho_parse.py" ptbr; exit 0 ;;
  --token-de) espelho__token_de "${2:-}"; echo; exit 0 ;;
  --notificar) espelho__notificar "${2:-}" "${3:-}" "${4:-0}" "${5:-}" "${6:-}"; echo; exit 0 ;;
  # MOPS-CUSTO-REAL-01: registra custo real de um pouso (prova/teste e reuso).
  # Uso: espelho.sh --registrar-custo <ID> <arquivo-log-do-pane> <arquivo-espelho-json>
  # Extrai "Session: <id>" do log, consulta custo_sessoes.sh e grava no json.
  --registrar-custo) espelho__custo_registrar "${2:-}" "${3:-}" "${4:-}"; echo; exit 0 ;;
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
  CMD="env HOME=/home/worker timeout ${CHAT_TIMEOUT} ${HERMES_BIN} chat -q --profile ${PROFILE} \"${PROMPT_TEXT}\" </dev/null; echo \"ESPELHO\"\"-EXIT-${RAND}-\$?\""
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
# ESPELHO-02B: eco/falha NAO vira veredito ok:true. Sem marcador ou com exit
# != 0 do agente, o JSON final sai como recusa tipada (ok:false + motivo).
READ_OUT=$(herdr pane read "$PANE_ID" 2>/dev/null || true)
MATCH=$(printf '%s' "$READ_OUT" | grep -o "ESPELHO-EXIT-${RAND}-[0-9]*" | tail -1 || true)
EXIT_CODE="${MATCH##*-}"
MOTIVO=""
if [ -z "$MATCH" ]; then
  EXIT_CODE=""
  VEREDITO="FAIL"
  MOTIVO="ESP_SEM_MARKER"
elif [ "$EXIT_CODE" = "0" ]; then
  VEREDITO="PASS"
else
  VEREDITO="FAIL"
  MOTIVO="AGENT_FAIL"
fi
OK_FLAG="false"
if [ "$VEREDITO" = "PASS" ]; then OK_FLAG="true"; fi

herdr tab close "$TAB_ID" >/dev/null 2>&1 || true

# MOPS-CUSTO-REAL-01: guardar o log do pane e registrar o custo real da sessao
# (o hermes chat -q imprime "Session: <id>" no fim; custo exato vem do state.db).
printf '%s\n' "$READ_OUT" > "${STATE_FILE}.log"
CUSTO_SESSAO="$(espelho__custo_registrar "$ID" "${STATE_FILE}.log" "$STATE_FILE" || true)"

# Notificar Guardian (nao quebra o fluxo se falhar)
MS=$(($(date +%s%3N) - START_MS))
NOTIFY_STATUS=$(espelho__notificar "$ID" "$VEREDITO" "$MS" "$ENV_FILE_DEFAULT" "$CUSTO_SESSAO")

# 6. Saida JSON (1 linha) — notify tipado SEMPRE presente
printf '{"ok":%s,"id":"%s","tab_id":"%s","pane_id":"%s","veredito":"%s","motivo":"%s","session_id":"%s","custo_usd":%s,"ms":%s,"notify":"%s"}\n' \
  "$OK_FLAG" "$ID" "$TAB_ID" "$PANE_ID" "$VEREDITO" "$MOTIVO" "$CUSTO_SESSAO" \
  "$(case "$CUSTO_SESSAO" in ''|*[!0-9.]*) printf null ;; *) printf '%s' "$CUSTO_SESSAO" ;; esac)" \
  "$MS" "$NOTIFY_STATUS"

# Atualiza espelho final
printf '{"id":"%s","tab_id":"%s","pane_id":"%s","status":"done","veredito":"%s","motivo":"%s","session_id":"%s","custo_usd":%s,"ms":%s,"notify":"%s"}\n' \
  "$ID" "$TAB_ID" "$PANE_ID" "$VEREDITO" "$MOTIVO" "$CUSTO_SESSAO" \
  "$(case "$CUSTO_SESSAO" in ''|*[!0-9.]*) printf null ;; *) printf '%s' "$CUSTO_SESSAO" ;; esac)" \
  "$MS" "$NOTIFY_STATUS" > "$STATE_FILE"

# GB-POUSO-EXPIRA-01: aviso de missão pousada MORRE com a missão — o próprio
# espelho rename o json para <ID>.espelho.pousado.json no pouso, assim o
# varrimento de "running" fica limpo por construção (endpoints tratam ambos os
# nomes; a ponte da office vê o pousado e injeta o session_end).
mv -f "$STATE_FILE" "${STATE_FILE%.espelho.json}.espelho.pousado.json"
