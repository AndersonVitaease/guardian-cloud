#!/usr/bin/env bash
# prova-mecanico.sh — prova da MISSAO MECANICO-01
# 1. bash -n scripts/mecanico.sh
# 2. conserto do PINTOR: PNG >0 bytes em wt-RD-SUBJ-AUDIT-01/images/ (ou FAIL honesto)
# 3. `RESUMO: X falhas`
set -u
FAILS=0
chk(){ if [ "$2" = "0" ]; then echo "[OK] $1"; else echo "[FAIL] $1 ($3)"; FAILS=$((FAILS+1)); fi; }

bash -n /home/worker/harness-s2/scripts/mecanico.sh; chk "bash -n scripts/mecanico.sh" $? "sintaxe"

PNG=$(find /home/worker/wt-RD-SUBJ-AUDIT-01/images -maxdepth 1 -name '*.png' -size +0c 2>/dev/null | head -1)
if [ -n "$PNG" ]; then
  echo "[OK] PNG em images/ ($PNG, $(stat -c %s "$PNG") bytes)"
else
  echo "[FAIL] PNG ausente em images/ — veredito honesto do mecanico:"
  tail -5 /home/worker/harness-s2/runs/mecanico/mecanico-trail.jsonl 2>/dev/null
  FAILS=$((FAILS+1))
fi

echo "RESUMO: $FAILS falhas"
exit $(( FAILS > 0 ? 1 : 0 ))
