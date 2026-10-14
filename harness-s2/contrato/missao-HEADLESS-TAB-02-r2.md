---
class: mecanica
component: harness-s2
---
# MISSÃO HEADLESS-TAB-02 — r2 fecho (relatório + validação)

Fonte: ROADMAP.md linha 457 (prio 1). Continuação da r1.

## CONTINUAÇÃO — NÃO RECOMECE
O trabalho técnico da r1 está PRONTO e COMMITADO neste worktree (branch `rd-headless-tab-02`). Não investigue, não rode a prova, não toque em código. Sua ÚNICA tarefa: escrever o relatório de fecho e commitar.

## Estado verificado do WIP (11/10 ~13:30 BRT, supervisor)
- Commits prontos: `710983a3` e `26156fb4` ("HEADLESS-TAB-02: label RUN:ID#sSEED + pane run tail -F ao vivo (fail-open) + prova hermetica") e `b6114609` ("HEADLESS-TAB-02: aba unica RUN:ID#sSEED + montagem ao vivo tail da trilha no pane (fail-open)"). Contrato r1 em `c404671d`.
- `patches/orchestrator-consumer.diff`: 68 linhas, diff -u aplicável pelo supervisor.
- `prova-HEADLESS-TAB-02.py` + `prova-HEADLESS-TAB-02.out` presentes. `git status` mostra APENAS ` M prova-HEADLESS-TAB-02.out`.
- `RELATORIO-HEADLESS-TAB-02.md` tem só 21 bytes (só a data "11/10/2026 13:19 BRT") — é o ÚNICO stop faltante.
- Causa raiz do FAIL da r1: 3 tentativas vaguearam em exploração; nada técnico faltava (5/6 stops verdes no disco antes do relatório).

## Tarefa única (nesta ordem, sem explorar)
1. Escreva `RELATORIO-HEADLESS-TAB-02.md` COMPLETO e HONESTO (>600 bytes), SUBSTITUINDO o arquivo atual de 21 bytes com Write inteiro (não Edit). Conteúdo obrigatório:
   - Entrega real: os 3 commits acima (subjects literais), `patches/orchestrator-consumer.diff` (68 linhas) e a prova hermética `prova-HEADLESS-TAB-02.py` com marker `PROVA-HEADLESS-TAB-02-OK` em `prova-HEADLESS-TAB-02.out`.
   - O que o patch muda no consumer: label único `RUN:<ID>#s<seed>` em `ensure_run_tab` + montagem do conteúdo AO VIVO no pane (`herdr pane run` com `until test -f <trilha>; do sleep 1; done; tail -n +1 -F <trilha>`) + fail-open quando o dispatch não traz run_dir.
   - Instruções supervisor-side EXATAS de aplicação: ler o cabeçalho do diff com `code_slice.sh /home/worker/wt-HEADLESS-TAB-02/patches/orchestrator-consumer.diff 1 8` para confirmar os caminhos a/b e escrever o comando `patch`/`git apply` correto sobre o arquivo alvo indicado no próprio cabeçalho do diff (o consumer de produção; caminho exato vem do diff) + restart do serviço systemd do consumer (`systemctl restart` da unit do orchestrator-consumer) + como provar depois (grep do label `#s` no arquivo patchado e `systemctl status` da unit).
   - Status da r1: FAIL 5/6 em 3 tentativas por vagueio (relatório subdimensionado com 21 bytes), horários BRT; data/hora desta r2 em BRT (-03).
2. O arquivo `prova-HEADLESS-TAB-02.out` está modificado (` M`): commite-o JUNTO com o relatório (é saída da prova da missão).
3. Commit único: `cd /home/worker/wt-HEADLESS-TAB-02 && git add RELATORIO-HEADLESS-TAB-02.md prova-HEADLESS-TAB-02.out && git commit -m 'HEADLESS-TAB-02: r2 relatorio de fecho'`. Worktree deve ficar limpo (`git diff --quiet HEAD` e `git status` sem mudanças).

## Proibições
- NÃO altere código (server/mission_run/despachar — já pronto e commitado); NÃO mexa em `patches/`; NÃO escreva em `/opt` ou `/root`; NÃO despache nada.
- NUNCA use `git reset/checkout/stash/clean`; `git add` apenas dos 2 arquivos da tarefa.
- Zero exploração: leia no máximo o cabeçalho do diff (passo 1) com `code_slice.sh`.

## MAPA
- RELATORIO-HEADLESS-TAB-02.md : arquivo inteiro (Write) : 1
- patches/orchestrator-consumer.diff : cabeçalho p/ instruções de patch : L1-8
- prova-HEADLESS-TAB-02.out : mudança ` M` : commitar junto

```harness-stop
cmd cd /home/worker/wt-HEADLESS-TAB-02 && test $(stat -c%s RELATORIO-HEADLESS-TAB-02.md) -gt 600
cmd cd /home/worker/wt-HEADLESS-TAB-02 && grep -q HEADLESS-TAB-02 RELATORIO-HEADLESS-TAB-02.md
cmd cd /home/worker/wt-HEADLESS-TAB-02 && git diff --quiet HEAD
cmd cd /home/worker/wt-HEADLESS-TAB-02 && git log -3 --format=%s | grep -q "HEADLESS-TAB-02: r2 relatorio de fecho"
```
