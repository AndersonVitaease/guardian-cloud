# MISSÃO HEADLESS-TAB-02C — fecho mínimo r3 (continuação 02)

CONTINUAÇÃO — NÃO recomece, NÃO mexa em código. Worktree real: `/home/worker/wt-HEADLESS-TAB-02` (branch `rd-headless-tab-02`, último commit `edc91bc8` "r2 fecho (relatorio + validacao)"). Estado VERIFICADO pelo supervisor agora:

- A prova `prova-HEADLESS-TAB-02.py` roda AO VIVO com exit 0 e marcador `PROVA-HEADLESS-TAB-02-OK` (todas as verificações (i)-(iv) OK).
- Único diff aberto: `prova-HEADLESS-TAB-02.out` (regenerado pela prova — só caminhos de tempdir mudaram, 2 linhas).
- As 3 tentativas da r2 falharam por `max_turns` (40 turnos), com o trabalho pousado — o veredito foi prematuro.

## Entregas (só isto)
1. Rodar `python3 prova-HEADLESS-TAB-02.py` (deve sair `PROVA-HEADLESS-TAB-02-OK`).
2. `git add prova-HEADLESS-TAB-02.out` e commit único: assunto `HEADLESS-TAB-02: r3 fecho (prova out)`. MAIS NADA.
3. Proibido: editar código, testes, relatório, README; proibido `git add -A`.

## Regras
- Sem sudo (você já é worker). Sem cat/head/ls; leitura por code_slice/grep -n.
- Não baixe nada da internet.

```harness-stop
cmd cd /home/worker/wt-HEADLESS-TAB-02 && python3 prova-HEADLESS-TAB-02.py
cmd cd /home/worker/wt-HEADLESS-TAB-02 && git log --format=%s -1 | grep -q -F 'HEADLESS-TAB-02: r3 fecho (prova out)'
cmd cd /home/worker/wt-HEADLESS-TAB-02 && test -z "$(git status -s -- .)"
```
