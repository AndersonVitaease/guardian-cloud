#!/usr/bin/env bash
# prova-mecanico-v11.sh — prova da MISSAO V11-MECANICO
# Inicia o mecanico com um job fake (não-pintor) e MATA o filho da prova
# no meio → o mecanico precisa devolver JSON tipado (não travar), registrar
# FILHO_MORTO na trilha POR INSTÂNCIA e sair com veredito.
# Última linha: `RESUMO: X falhas`.
set -u
REPO=/home/worker/harness-s2
MEC="$REPO/scripts/mecanico.sh"
WORK="$REPO/runs/mecanico/tmp-v11"
FAILS=0
chk(){ if [ "$2" = "0" ]; then echo "[OK] $1"; else echo "[FAIL] $1 ($3)"; FAILS=$((FAILS+1)); fi; }

rm -rf "$WORK"; mkdir -p "$WORK"
CHILD_FILE="$WORK/filho.pid"
OUT="$WORK/saida-mecanico.json"

# 1. sintaxe
bash -n "$MEC"; chk "bash -n scripts/mecanico.sh" $? "sintaxe"

# 2. prova fake: escreve o próprio PID e dorme (filho que será morto)
cat > "$WORK/prova-fake-v11.py" <<PYEOF
import subprocess, sys, os
open("$CHILD_FILE", "w").write(str(os.getpid()))
p = subprocess.Popen(["sleep", "300"])
p.wait()
PYEOF

# 3. mecanico em background com job FAKE (não-pintor) e prova apontada pro fake
MEC_PROVA="$WORK/prova-fake-v11.py" MEC_PROVA_TIMEOUT=120 \
  bash "$MEC" "$REPO" "JOB-FAKE-NAO-PINTOR-V11" > "$OUT" 2>&1 &
MECPID=$!

# espera o filho da prova nascer (máx 30 s)
NASCIDO=1
for _ in $(seq 1 60); do
  [ -s "$CHILD_FILE" ] && break
  sleep 0.5
done
[ -s "$CHILD_FILE" ] || NASCIDO=0
chk "filho da prova nasceu (pid em $CHILD_FILE)" $(( 1 - NASCIDO )) "filho não apareceu em 30s"

# 4. MATA o filho no meio (python e o wrapper timeout — guard deve ver sinal)
if [ "$NASCIDO" = "1" ]; then
  FP=$(cat "$CHILD_FILE")
  kill -9 "$FP" 2>/dev/null
  pkill -9 -f "$WORK/prova-fake-v11.py" 2>/dev/null
  chk "kill -9 no filho da prova (pid=$FP)" 0 "kill falhou"
fi

# 5. mecanico NÃO pode travar: deve sair sozinho (máx 60 s após o kill)
DEAD=1
for _ in $(seq 1 120); do
  kill -0 "$MECPID" 2>/dev/null || { DEAD=0; break; }
  sleep 0.5
done
[ "$DEAD" = "0" ] || { kill -9 "$MECPID" 2>/dev/null; }
chk "mecanico não travou: saiu após o filho morto" "$DEAD" "mecanico ainda vivo após 60s"

wait "$MECPID" 2>/dev/null; MRC=$?

# 6. JSON tipado na saída
printf '%s' "$(cat "$OUT" 2>/dev/null)" | grep -q '{"ok":false,"error":"MEC_PROVA_FALHOU"'
chk "JSON tipado com veredito na saída (MEC_PROVA_FALHOU)" $? "sem JSON tipado (saída: $(tail -2 "$OUT" 2>/dev/null | tr '\n' ';'))"

# 7. trilha POR INSTÂNCIA: mecanico-trail-<pid>.jsonl existe e registra FILHO_MORTO
TRAIL_INST="$REPO/runs/mecanico/mecanico-trail-$MECPID.jsonl"
[ -s "$TRAIL_INST" ]; chk "trilha por instância existe ($TRAIL_INST)" $? "trilha ausente"
grep -q 'FILHO_MORTO' "$TRAIL_INST" 2>/dev/null
chk "trilha registra FILHO_MORTO (guard de interrupção)" $? "sem FILHO_MORTO na trilha"

# 8. job do argumento manda: cura do PINTOR NÃO reprocessada
if grep -q '"step":"patch"' "$TRAIL_INST" 2>/dev/null; then
  chk "job não-pintor NÃO reprocessou patch do pintor" 1 "evento patch presente"
else
  chk "job não-pintor NÃO reprocessou patch do pintor" 0 ""
fi
if grep -q '"step":"modelo"' "$TRAIL_INST" 2>/dev/null; then
  chk "job não-pintor NÃO reprocessou ensure_model do pintor" 1 "evento modelo presente"
else
  chk "job não-pintor NÃO reprocessou ensure_model do pintor" 0 ""
fi

echo "RESUMO: $FAILS falhas"
exit $(( FAILS > 0 ? 1 : 0 ))