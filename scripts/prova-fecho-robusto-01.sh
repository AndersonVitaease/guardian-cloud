#!/bin/bash
# DESP-FECHO-ROBUSTO-01: prova do fecho robusto.
set -u
echo '{"missao":"PROVA-FECHO","status":"ok"}' > /tmp/resumo-PROVA-FECHO.json
rm -f /tmp/fechar_missao-PROVA-FECHO.log
bash /home/worker/wt-DESP-FECHO-ROBUSTO-01/scripts/fechar_missao.sh PROVA-FECHO
rc1=$?
bash /home/worker/wt-DESP-FECHO-ROBUSTO-01/scripts/fechar_missao.sh PROVA-FECHO
rc2=$?
if [ $rc1 -ne 0 ] || [ $rc2 -ne 0 ]; then echo "FALHA rc1=$rc1 rc2=$rc2"; exit 1; fi
test -f /tmp/fechar_missao-PROVA-FECHO.log || { echo "FALHA log ausente"; exit 1; }
echo "PROVA OK rc1=$rc1 rc2=$rc2"
exit 0
