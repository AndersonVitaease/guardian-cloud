# MISSÃO TRIAGEM-SUITE-01 — diagnóstico das falhas pré-existentes da suíte do harness

Fonte: FIND 12/10 — suíte da base harness-s2 como worker: 12 failed, 641
passed (custo_dia_runs 5, enforce 2, harness_close 1, tools_guard_02 2,
watchdog 2 — os 2 de enforce foram CORRIGIDOS pelo merge RD-GITGUARD-FIX-01;
re-rode para confirmar). Objetivo: DIAGNÓSTICO, não correção — nenhum arquivo
de código é alterado nesta missão.

## Mecânica

- Suíte como worker (como o fecho roda):
  cd /home/worker/wt-RD-WORKER-GUARD && timeout 240 sudo -u worker /usr/bin/env bash -c "/usr/bin/python3 -m pytest tests/ -q 2>&1" | grep -E "FAILED|passed|failed"
- Para cada FAILED: rode o teste isolado e capture a assertiva
  (pytest <teste> -q 2>&1 | tail -20).

## Entregas (nesta ordem)

1. RELATORIO-TRIAGEM-SUITE-01.md (na raiz do worktree, via heredoc python —
   Write/Edit confinados ao run-dir) contendo, para CADA teste que falhar:
   nome, assertiva que quebrou, e classificação em exatamente uma das
   categorias: (A) BUG_REAL — comportamento do harness errado; (B) AMBIENTE —
   teste correto mas depende de contexto que a suíte não provê; (C) OBSOLETO
   — teste testando comportamento que mudou. Com uma linha de evidência por
   item (a saída do pytest).
2. Última seção do relatório: contagem por categoria + recomendação por item
   (corrigir código | corrigir teste | pular com justificativa).
3. Marcador TRIAGEM-SUITE-OK no relatório.
4. UM commit: `git add RELATORIO-TRIAGEM-SUITE-01.md` + subject exato
   `TRIAGEM-SUITE-01: diagnostico das falhas pre-existentes (fecho)`.

## Regras (GB-FORCA-ESCRITA-01)

Heredoc python p/ escrever; code_slice p/ ler; sem git reset/checkout de
branch/stash/clean; PROIBIDO editar código ou testes nesta missão (diagnóstico
somente).

## Stops Vermelhos na baseline (NÃO corrija as stops)

```harness-stop
cmd cd /home/worker/wt-RD-WORKER-GUARD && grep -q -F 'TRIAGEM-SUITE-OK' RELATORIO-TRIAGEM-SUITE-01.md
cmd cd /home/worker/wt-RD-WORKER-GUARD && grep -q -F 'BUG_REAL\|AMBIENTE\|OBSOLETO' RELATORIO-TRIAGEM-SUITE-01.md
cmd cd /home/worker/wt-RD-WORKER-GUARD && test "$(git log -1 --format=%s)" = "TRIAGEM-SUITE-01: diagnostico das falhas pre-existentes (fecho)"
```
