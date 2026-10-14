# MISSÃO RD-ENG-SHIP-09 — SHIP final do M1-GATE (wrapper com sequência oficial 5/5)

Fonte: continuação da SHIP-08 — a tool release_pipeline agora orquestra a
sequência oficial test→build→candidate→deploy (suíte 5/5, commit e338ae0,
aplicada em produção pelo supervisor). Fonte da cadeia: ROADMAP L55 + ordem do
operator 11/10 (SHIP aprovado; condução SEMPRE por missão).

## Tarefa (nesta ordem)

1. Como worker, invoque a tool bash governada do SEU worktree:
   bash tools-bash/release_pipeline.sh pipeline 1696e9baff935bb1a390c2784b9975dd1282f84f
2. O corpo da resposta deve ser citado VERBATIM no relatório (accepted/jobId/erro).
3. Depois, a cada ~45s, rode: bash tools-bash/release_pipeline.sh status — até
   currentCommitSha == 1696e9baff935bb1a390c2784b9975dd1282f84f OU um erro tipado.
   NUNCA conclua SHIP-OK com currentCommitSha diferente do alvo (lição SHIP-07).
4. RELATORIO-RD-ENG-SHIP-09.md com marcador SHIP-OK (só com currentCommitSha
   igual ao alvo, deployStatus PASS e smokeStatus PASS) ou SHIP-FALHOU (com o
   erro tipado verbatim). Nada de rollback por conta própria.
5. Commit worker com o ID no subject (git add restrito ao relatório).

## Stops Vermelhos na baseline (NÃO corrija as stops)

```harness-stop
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && test -f RELATORIO-RD-ENG-SHIP-09.md
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && grep -q -F 'SHIP-OK' RELATORIO-RD-ENG-SHIP-09.md
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && grep -q -F '1696e9baff935bb1a390c2784b9975dd1282f84f' RELATORIO-RD-ENG-SHIP-09.md
```
