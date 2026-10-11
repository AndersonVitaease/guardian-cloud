# MISSÃO RD-ENG-SHIP-01 — retomar e provar o deploy do eng-mcp (pipeline oficial)

Fonte: ordem operator 11/10 20:44 BRT (aprovação do SHIP em chat; supervisor deve
DELEGAR, nunca executar — conduta fixa).

## Contexto

O supervisor iniciou engineering.release.pipeline para o commit
22f073b23fea895f9ebbae845fd5fc760becf414 (branch BASE44-DECOUPLE-01 em /opt/memoryos;
contém os 2 merges do dia: RD-ORCH-TEMPLATE-STOPS-01R3 e RD-SANIDADE-TESTS-01R3).
Status real no momento da entrega: operation test PASS (1986 tests, 1933 passed,
0 failed, 104s), build PASS (imagem eng-mcp-candidate:commit-22f073b2...),
candidate PASS (150 tools validadas), operation deploy ACEITO e ENFILEIRADO —
deployJobId: a7f4e6e2-8fe2-4581-822b-94cbb23006b4. O pipeline parou ali: a próxima
chamada é engineering.release.pipeline com esse deployJobId (orientação do runner:
"Call engineering.release.pipeline with this deployJobId after reconnecting").

## Tarefa

1. Retome o pipeline: chame a tool MCP engineering_release_pipeline com
   deployJobId=a7f4e6e2-8fe2-4581-822b-94cbb23006b4 (e acknowledgeRelease=true).
   Ela é determinística e allowlisted — sua chamada É o caminho oficial; NÃO use
   docker/shell/curl direto no container (proibido).
2. Verifique o deploy: a mesma resposta traz evidence com operation deploy
   (converged, catalogVersion, toolCount, productionImage, smokeStatus). Confirme
   que catalogVersion subiu para eng-mcp-tools-v153 (ou a versão pós-merge) e que
   o toolCount esperado (150 + tools novas) bate com o catálogo.
3. Se o deploy falhar em qualquer step: NÃO faça rollback por conta própria —
   chame engineering_release_pipeline apenas em modo de leitura/estado (ou
   engineering_vps_reconcile) para capturar o estado real, e reporte o código
   tipado de falha. Rollback oficial só com ordem do operator.
4. Repita a leitura do estado até convergir ou falhar tipado (sem loop de
   polling: no máximo 3 leituras espaçadas por trabalho real entre elas).

## Regras de escrita (GB-FORCA-ESCRITA-01)

- Escrita em arquivo: direto no destino (Write), NUNCA .tmp/.sh + mv/cp.
- Todo stop roda `cd /home/worker/wt-RD-ENG-SHIP-01 &&` primeiro.
- Sem cat/head/tail/ls/find/grep -oE/sed -i/awk soltos: use code_find/code_slice/
  file_peek, grep -n COM PIPE, python3 para JSON.
- Máximo 3 linhas de ferramenta por turno.
- Commit como worker com o ID no subject; NUNCA git reset/checkout/stash/clean;
  merge/fecho é do supervisor.

## MAPA (fontes cravadas)

- deployJobId alvo: a7f4e6e2-8fe2-4581-822b-94cbb23006b4 (evidence do supervisor
  11/10 20:42 BRT — operation deploy httpStatus 202, status queued)
- commit alvo: 22f073b23fea895f9ebbae845fd5fc760becf414 (BASE44-DECOUPLE-01, /opt/memoryos)
- tool MCP: engineering_release_pipeline (MCP engmcp-local, catálogo v152)

## Stops (condições de parada)

```harness-stop
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && test -f RELATORIO-RD-ENG-SHIP-01.md
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && grep -q -F 'RD-ENG-SHIP-01' RELATORIO-RD-ENG-SHIP-01.md
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && grep -q -F 'a7f4e6e2-8fe2-4581-822b-94cbb23006b4' RELATORIO-RD-ENG-SHIP-01.md
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && grep -q -E 'SHIP-OK|SHIP-FALHOU' RELATORIO-RD-ENG-SHIP-01.md
```

SHIP-OK = converged true + smoke PASS; SHIP-FALHOU = qualquer step com falha tipada
real (relate o código exato e o estado do container anterior).
