# MISSÃO DESP-STOP-01E — fecho (continuação 01)

O trabalho está pousado: commit `d1813eee` (lint recusa STOP_INTERPRETE_ESTRANHO) + prova `prova-DESP-STOP-01.py` VERDE no disco (exit 0, .out 221 bytes com `DESP-STOP-01-PROVA-OK`) — mas a prova e o .out NÃO foram commitados, e `tools-bash/custo_dia.sh` está modificado sem commit. A missão morreu no ritual de fecho.

## Entrega (fecho mínimo, sem re-trabalho)
1. Revise o diff de `tools-bash/custo_dia.sh`: se é parte coerente desta entrega (ex.: ajuste relacionado ao lint/custo), mantenha e comite; se é acidental, reverta com `git checkout -- tools-bash/custo_dia.sh` (revert de arquivo próprio é permitido; nada de reset/checkout de branch).
2. Comite prova + .out: `DESP-STOP-01E: prova + artifacts`.
3. Worktree limpo no fim.

## Stops
```harness-stop
cmd cd /home/worker/wt-DESP-STOP-01 && TMPDIR=$(mktemp -d) python3 prova-DESP-STOP-01.py
cmd cd /home/worker/wt-DESP-STOP-01 && grep -q -F 'DESP-STOP-01-PROVA-OK' prova-DESP-STOP-01.out
cmd cd /home/worker/wt-DESP-STOP-01 && test -z "$(git status -s -- .)"
cmd cd /home/worker/wt-DESP-STOP-01 && test -n "$(git ls-files prova-DESP-STOP-01.py)" # prova trackeada (baseline: untracked)
```
