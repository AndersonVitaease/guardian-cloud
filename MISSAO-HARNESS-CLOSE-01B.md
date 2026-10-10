# MISSÃO HARNESS-CLOSE-01B — fecho da fase-fecho: 2 testes vermelhos + commit

Fonte: ROADMAP.md linha 370.

operatorOrder: continuação autorizada pelo operador 10/10 (verificação 18:01 BRT).

## CONTEXTO — CONTINUAÇÃO, NÃO RECOMECE

A HARNESS-CLOSE-01 falhou 3× por vagueio, mas o trabalho está NO DISCO do worktree `/home/worker/wt-HARNESS-CLOSE-01` (estado VERIFICADO pelo supervisor às 18:05 BRT):

- `harness.py` MODIFICADO (não commitado), `py_compile` OK — a implementação do bloco `harness-close` (parse + re-prompt de fecho + cap 3 + rollback HARNESS_CLOSE) já está escrita (9 ocorrências de `harness_close|close_reprompt`).
- `tests/test_harness_close.py` NOVO, untracked — suíte dele: **5 passed, 2 failed**:
  - `TestClose::test_sem_bloco_close_comportamento_inalterado`
  - (leia a 2ª falha exata rodando o teste)
- REGRA DE OURO: NUNCA `git reset/checkout/stash/clean` — o WIP é a única cópia.

## TAREFA (ordem)

1. Rode `/usr/bin/python3 -m pytest tests/test_harness_close.py -q` e leia as 2 falhas EXATAS.
2. Correção MÍNIMA: se o teste define o comportamento, corrija o harness.py; se o patch está certo e o teste está errado, corrija o teste. Preserve: rollback HARNESS_CLOSE=0 desliga tudo; missão SEM bloco close = comportamento inalterado; cap de 3 re-prompts; evento `_close_reprompt` no trail.
3. Suíte INTEIRA verde: `/usr/bin/python3 -m pytest tests/ -q` (baseline da base era 524 passed, 2 skipped).
4. Commit como worker: `HARNESS-CLOSE-01B: fase-fecho (bloco harness-close + re-prompt cap 3 + rollback)` com `git add` SÓ de `harness.py` e `tests/test_harness_close.py`.
5. `RELATORIO-HARNESS-CLOSE-01B.md` na raiz (2 linhas: o que o bloco faz + prova da suíte) + commit `HARNESS-CLOSE-01B: relatorio`.

## MAPA PRÉ-DIGERIDO

- Implementação já escrita em `harness.py` — procure `harness_close`/`close_reprompt` com `grep -n` (leitura mecânica recusada 2× → `code_slice.sh <arq> <ini> <fim>`).
- Testes em `tests/test_harness_close.py` — patch de ATRIBUTO `harness.HARNESS_CLOSE` (nunca env no setUp; chega tarde, o módulo já importou).
- Testes de run longa sem entregável precisam `vagueio=False`.
- Edite APÓS ler o trecho exato imediatamente antes (Edit com old_string de UMA linha distinta).

```harness-stop
cmd cd /home/worker/wt-HARNESS-CLOSE-01 && git log -1 --format=%s | grep -q -F "HARNESS-CLOSE-01B: fase-fecho"
cmd cd /home/worker/wt-HARNESS-CLOSE-01 && /usr/bin/python3 -m py_compile harness.py
cmd cd /home/worker/wt-HARNESS-CLOSE-01 && /usr/bin/python3 -m pytest tests/ -q
cmd cd /home/worker/wt-HARNESS-CLOSE-01 && git ls-files --error-unmatch tests/test_harness_close.py
cmd cd /home/worker/wt-HARNESS-CLOSE-01 && git ls-files --error-unmatch RELATORIO-HARNESS-CLOSE-01B.md
```
