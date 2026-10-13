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

# snapshot: trilha que já existia antes (a NOVA é a desta instância)
ANTIGAS=""
[ -d "$TRAIL_DIR" ] && ANTIGAS="$(ls -t "$TRAIL_DIR"/mecanico-trail-*.jsonl 2>/dev/null || true)"

if [ "$(id -u)" = "0" ]; then
  sudo -u worker env MEC_PROVA="${MEC_PROVA:-}" MEC_WT="${MEC_WT:-$REPO}" "$@" \
    bash "$MECANICO" "$REPO" "$MISSAO" > "$TRAIL_DIR/ultima-saida-mecanico.txt" 2>&1 &
else
  # prova hermética roda como worker — sem sudo, executa direto
  env MEC_PROVA="${MEC_PROVA:-}" MEC_WT="${MEC_WT:-$REPO}" "$@" \
    bash "$MECANICO" "$REPO" "$MISSAO" > "$TRAIL_DIR/ultima-saida-mecanico.txt" 2>&1 &
fi
MPID=$!

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
  OUT="$("$HERDR" tab create --label "RUN:MECANICO#m${MPID}" 2>/dev/null || true)"
  TAB="$(printf '%s' "$OUT" | python3 -c 'import sys,json
try: print(json.load(sys.stdin)["result"]["root_pane"]["pane_id"])
except Exception: print("")' 2>/dev/null)"
  if [ -n "$TAB" ]; then
    "$HERDR" pane run "$TAB" "tail -n 30 -F $TRAIL" >/dev/null 2>&1 || true
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
SAIDA="$(cat "$TRAIL_DIR/ultima-saida-mecanico.txt" 2>/dev/null || true)"
VERDICT="$(printf '%s' "$SAIDA" | grep -m1 '"ok"' || true)"
case "$VERDICT" in *'"ok":true'*) ST=pass ;; *'"ok":false'*) ST=fail ;; *) ST="rc=$RC" ;; esac
printf '{"id": "MECANICO-%s", "status": "%s", "finished_at": "%s", "tab_id": "%s", "trail": "%s"}\n' \
  "$MPID" "$ST" "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$TAB" "$TRAIL" > "$ESP"
printf '%s\n' "$VERDICT"
exit "$RC"
