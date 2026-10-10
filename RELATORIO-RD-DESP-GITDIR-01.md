# RELATÓRIO RD-DESP-GITDIR-01 — Cura do gitdir de worktree aninhado

## O que foi feito

Criado `scripts/despachar_rapido_gitdir.py` com 2 funções:

- `resolver_gitdir(caminho)`: roda `git -C <caminho> rev-parse --git-common-dir`
  (e, quando `.git` é FILE — stub de worktree — usa `rev-parse --git-dir` para
  obter o gitdir específico `<pai>/.git/worktrees/<nome>`), retorna caminho
  absoluto e realpath. Em falha (rc != 0) raise
  `RuntimeError("GITDIR_INDETERMINADO: <stderr curto>")`.
- `corrigir_gitdir(caminho, chown_fn=None, spec="worker:worker")`: monta alvos
  (caminho, `.git` FILE quando existir, gitdir real), filtra existentes, aplica
  chown (subprocess `chown -R` para diretório, `chown` para arquivo, timeout
  120 s, raise em rc != 0) ou `chown_fn(alvo, spec)` quando injetado; retorna
  lista dos alvos chownados na ordem caminho, .git FILE, gitdir.

Motivação: em worktree aninhado o gitdir real mora FORA do worktree
(`<repo-pai>/.git/worktrees/<nome>`); sem chown dele o commit do worker morre
em "dubious ownership" (PROVA_COMMIT_FALHOU). A cura existia só em /opt; agora
fixada no repo como módulo próprio.

## Saída real do aceite

```
$ python3 -m unittest tests.test_despachar_rapido_gitdir
...
Ran 3 tests in 0.088s

OK
```

## Provas dos stops

- `git log -1 --pretty=%s` contém `RD-DESP-GITDIR-01`; commit inclui
  `scripts/despachar_rapido_gitdir.py` e este relatório.
- `python3 -m py_compile scripts/despachar_rapido_gitdir.py` → OK.
- `grep -F 'rev-parse --git-common-dir'`, `def corrigir_gitdir`,
  `def resolver_gitdir` → presentes.
- `python3 -m unittest tests.test_despachar_rapido_gitdir` → `OK` (3 tests).
- `tests/test_despachar_rapido_gitdir.py` não editado (`git diff --quiet HEAD`).
- Este relatório existe e cita `RD-DESP-GITDIR-01`.