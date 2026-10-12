# MISSÃO RD-WORKER-GUARD-01 — guardas mecânicas do worker (reset proibido + prova obrigatória no veredito)

Fonte: lições do ciclo 11-12/10 — worker fez git reset apagando o branch
(OFFICE-02) e marcou veredito OK com ressalvas que o desmentiam (SHIP-07/10,
OFFICE-03). Cláusula no contrato não trava; guarda mecânica sim.

## MAPA (arquivo:linha, base rd-segue-01)

- harness.py — ciclo do worker: execução de tools Bash (ponto de interceptação
  para o guard de comandos) e emissão do veredito/STOP conditions
- mission_run.py — spawn da run e variáveis de ambiente da missão
- Contratos existentes citam a regra como "GB-FORCA-ESCRITA-01" (grep no
  harness-s2 para achar onde a regra é avaliada hoje, se algum lugar)

## Tarefa (nesta ordem)

1. GUARD DE GIT no Bash do worker: comandos `git reset --hard`, `git reset
   <ref>` que mova branch, `git checkout <ref>` de mudança de branch, `git
   stash`, `git clean` → recusa ANTES de executar, erro tipado
   GIT_GUARD_RESET_PROIBIDO (stdout da tool: {"ok":false,...}), sem matar a
   run. `git checkout -- <arquivo>` (restore de arquivo) e `git reset` de
   UNSTAGE (sem --hard, sem ref) continuam permitidos. Log da recusa no trail.
2. PROVA OBRIGATÓRIA no veredito: quando o contrato declarar stop de veredito
   (ex.: marcador SHIP-OK/XP-OK), o harness só aceita o veredito como OK se o
   ÚLTIMO turno rodou o comando de prova declarado no contrato com saída
   contendo o esperado (ex.: "0 falhas"). Implementação mínima: convenção
   `## Prova mecanica` no contrato com linhas `cmd ...` + `expect ...`; o
   harness executa e confere ANTES de emitir veredito positivo; prova falha →
   veredito tipado PROVA_FALHOU. Sem a seção, comportamento atual (não quebra
   contratos antigos).
3. Testes: tests/test_worker_guard.py — (a) reset --hard recusado com erro
   tipado; (b) checkout de arquivo permitido; (c) veredito OK com prova verde;
   (d) prova vermelha → PROVA_FALHOU; (e) contrato sem seção = comportamento
   antigo. Rode a suíte do harness como worker.
4. RELATORIO-RD-WORKER-GUARD-01.md com marcador WORKER-GUARD-OK + contagem da
   suíte. Commit worker com o ID no subject; git add restrito.

## Regras de escrita (GB-FORCA-ESCRITA-01)

- Write direto no destino; leitura com code_slice (nunca insistir na Read);
  payload nunca na linha de comando; sem git reset/checkout de branch/stash/
  clean NESTA missão (o guard é código novo, não execução); sem tocar em
  routing/bridge.

## Stops Vermelhos na baseline (NÃO corrija as stops)

```harness-stop
cmd cd /home/worker/wt-RD-WORKER-GUARD && test -f RELATORIO-RD-WORKER-GUARD-01.md
cmd cd /home/worker/wt-RD-WORKER-GUARD && grep -q -F 'WORKER-GUARD-OK' RELATORIO-RD-WORKER-GUARD-01.md
cmd cd /home/worker/wt-RD-WORKER-GUARD && grep -q -F 'GIT_GUARD_RESET_PROIBIDO' harness.py
```
