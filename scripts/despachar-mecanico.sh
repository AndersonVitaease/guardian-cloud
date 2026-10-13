#!/usr/bin/env bash
# despachar-mecanico.sh — rota de despacho do agente MECÂNICO com espelho no herdr.
# ESPELHO-MECANICO-01: o mecânico não pode mais rodar "cego" — o despacho cria
# aba RUN:MECANICO#m<pid> no herdr com tail -F da trilha da instância e grava
# espelho na sala (ESPELHO_SALA_DIR, default /tmp/ag-live).
# Uso (supervisor): despachar-mecanico.sh REPO "MISSAO" [ENV_MEC=valor ...]
# Sobrescrevíveis para prova hermética: HERDR_BIN, MECANICO_BIN, ESPELHO_SALA_DIR.
set -u
REPO="${1:?uso: despachar-mecanico.sh REPO MISSAO [VAR=valor ...]}"
MISSAO="${2:?falta MISSAO}"
shift 2 || true
HERDR="${HERDR_BIN:-herdr}"
MECANICO="${MECANICO_BIN:-/home/worker/harness-s2/scripts/mecanico.sh}"
SALA="${ESPELHO_SALA_DIR:-/tmp/ag-live}"
TRAIL_DIR="$REPO/runs/mecanico"
mkdir -p "$TRAIL_DIR" "$SALA"
# o worker precisa escrever a trilha/relatório — nunca deixar runs/mecanico root-owned
chown -R worker:worker "$TRAIL_DIR" 2>/dev/null || true

aviso(){ [ "$ROOT" = "1" ] || return 0;
  local h; h=$(printf '%s' "$1" | md5sum | cut -c1-16)
  mkdir -p /tmp/aviso-dedup 2>/dev/null
  [ -e "/tmp/aviso-dedup/$h" ] && return 0
  : > "/tmp/aviso-dedup/$h"
  bash "$AVISO_BIN" "$1" >/dev/null 2>&1 &
}


# GB-MEC-GUARDIAN: registro no Guardian (spool/ledger/avisos) — sobrescrevíveis p/ prova
SPOOL_FILE="${SPOOL_FILE:-/opt/mission-events/spool.jsonl}"
LEDGER_DIR="${LEDGER_DIR:-/root/.hermes/mission-state}"
AVISO_BIN="${AVISO_BIN:-/opt/mission-events/scripts/aviso_chat.sh}"
ROOT=0; [ "$(id -u)" = "0" ] && ROOT=1
spool(){ [ "$ROOT" = "1" ] || return 0; printf '{"ts":"%s","source":"despachar-mecanico","kind":"%s","missionId":"%s","msg":"%s","data":{}}\n' \
  "$(date -u +%FT%TZ)" "$1" "MECANICO-$MPID" "$(printf '%s' "$2" | tr '"' "'" | cut -c1-160)" >> "$SPOOL_FILE" 2>/dev/null || true; }
led(){ [ "$ROOT" = "1" ] || return 0; printf '%s' "$1" > "$LEDGER_DIR/MECANICO-$MPID.json" 2>/dev/null || true; }
aviso(){ [ "$ROOT" = "1" ] || return 0;
  local h; h=$(printf '%s' "$1" | md5sum | cut -c1-16)
  mkdir -p /tmp/aviso-dedup 2>/dev/null
  [ -e "/tmp/aviso-dedup/$h" ] && return 0
  : > "/tmp/aviso-dedup/$h"
  bash "$AVISO_BIN" "$1" >/dev/null 2>&1 &
}


# snapshot: trilha que já existia antes (a NOVA é a desta instância)
ANTIGAS=""
[ -d "$TRAIL_DIR" ] && ANTIGAS="$(ls -t "$TRAIL_DIR"/mecanico-trail-*.jsonl 2>/dev/null || true)"

if [ "$(id -u)" = "0" ]; then
  sudo -u worker env MEC_PROVA="${MEC_PROVA:-}" MEC_WT="${MEC_WT:-$REPO}" "$@" \
    bash "$MECANICO" "$REPO" "$MISSAO" > "$TRAIL_DIR/ultima-saida-$$.txt" 2>&1 &
else
  # prova hermética roda como worker — sem sudo, executa direto
  env MEC_PROVA="${MEC_PROVA:-}" MEC_WT="${MEC_WT:-$REPO}" "$@" \
    bash "$MECANICO" "$REPO" "$MISSAO" > "$TRAIL_DIR/ultima-saida-$$.txt" 2>&1 &
fi
MPID=$!
spool mission_start "mecanico despachado: $MISSAO"
led "$(printf '{"missionId":"MECANICO-%s","status":"running","engine":"mecanico","createdAt":"%s","cwd":"%s","missao":"%s"}' "$MPID" "$(date -u +%FT%TZ)" "$REPO" "$(printf '%s' "$MISSAO" | tr '"' "'")")"

# espera a trilha NOVA nascer (a da instância atual)
TRAIL=""
for _ in $(seq 1 30); do
  for f in $(ls -t "$TRAIL_DIR"/mecanico-trail-*.jsonl 2>/dev/null); do
    case "$ANTIGAS" in *"$f"*) continue ;; esac
    TRAIL="$f"; break
  done
  [ -n "$TRAIL" ] && break
  sleep 0.5
done

TAB=""
if [ -n "$TRAIL" ]; then
  LABEL="$(printf '%s' "$MISSAO" | sed -n 's/^\([A-Za-z0-9-]\{1,40\}\):.*/\1/p')"
  [ -n "$LABEL" ] || LABEL="MECANICO"
  for _t in 1 2 3; do
    OUT="$("$HERDR" tab create --label "RUN:${LABEL}#m${MPID}" 2>/dev/null || true)"
    [ -n "$(printf '%s' "$OUT" | grep -o root_pane)" ] && break
    sleep 2
  done
  TAB="$(printf '%s' "$OUT" | python3 -c 'import sys,json
try: print(json.load(sys.stdin)["result"]["root_pane"]["pane_id"])
except Exception: print("")' 2>/dev/null)"
  if [ -n "$TAB" ]; then
    "$HERDR" pane run "$TAB" "tail -n 30 -F $TRAIL" >/dev/null 2>&1 || true
    aviso "🛰️ NASCEU: missão MECANICO-$MPID ($MISSAO) — aba RUN:${LABEL} no herdr (pane $TAB)"
  else
    # fail-open honesto: cura curta — matar a cura por falta de espelho é pior.
    printf '{"event":"ESPELHO_INDISPONIVEL","detalhe":"tab create falhou — cura segue sem espelho"}\n'
  fi
else
  printf '{"event":"TRILHA_AUSENTE","detalhe":"trilha da instância não nasceu em 15s"}\n'
fi

ESP="$SALA/MECANICO-$MPID.espelho.json"
printf '{"id": "MECANICO-%s", "status": "running", "started_at": "%s", "tab_id": "%s", "trail": "%s"}\n' \
  "$MPID" "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$TAB" "$TRAIL" > "$ESP"

wait "$MPID"; RC=$?
SAIDA="$(cat "$TRAIL_DIR/ultima-saida-$$.txt" 2>/dev/null || true)"
VERDICT="$(printf '%s' "$SAIDA" | grep -m1 '"ok"' || true)"
case "$VERDICT" in *'"ok":true'*) ST=pass ;; *'"ok":false'*) ST=fail ;; *) ST="rc=$RC" ;; esac
printf '{"id": "MECANICO-%s", "status": "%s", "finished_at": "%s", "tab_id": "%s", "trail": "%s"}\n' \
  "$MPID" "$ST" "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$TAB" "$TRAIL" > "$ESP"
ST2="$ST"; [ "$ST2" = "pass" ] && VER="PASS" || VER="FAIL"
spool mission_end "veredito $VER: $MISSAO"
led "$(printf '{"missionId":"MECANICO-%s","status":"closed","engine":"mecanico","veredito":"%s","custo_usd":0.0,"closedAt":"%s","trail":"%s"}' "$MPID" "$VER" "$(date -u +%FT%TZ)" "$TRAIL")"
aviso "🏁 MECANICO-$MPID ($MISSAO): $VER — aba ${TAB:-sem-aba}, trilha ${TRAIL:-nenhuma}"
printf '%s\n' "$VERDICT"
exit "$RC"
