#!/usr/bin/env bash
# test_espelho.sh — teste hermetico do espelho.sh (ESPELHO-02) no herdr real.
# Cubre: filtro de stream (cores + supressao de lixo), falso-match (eco do
# comando NAO vira veredito), token de notify (presente/ausente) e o fluxo
# completo do espelho.sh com prompt trivial.
set -uo pipefail

FAILS=0
TS=$(date +%Y%m%d%H%M%S)
LABEL="TESTE-ESPELHO-${TS}"
SCRATCH="$(cd "$(dirname "$0")" && pwd)/fixtures"
ESPELHO="/home/worker/harness-s2/scripts/espelho.sh"
mkdir -p "$SCRATCH"

check() {
  if [ "$1" = "0" ]; then
    echo "OK: $2"
  else
    echo "FALHA: $2"
    FAILS=$((FAILS + 1))
  fi
}

# ============ 1. Filtro de stream (hermetico, offline) ============
ENTRADA=$(printf '%s\n' \
  'preparing terminal session' \
  '$ true 0.0s' \
  '[12/10 04:45:01 BRT] INÍCIO seed=2294 modelo=x budget=$0.05' \
  'Hermes> vou aplicar o patch agora' \
  '[12/10 04:45:22 BRT] turno 5 | Write | 0ms | $0.00 | ok | /x/prova-xyz.py' \
  'OK: prova hermetica passou' \
  'RESUMO: 0 falhas' \
  '[12/10 04:45:03 BRT] turno 1 | Bash | 0ms | ERRO | cd x' \
  'VEREDITO FAIL | motivo=vagueio' \
  'RESUMO: 2 falhas' \
  '[12/10 04:45:27 BRT] turno 7 | Bash | 9ms | ok | git commit -m fix' \
  '[12/10 04:45:03 BRT] turno 1 | Bash | 11ms | $0.00 | ok | ls')
SAIDA=$(printf '%s\n' "$ENTRADA" | bash "$ESPELHO" --filtro-stream)

check "$(printf '%s\n' "$SAIDA" | grep -q 'preparing terminal' && echo 1 || echo 0)" "filtro oculta 'preparing terminal'"
check "$(printf '%s\n' "$SAIDA" | grep -q '\$ true 0.0s' && echo 1 || echo 0)" "filtro oculta '\$ true 0.0s'"
check "$(printf '%s\n' "$SAIDA" | grep -q 'ok | ls' && echo 1 || echo 0)" "filtro oculta linha irrelevante (ls)"
check "$(printf '%s\n' "$SAIDA" | grep -q 'Hermes> vou aplicar' && echo 0 || echo 1)" "filtro mantem fala do agente (Hermes)"
check "$(printf '%s\n' "$SAIDA" | grep -q 'Write | 0ms' && echo 0 || echo 1)" "filtro mantem patch escrito (Write)"
check "$(printf '%s\n' "$SAIDA" | grep -q 'git commit' && echo 0 || echo 1)" "filtro mantem commit"
check "$(printf '%s\n' "$SAIDA" | grep -q 'VEREDITO FAIL' && echo 0 || echo 1)" "filtro mantem veredito"
check "$(printf '%s\n' "$SAIDA" | grep -q 'INÍCIO seed=2294' && echo 0 || echo 1)" "filtro mantem marco de inicio"
check "$(printf '%s\n' "$SAIDA" | grep -qF $'\033[32mRESUMO: 0 falhas' && echo 0 || echo 1)" "RESUMO 0 falhas em VERDE (ANSI 32)"
check "$(printf '%s\n' "$SAIDA" | grep -qF $'\033[32mOK: prova' && echo 0 || echo 1)" "prova OK em VERDE (ANSI 32)"
check "$(printf '%s\n' "$SAIDA" | grep -qF $'\033[33m' <<< "$(printf '%s\n' "$SAIDA" | grep 'Write | 0ms')" && echo 0 || echo 1)" "patch em AMARELO (ANSI 33)"
check "$(printf '%s\n' "$SAIDA" | grep -qF $'\033[31mVEREDITO FAIL' && echo 0 || echo 1)" "veredito FAIL em VERMELHO (ANSI 31)"
check "$(printf '%s\n' "$SAIDA" | grep -qF $'\033[31m' <<< "$(printf '%s\n' "$SAIDA" | grep 'ERRO | cd x')" && echo 0 || echo 1)" "erro em VERMELHO (ANSI 31)"

# ============ 2. Falso-match: eco do comando NAO vira veredito ============
RAND="771002${TS}"
ECO_CMD="echo \"ESPELHO\"\"-EXIT-${RAND}-0\""
# O eco do comando (com aspas) NAO casa a regex do marcador da run:
check "$(printf '%s' "$ECO_CMD" | grep -Eo "ESPELHO-EXIT-${RAND}-[0-9]+" >/dev/null 2>&1 && echo 1 || echo 0)" \
  "regex do marcador NAO casa com o eco do comando (com aspas)"
# A saida em execucao (shell concatena as aspas vazias) casa:
check "$(printf '%s' "ESPELHO-EXIT-${RAND}-0" | grep -Eo "ESPELHO-EXIT-${RAND}-[0-9]+" >/dev/null 2>&1 && echo 0 || echo 1)" \
  "regex do marcador casa com a saida em execucao"

# Prova ao vivo no herdr: send-text SEM Return nao dispara wait-output;
# apos o Return, a saida real dispara.
TAB_JSON=$(herdr tab create --label "$LABEL" --cwd /home/worker 2>/dev/null) || TAB_JSON=""
if [ -n "$TAB_JSON" ]; then
  TAB_ID=$(PROMPT_JSON="$TAB_JSON" python3 /home/worker/harness-s2/scripts/_espelho_parse.py create 2>/dev/null | cut -d'|' -f1)
  WS_ID=$(PROMPT_JSON="$TAB_JSON" python3 /home/worker/harness-s2/scripts/_espelho_parse.py create 2>/dev/null | cut -d'|' -f2)
  PANE_JSON=$(herdr pane list --workspace "$WS_ID" 2>/dev/null)
  PANE_ID=$(PANE_JSON="$PANE_JSON" TAB_ID="$TAB_ID" python3 /home/worker/harness-s2/scripts/_espelho_parse.py pane 2>/dev/null)
  if [ -n "$PANE_ID" ]; then
    herdr pane send-text "$PANE_ID" "$ECO_CMD" >/dev/null 2>&1
    if herdr pane wait-output "$PANE_ID" --regex "ESPELHO-EXIT-${RAND}-[0-9]+" --timeout 4000 >/dev/null 2>&1; then
      check 1 "eco sem Return NAO dispara wait-output (falso veredito reproduzido!)"
    else
      check 0 "eco sem Return NAO dispara wait-output"
    fi
    herdr pane send-keys "$PANE_ID" Return >/dev/null 2>&1
    if herdr pane wait-output "$PANE_ID" --regex "ESPELHO-EXIT-${RAND}-[0-9]+" --timeout 30000 >/dev/null 2>&1; then
      check 0 "execucao real (apos Return) dispara wait-output"
    else
      check 1 "execucao real (apos Return) dispara wait-output"
    fi
  else
    check 1 "pane_id descoberto no herdr"
  fi
  herdr tab close "$TAB_ID" >/dev/null 2>&1
  check "$?" "aba de teste fechada"
else
  echo "PULO: herdr sem workspace ativo neste shell — prova ao vivo do falso-match roda na sessao mission-ops"
fi

# ============ 3. Notify com token (hermetico) ============
ENV_OK="$SCRATCH/env-ok-${TS}"
ENV_VAZIO="$SCRATCH/env-vazio-${TS}"
printf 'OUTRO=x\nGUARDIAN_NOTIFY_TOKEN=token-teste-%s\n' "$TS" > "$ENV_OK"
printf 'OUTRO=x\n' > "$ENV_VAZIO"
chmod 600 "$ENV_OK"

TOK=$(bash "$ESPELHO" --token-de "$ENV_OK")
check "$([ "$TOK" = "token-teste-${TS}" ] && echo 0 || echo 1)" "token extraido do .env corretamente"
TOK2=$(bash "$ESPELHO" --token-de "$ENV_VAZIO")
check "$([ -z "$TOK2" ] && echo 0 || echo 1)" "sem chave de token -> vazio"
TOK3=$(bash "$ESPELHO" --token-de "$SCRATCH/nao-existe-${TS}")
check "$([ -z "$TOK3" ] && echo 0 || echo 1)" ".env inexistente -> vazio"
ST=$(bash "$ESPELHO" --notificar "TESTE-${TS}" "PASS" "5" "$ENV_VAZIO")
check "$([ "$ST" = "NOTIFY_SEM_TOKEN" ] && echo 0 || echo 1)" "sem token -> falha tipada NOTIFY_SEM_TOKEN (sem POST)"
rm -f "$ENV_OK" "$ENV_VAZIO"

# ============ 4. Fluxo completo: JSON ok:true via espelho.sh ============
PROBE=$(herdr tab create --label "PROBE-${TS}" --cwd /home/worker 2>&1 || true)
if printf '%s' "$PROBE" | grep -q '"workspace_not_found"'; then
  echo "PULO: fluxo completo exige herdr com workspace ativo (sessao mission-ops)"
else
  PROBE_ID=$(PROMPT_JSON="$PROBE" python3 /home/worker/harness-s2/scripts/_espelho_parse.py create 2>/dev/null | cut -d'|' -f1)
  herdr tab close "$PROBE_ID" >/dev/null 2>&1 || true
  PROMPT_FILE="$SCRATCH/prompt-${TS}.txt"
  printf 'echo pronto' > "$PROMPT_FILE"
  OUT=$(bash "$ESPELHO" "TESTE-ESPELHO-${TS}" "$PROMPT_FILE" 2>/dev/null || true)
  check "$(printf '%s' "$OUT" | grep -q '"ok":true' && echo 0 || echo 1)" "espelho.sh produziu JSON ok:true"
  check "$(printf '%s' "$OUT" | grep -q '"notify":"NOTIFY_SEM_TOKEN"' && echo 0 || echo 1)" "sem .env de token, notify tipado no JSON final"
fi

if [ "$FAILS" = "0" ]; then
  echo "RESUMO: 0 falhas"
else
  echo "RESUMO: ${FAILS} falhas"
fi
exit "$([ "$FAILS" = "0" ] && echo 0 || echo 1)"
