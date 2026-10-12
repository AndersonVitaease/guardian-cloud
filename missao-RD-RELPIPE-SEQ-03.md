# MISSÃO RD-RELPIPE-SEQ-03 — wrapper release_pipeline orquestra a sequência oficial

Fonte: continuação da SHIP-08/SEQ-01/SEQ-02 (INPUT_INVALID: o runner NÃO tem a
operação "pipeline" — a sequência oficial é test → build → candidate → deploy,
com {commit} em cada passo; quem orquestra é a camada MCP, e agora o wrapper).

## MAPA (arquivo:linha)

- tools-bash/release_pipeline.sh:29-40 — modos pipeline (commit/jobId, argv 2)
- tools-bash/release_pipeline.sh:47-57 — payload atual (enviar por passo)
- tools-bash/release_pipeline.sh:59-63 — POST /v1/release no socket oficial
- tools-bash/test_release_pipeline.sh — suíte 6/6 (estende, nunca quebra)
- Referência de comportamento (só leitura, supervisor já provou):
  /opt/memoryos/eng-mcp/src/tools.ts:322-340 — runOfficialReleasePipeline:
  sequência test → build → candidate → deploy, cada passo com {commit},
  parada no primeiro passo com httpStatus fora de 2xx.

## Tarefa

1. Faça o wrapper aceitar `pipeline <commitSha40>` (só esse modo novo; o modo
   jobId de retomada mantém) e, para o modo commit, executar EM SEQUÊNCIA os
   4 passos oficiais: test, build, candidate, deploy — cada um com payload
   {"operation":"<passo>","commit":"<sha>"} no MESMO socket; parar no 1º passo
   com httpStatus fora de 2xx (erro tipado STEP_<PASSO>_FALHOU com o corpo).
2. Torno o curl INJETÁVEL: env CURL_BIN (default "curl"); os testes usam um
   stub de curl por script de fixture (sem socket, sem rede, sem timeout) —
   NADA de socket fake na suíte (lição SEQ-02: timeouts de 10s).
3. NUNCA coloque payload de runner na linha de comando Bash — o guard de
   consequência recusa (lição SEQ-02). Payload vive DENTRO do script; o teste
   só chama o script e um stub de curl com fixture.
4. Suíte nova: por passo (4 testes: 2xx segue, não-2xx para com STEP_*), mais
   os 6 testes existentes verdes. Rode como worker.
5. Relatório RELATORIO-RD-RELPIPE-SEQ-03.md (marcador RELPIPE-SEQ-OK), commit
   do worker com o ID no subject; git add restrito aos 2 arquivos + relatório.

## Regras de escrita (GB-FORCA-ESCRITA-01)

- Escreva direto no caminho destino (Write), NUNCA via tee/sed/caminho
  intermediário; sem git reset/checkout/stash/clean; commit com o ID no
  subject; git add restrito.

## Stops Vermelhos na baseline (NÃO corrija as stops)

```harness-stop
cmd cd /home/worker/wt-RD-QUEUE-INODE-01 && test -f RELATORIO-RD-RELPIPE-SEQ-03.md
cmd cd /home/worker/wt-RD-QUEUE-INODE-01 && grep -q -F 'RELPIPE-SEQ-OK' RELATORIO-RD-RELPIPE-SEQ-03.md
cmd cd /home/worker/wt-RD-QUEUE-INODE-01 && grep -q -F 'STEP_DEPLOY_FALHOU' tools-bash/release_pipeline.sh
```
