# MISSÃO DESP-STOP-01 — lint valida interpretador da prova nos stops

Prova viva (11/10): DESP-FECHO-BASE-01 fechou FAIL FALSO — a prova era `.sh` verde com bash, mas o stop rodava `python3 scripts/prova-...sh` (SyntaxError). Cura: o lint de contrato deve recusar stop cujo comando chame `python3` em arquivo com extensão `.sh` (e `bash`/`sh` em `.py`).

## MAPA (scripts/, branch rd-desp-stop-01)
- despachar_missao.py:77-80 — lint bloqueante existente (chama LINT antes de parsear stops); é onde o novo check entra ou no próprio lint.
- Encontre LINT no topo do arquivo (constante) — o linter externo pode ser o lugar certo (se o lint valida "cita arquivos sem MAPA", adiciona regra: comando de stop `python3 X.sh` ou `bash X.py` => erro `STOP_INTERPRETE_ESTRANHO`).
- test_lint* / tests/ — testes existentes do lint; adicione caso novo (positivo e negativo).
- prova-stream02.py, scripts/prova-DESP-FECHO-BASE-01.sh — exemplos reais (não mexa).

## Entregas
1. Regra no lint: stop `cmd ... python3 <algo>.sh` (ou `sh`/`bash <algo>.py`) recusa contrato com `STOP_INTERPRETE_ESTRANHO` + nome do arquivo. Extensões `.py`→python3, `.sh`→bash/sh.
2. Testes: contrato com stop errado recusado; com stop certo aceito.
3. Prova E2E hermética `prova-DESP-STOP-01.py`: contrato errado → LINT_RECUSADO com código novo; contrato certo → despacho não recusa por isso. Marcador `DESP-STOP-01-PROVA-OK` no .out >200 bytes.
4. Commits `DESP-STOP-01:`. Sem sudo, sem reset/checkout/stash, sem internet.

## Stops
```harness-stop
cmd cd /home/worker/wt-DESP-STOP-01 && python3 -m pytest tests/ -q
cmd cd /home/worker/wt-DESP-STOP-01 && python3 prova-DESP-STOP-01.py
cmd cd /home/worker/wt-DESP-STOP-01 && test $(stat -c%s prova-DESP-STOP-01.out 2>/dev/null || echo 0) -gt 200
cmd cd /home/worker/wt-DESP-STOP-01 && git log --format=%s -1 | grep -q -F 'DESP-STOP-01'
cmd cd /home/worker/wt-DESP-STOP-01 && test -z "$(git status -s -- .)"
```
