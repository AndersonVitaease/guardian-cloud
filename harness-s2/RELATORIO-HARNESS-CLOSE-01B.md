# HARNESS-CLOSE-01B — relatório

O bloco `harness-close` do contrato adiciona stops de fecho pós-entregável: após os stops normais verdes, o harness injeta re-prompt de fecho (cap de 3 ciclos, evento `_close_reprompt` no trail) e, se os stops de fecho falharem, encerra com FAIL honesto (`fecho_incompleto`); `HARNESS_CLOSE=0` (rollback) desliga todo o comportamento e missões sem bloco close ficam inalteradas.

Prova: suíte completa verde — `525 passed, 2 skipped` (`/usr/bin/python3 -m pytest tests/ -q`), incluindo os 7 testes de `tests/test_harness_close.py` (parse, reprompt+FAIL honesto, close verde, sem bloco inalterado, rollback).