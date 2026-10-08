#!/bin/sh
# 3 execuções do ZERO da canária média — cwd isolado por run, seed variado.
cd /home/worker/harness-s2
for s in ${SEEDS:-11 12 13}; do
  python3 harness.py --contract canary/contrato-canaria-media.md --cwd runs/canaria \
    --budget 1.0 --max-turns 60 --seed $s > runs/canaria-seed$s.log 2>&1
  echo "seed=$s exit=$?" >> runs/canarias-exit.txt
done
