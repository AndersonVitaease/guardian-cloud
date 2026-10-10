# MISSÃO RUN-STREAM-01C — 3 correções do run_stream.sh medidas ao vivo

Fonte: ROADMAP.md linha 381.

operatorOrder: micro-correções aprovadas pelo operador 10/10.

## CONTINUAÇÃO — ESTADO VERIFICADO (não recomeçar)
- Worktree /home/worker/wt-RUN-STREAM-01, branch rd-run-stream-01 já mergeada na base (shebang corrigido em RUN-STREAM-01B). run_stream.sh instalado em /opt e funcional.
- As 3 arestas abaixo foram MEDIDAS pelo supervisor em prova viva (`run_stream.sh HARNESS-CLOSE-01B` em 10/10 ~19:10 BRT):
  1. **Resolver de missionId pega run dir velho**: com `--follow`/snapshot por ID, apontou o trail de tentativa ANTIGA que já tinha veredito vagueio, em vez do run dir ativo da tentativa corrente (o ledger cwd pode estar stale no layout tentativa-N). CORREÇÃO: ao resolver missionId, escolher o run dir MAIS RECENTE por mtime entre tentativa-*/run-* do mission dir (e validar que o trail não tem VEREDITO se existir run dir mais novo sem veredito).
  2. **Veredito vaza dict interno**: linha `VEREDITO | vagueio | ${'calls': 20, 'usd': 0.029157, ...}` — extrair só usd/formatar `usd=0.029` (e turnos/motivo já ok).
  3. **custo acumulado (janela) = $0.000000** com eventos presentes: soma dos deltas não pegou o campo certo do trail — corrigir para o campo de custo real usado nos eventos de turno.

## TAREFA
1. Corrigir os 3 pontos em run_stream.sh.
2. Estender test_run_stream.sh: (a) dois run dirs tentativa-1 (com VEREDITO) e tentativa-2 (sem) → resolver escolhe tentativa-2; (b) linha VEREDITO sai formatada sem `${`; (c) custo acumulado ≠ 0 com fixture de deltas conhecidos.
3. Commit `RUN-STREAM-01C: resolver mtime + veredito limpo + custo real` e `RUN-STREAM-01C: relatorio` (RELATORIO-RUN-STREAM-01C.md, 2 linhas).

## ACEITE
```harness-stop
cmd cd /home/worker/wt-RUN-STREAM-01 && git log -1 --format=%s | grep -q -F "RUN-STREAM-01C: resolver mtime"
cmd cd /home/worker/wt-RUN-STREAM-01 && bash -n run_stream.sh
cmd cd /home/worker/wt-RUN-STREAM-01 && bash test_run_stream.sh
cmd cd /home/worker/wt-RUN-STREAM-01 && git ls-files --error-unmatch run_stream.sh && git -C /home/worker/wt-RUN-STREAM-01 diff --quiet HEAD -- run_stream.sh
cmd cd /home/worker/wt-RUN-STREAM-01 && git ls-files --error-unmatch RELATORIO-RUN-STREAM-01C.md
```

PROIBIDO: git reset/checkout/stash/clean; escrita em /opt e /root; loop de sleep.
