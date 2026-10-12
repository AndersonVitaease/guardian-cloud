# MISSÃO RD-WORKER-GUARD-01C — continuação: provar, commitar e relatar o guard de git

Fonte: ROADMAP-GUARDIAN v2 §WORKER-GUARD; continuação de RD-WORKER-GUARD-01
(FECHO MÍNIMO — o trabalho já pousou no disco).

CONTINUAÇÃO — não recomece. Estado VERIFICADO do WIP no worktree
/home/worker/wt-RD-WORKER-GUARD (tentativas anteriores da missão mãe falharam
em vagueio antes do commit; o código está pronto mas NÃO commitado):

- harness.py MODIFICADO (não commitado): guard de git no Bash (recusa
  `git reset --hard`, reset com ref, checkout de branch, stash, clean com
  erro tipado GIT_GUARD_RESET_PROIBIDO; checkout -- arquivo e unstage
  permitidos) + prova mecânica no veredito (_parse_prova_mecanica,
  _rodar_prova_mecanica, veredito PROVA_FALHOU).
- tests/test_worker_guard.py NOVO (não commitado): 9 testes pytest
  (reset --hard/recusado, reset com ref, checkout branch, stash/clean,
  checkout arquivo permitido, unstage permitido, prova verde OK, prova
  vermelha PROVA_FALHOU, contrato sem seção, log da recusa no trail via
  RD_GIT_GUARD_LOG).

## Tarefa (nesta ordem — NADA de código novo, exceto correção mínima se a suíte acusar falha)

1. Rode a suíte como worker: `cd /home/worker/wt-RD-WORKER-GUARD && python3 -m pytest tests/test_worker_guard.py -q`.
2. Se TODOS passarem: vá direto ao passo 3. Se algum falhar: correção
   MÍNIMA no ponto acusado (harness.py ou test_worker_guard.py) — um
   `old_string` de UMA linha distinta por edição, relido com code_slice
   IMEDIATAMENTE antes — e re-robe a suíte. Proibido refazer/refatorar.
3. `git add` restrito: só `harness.py` e `tests/test_worker_guard.py`.
   UM commit com subject `RD-WORKER-GUARD-01C: guard de git + prova mecanica (fecho)`.
4. RELATORIO-RD-WORKER-GUARD-01C.md com marcador WORKER-GUARD-OK + contagem
   exata da suíte (ex.: `9 passed`) + resultado do pytest colado.

## MAPA (arquivo:símbolo:linha, WIP atual)

- harness.py:run_tool:1122 — guard de comandos Bash (ponto de interceptação)
- harness.py:_parse_prova_mecanica:491 — parse da seção `## Prova mecanica`
- harness.py:_rodar_prova_mecanica:513 — execução da prova + PROVA_FALHOU
- tests/test_worker_guard.py — suíte (9 testes pytest)

## Regras (GB-FORCA-ESCRITA-01)

Write direto; leitura com code_slice; sem git reset/checkout de branch/stash/
clean; sem tocar em routing/bridge; `git add` restrito (nunca -A).

## Stops Vermelhos na baseline (NÃO corrija as stops)

```harness-stop
cmd cd /home/worker/wt-RD-WORKER-GUARD && python3 -m pytest tests/test_worker_guard.py -q 2>&1 | grep -q -E '^9 passed'
cmd cd /home/worker/wt-RD-WORKER-GUARD && test -z "$(git status --porcelain)"
cmd cd /home/worker/wt-RD-WORKER-GUARD && grep -q -F 'WORKER-GUARD-OK' RELATORIO-RD-WORKER-GUARD-01C.md
```

## Prova mecanica

cmd cd /home/worker/wt-RD-WORKER-GUARD && python3 -m pytest tests/test_worker_guard.py -q
expect 9 passed
