#!/bin/bash
# MISSAO-FECHAR-TIMEOUT-01: prova hermetica do timeout por step no fecho.
# Cenario A: vigia_chat fake dorme 1200s >> FECHAR_STEP_TIMEOUT=5 → o fecho tem
#   que abortar com TIMEOUT_STEP, exit 2, em <5s (antes: pendurava para sempre).
# Cenario B: vigia_chat fake falha rapido (rc=7) → cobre resultado tipado FALHA
#   com 2 tentativas, fail-open (exit 0, ok:false) e steps_pulados vazio.
# Marcador de sucesso: FECHAR-TIMEOUT-OK; ultima linha: RESUMO: 0 falhas.
set -u
FECHAR="/home/worker/harness-s2/scripts/fechar_missao.sh"
FAILS=0
FIX="$(mktemp -d /tmp/prova-fechar-timeout-01.XXXXXX)"
trap 'rm -rf "$FIX"' EXIT

falha(){ echo "FALHA: $*"; FAILS=$((FAILS+1)); }

# ---------- fixtures fake (hermeticos, nenhum servico real) ----------
cat > "$FIX/ledger_fechar.sh" <<'EOF'
#!/bin/bash
printf '{"ok":true,"fechado":"%s","fake":"ledger"}\n' "$1"
exit 0
EOF
cat > "$FIX/mirror_fechar.sh" <<'EOF'
#!/bin/bash
printf '{"ok":true,"fake":"mirror"}\n'
exit 0
EOF
cat > "$FIX/tab_reap.sh" <<'EOF'
#!/bin/bash
printf '{"ok":true,"tool":"tab_reap","fake":true,"modo":"apply"}\n'
exit 0
EOF
cat > "$FIX/vigia_chat.sh" <<EOF
#!/bin/bash
sleep \${VIGIA_SLEEP:-1200}
: > "$FIX/marca-vigia-A"
printf '{"ok":false,"tool":"vigia_chat","fake":"vigia","delivered":false}\n'
exit \${VIGIA_RC:-0}
EOF
chmod +x "$FIX"/*.sh

# ================= CENARIO A: timeout por step =================
rm -f /tmp/fechar_missao-PROVA-FT-01.log /tmp/fechar_missao-PROVA-FT-01.steps.json
T0=$(date +%s)
SAIDA="$(FECHAR_FAKE="$FIX" FECHAR_STEP_TIMEOUT=3 FECHAR_KILL_WAIT=1 \
  bash "$FECHAR" PROVA-FT-01)"
RC=$?
T1=$(date +%s)
DUR=$((T1 - T0))
echo "--- cenario A (timeout) rc=$RC dur=${DUR}s ---"
echo "$SAIDA"

[ "$RC" = "2" ] || falha "cenario A exit esperado 2 (timeout_step), obtido $RC"
[ "$DUR" -lt 5 ] || falha "cenario A duracao ${DUR}s >= 5s (deve abortar rapido, nao pendurar)"
[ -f /tmp/fechar_missao-PROVA-FT-01.steps.json ] || falha "cenario A steps.json ausente"
if [ -f /tmp/fechar_missao-PROVA-FT-01.steps.json ]; then
  jq -e '
    .ok == false and
    .status == "timeout_step" and
    .timeout_step_s == 3 and
    .abortado_timeout == true and
    (.duracao_s < 5) and
    ([.steps[] | select(.step == "vigia_chat")][0].status == "TIMEOUT_STEP") and
    ([.steps[] | select(.step == "vigia_chat")][0].timeout_excedido == true) and
    ([.steps[] | select(.step == "ledger_fechar")][0].status == "OK") and
    ([.steps[] | select(.step == "mirror_fechar")][0].status == "OK") and
    ([.steps[] | select(.step == "tab_reap")][0].status == "OK") and
    (.steps_pulados | length == 0)
  ' /tmp/fechar_missao-PROVA-FT-01.steps.json >/dev/null \
    || falha "cenario A JSON tipado incorreto: $(cat /tmp/fechar_missao-PROVA-FT-01.steps.json)"
fi
if ps -eo args | grep -F "vigia_chat.sh PROVA-FT-01" | grep -v grep >/dev/null; then
  falha "cenario A deixou processo vigia fake vivo (loop morto residual)"
fi
if [ -f "$FIX/marca-vigia-A" ]; then
  falha "cenario A: fixture de vigia concluiu (nao deveria)"
fi

# ================= CENARIO B: falha rapida tipada, sem timeout =================
FIXB="$(mktemp -d /tmp/prova-fechar-timeout-01b.XXXXXX)"
cat > "$FIXB/vigia_chat.sh" <<'EOF'
#!/bin/bash
printf '{"ok":false,"tool":"vigia_chat","fake":"vigia"}\n'
exit 7
EOF
chmod +x "$FIXB"/*.sh
cp "$FIX/ledger_fechar.sh" "$FIX/mirror_fechar.sh" "$FIX/tab_reap.sh" "$FIXB/"
rm -f /tmp/fechar_missao-PROVA-FT-02.log /tmp/fechar_missao-PROVA-FT-02.steps.json
SB="$FIXB/marca-vigia-B"
# fixture B grava marca ao fim (prova que o step rodou as 2 tentativas e saiu)
cat > "$FIXB/vigia_chat.sh" <<EOF
#!/bin/bash
printf '{"ok":false,"tool":"vigia_chat","fake":"vigia"}\n'
: > "$SB"
exit 7
EOF
chmod +x "$FIXB/vigia_chat.sh"
T0B=$(date +%s)
SAIDA_B="$(FECHAR_FAKE="$FIXB" bash "$FECHAR" PROVA-FT-02)"
RCB=$?
T1B=$(date +%s)
DURB=$((T1B - T0B))
echo "--- cenario B (falha rapida) rc=$RCB dur=${DURB}s ---"
echo "$SAIDA_B"

[ "$RCB" = "0" ] || falha "cenario B exit esperado 0 (fail-open legado), obtido $RCB"
[ "$DURB" -lt 20 ] || falha "cenario B duracao ${DURB}s >= 20s"
[ -f /tmp/fechar_missao-PROVA-FT-02.steps.json ] || falha "cenario B steps.json ausente"
if [ -f /tmp/fechar_missao-PROVA-FT-02.steps.json ]; then
  jq -e '
    .ok == false and
    .status == "falha_parcial" and
    .abortado_timeout == false and
    ([.steps[] | select(.step == "vigia_chat")][0].status == "FALHA") and
    ([.steps[] | select(.step == "vigia_chat")][0].rc == 7) and
    ([.steps[] | select(.step == "vigia_chat")][0].tentativas == 2) and
    ([.steps[] | select(.step == "vigia_chat")][0].timeout_excedido == false) and
    ([.steps[] | select(.step == "ledger_fechar")][0].status == "OK") and
    (.steps_pulados | length == 0) and
    (.duracao_s < 20)
  ' /tmp/fechar_missao-PROVA-FT-02.steps.json >/dev/null \
    || falha "cenario B JSON tipado incorreto: $(cat /tmp/fechar_missao-PROVA-FT-02.steps.json)"
fi
[ -f "$SB" ] || falha "cenario B: fixture de vigia nao rodou (marca ausente)"
rm -rf "$FIXB"

if [ "$FAILS" -eq 0 ]; then
  echo "FECHAR-TIMEOUT-OK"
  echo "RESUMO: 0 falhas"
  exit 0
fi
echo "RESUMO: $FAILS falhas"
exit 1
