# RELATORIO-RD-WORKER-GUARD-01D

WORKER-GUARD-OK

## Suíte
`python3 -m pytest tests/test_worker_guard.py -q` -> **10 passed**.

## Causa raiz (resumo)
`git clean -fdx` retornava `NameError: name 'cmd' is not defined` porque `clean`
nao estava em `_GIT_WRITE_SUBS` (harness.py:351); o subcomando caia em
`_classify_seg` (harness.py:372), que chamava `_git_guard(cmd)` na linha 410 sem
`cmd` no escopo. `stash` ja estava no conjunto, por isso passava.

## Fix
Adicionado `"clean"` a `_GIT_WRITE_SUBS` em harness.py (1 linha). Suite: 10 passed.
