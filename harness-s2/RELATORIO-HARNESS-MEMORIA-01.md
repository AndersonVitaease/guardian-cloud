# RELATORIO-HARNESS-MEMORIA-01 — HARNESS-MEMORIA-01 (rascunho T1)

## O que foi feito
Em andamento: scripts/aprende.py + wire em mission_run.py + tests/test_aprende.py.

## Verificador
pytest tests/test_aprende.py

## Motivo
Gap: aprendizado da missão morre no run dir, nada grava em memória consultável.

## Causa
Resultado de missão só existia em RELATORIO/resumo do run dir; faltava primitiva de captura.

## Dívidas
Nenhuma conhecida.