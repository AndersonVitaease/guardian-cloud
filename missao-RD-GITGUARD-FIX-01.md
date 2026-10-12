# MISSÃO RD-GITGUARD-FIX-01 — guard de git quebra redirect de LEITURA (NameError 'cmd')

Fonte: FIND 12/10 — merge do guard na base (1e05c669) regressinou o ENFORCE-H:
`git log/status` via Bash cru no worker dá "ERRO: NameError: name 'cmd' is not
defined" (provado: test_enforce.py::TestRedirect::test_git_log_e_redirecionado
falha na base). Causa cravada: `_git_guard(cmd)` é chamado dentro de
`_classify_seg(toks)` (harness.py:410), onde `cmd` não existe no escopo.

## MAPA (arquivo:linha, verificado)

- harness.py:372 — `def _classify_seg(toks):` (sem param cmd)
- harness.py:405-423 — dentro de _classify_seg: L410 `_gv0 = _git_guard(cmd)`
  (a linha que quebra); L413-423 redirect git_peek
- harness.py:592 — `return _classify_seg(plan[0])` (chamador em _bash_redirect)
- harness.py:450-488 — `def _git_guard(cmd)` (assinatura correta: recebe STRING)
- harness.py:1180 — 2º uso de _git_guard (em run_tool, onde cmd existe — ok)
- tests/test_enforce.py:122-124 — teste que hoje prova o NameError
- tests/test_worker_guard.py — suíte do guard (precisa seguir verde)

## Tarefa (nesta ordem)

1. Mudança mínima: `_classify_seg(toks, cmd=None)`; L410 vira
   `_gv0 = _git_guard(cmd if cmd is not None else " ".join(toks))`;
   no chamador L592 passe o segmento original:
   `return _classify_seg(plan[0], " ".join(plan[0]))` (ou passe a string
   original do segmento se disponível em _bash_redirect — escolha a menor
   alteração que faça os testes passar; NÃO redesenhe o guard).
2. Confirme com code_slice antes/depois de cada edit; escrita via Bash
   heredoc python (Write/Edit confinados ao run-dir — path absoluto dá
   PermissionError).
3. Suíte: `cd /home/worker/wt-RD-WORKER-GUARD && python3 -m pytest
   tests/test_enforce.py tests/test_worker_guard.py tests/test_fatiador.py -q`
   — tudo verde (relate a contagem exata).
4. RELATORIO-RD-GITGUARD-FIX-01.md na raiz do worktree (heredoc) com
   marcador GITGUARD-FIX-OK.
5. UM commit: `git add harness.py tests/ RELATORIO-RD-GITGUARD-FIX-01.md`
   + subject exato `RD-GITGUARD-FIX-01: guard nao quebra redirect de leitura (fecho)`.

## Regras (GB-FORCA-ESCRITA-01)

Heredoc python para escrever; code_slice/code_find para ler; sem git
reset/checkout de branch/stash/clean; sem tocar em routing/bridge; mudança
mínima (assinatura + 1-2 chamadores), sem redesign.

## Stops Vermelhos na baseline (NÃO corrija as stops)

```harness-stop
cmd cd /home/worker/wt-RD-WORKER-GUARD && python3 -m pytest tests/test_enforce.py tests/test_worker_guard.py -q 2>&1 | grep -q -E '[0-9]+ passed'
cmd cd /home/worker/wt-RD-WORKER-GUARD && grep -q -F 'GITGUARD-FIX-OK' RELATORIO-RD-GITGUARD-FIX-01.md
cmd cd /home/worker/wt-RD-WORKER-GUARD && test "$(git log -1 --format=%s)" = "RD-GITGUARD-FIX-01: guard nao quebra redirect de leitura (fecho)"
```
