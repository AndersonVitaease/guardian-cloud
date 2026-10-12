# MISSÃO RD-WORKER-GUARD-01D — continuação: fix de 1 linha (clean no _GIT_WRITE_SUBS) + fechar

Fonte: ROADMAP-GUARDIAN v2 §WORKER-GUARD; continuação de RD-WORKER-GUARD-01C
(diagnóstico já feito pelo supervisor — NÃO investigue, execute).

CONTINUAÇÃO — não recomece. Estado VERIFICADO do WIP (worktree
/home/worker/wt-RD-WORKER-GUARD, tudo NÃO commitado):

- harness.py MODIFICADO: guard de git + prova mecânica — código pronto,
  suíte dá `1 failed, 9 passed`.
- tests/test_worker_guard.py NOVO: 10 testes pytest.
- FALHA ÚNICA: `test_stash_e_clean_recusados` → `git clean -fdx` retorna
  `ERRO: NameError: name 'cmd' is not defined`. Causa raiz (confirmada por
  reprodução): `clean` não está em `_GIT_WRITE_SUBS` (harness.py:351), então
  `git clean` cai em `_classify_seg` (harness.py:372), que chama
  `_git_guard(cmd)` na linha 410 sem `cmd` no escopo. `stash` está no
  conjunto — por isso passou.

## Tarefa (nesta ordem — NADA além disto)

1. Edit com old_string EXATO de UMA linha (leia a linha com code_slice
   ANTES, arquivo harness.py):
   - old: `                   "stash", "apply", "add", "rm", "worktree", "branch", "init",`
   - new: `                   "stash", "clean", "apply", "add", "rm", "worktree", "branch", "init",`
2. Rode a suíte como worker:
   `cd /home/worker/wt-RD-WORKER-GUARD && python3 -m pytest tests/test_worker_guard.py -q`
   → esperado `10 passed`. Se algo diferente, corrija o MÍNIMO e re-robe.
3. `git add harness.py tests/test_worker_guard.py RELATORIO-RD-WORKER-GUARD-01D.md`
   e UM commit com subject exato
   `RD-WORKER-GUARD-01D: guard de git fechado (clean em _GIT_WRITE_SUBS)`.
4. RELATORIO-RD-WORKER-GUARD-01D.md com marcador WORKER-GUARD-OK + contagem
   da suíte + a causa raiz acima resumida. (Escreva o relatório ANTES do
   commit, na ordem 3→4 ajustada: relatório primeiro, depois add+commit.)

## MAPA (arquivo:símbolo:linha)

- harness.py:_GIT_WRITE_SUBS:351 — adicionar "clean" (fix único)
- harness.py:_classify_seg:372 — caminho onde o NameError ocorria (não editar)
- harness.py:_git_guard:450 — guard de git (não editar)
- tests/test_worker_guard.py — suíte, 10 testes

## Regras (GB-FORCA-ESCRITA-01)

Write direto; leitura com code_slice; sem git reset/checkout de branch/stash/
clean; sem tocar em routing/bridge; git add restrito aos 3 arquivos.

## Stops Vermelhos na baseline (NÃO corrija as stops)

```harness-stop
cmd cd /home/worker/wt-RD-WORKER-GUARD && python3 -m pytest tests/test_worker_guard.py -q 2>&1 | grep -q -E '^10 passed'
cmd cd /home/worker/wt-RD-WORKER-GUARD && test -z "$(git status --porcelain)"
cmd cd /home/worker/wt-RD-WORKER-GUARD && grep -q -F 'WORKER-GUARD-OK' RELATORIO-RD-WORKER-GUARD-01D.md
```

## Prova mecanica

cmd cd /home/worker/wt-RD-WORKER-GUARD && python3 -m pytest tests/test_worker_guard.py -q
expect 10 passed
