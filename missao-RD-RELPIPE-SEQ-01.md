# MISSÃO RD-RELPIPE-SEQ-01 — wrapper release_pipeline orquestra a sequência do runner

Fonte: continuação da RD-ENG-SHIP-08 (INPUT_INVALID cravado: o runner NÃO tem a
operação "pipeline" — aceita test/build/candidate/deploy/status/rollback passo a
passo; a orquestração mora na camada MCP).

## Contexto

A tool bash governada release_pipeline.sh (neste worktree, tools-bash/) hoje manda
uma ÚNICA chamada com operation "pipeline" — o runner recusa com INPUT_INVALID.

## MAPA (arquivo:linha)

- tools-bash/release_pipeline.sh:47-53 — case dos payloads (o pipeline falso está aqui)
- tools-bash/release_pipeline.sh:55-63 — curl POST /v1/release no socket oficial
- tools-bash/release_pipeline.sh:29-40 — modos commit/jobId (argv 2)
- eng-mcp/src/tools.ts:314-330 (leitura no checkout /opt/memoryos, SÓ LEITURA via
  code_slice) — runOfficialReleasePipeline: sequência oficial = test → build →
  candidate → deploy, cada passo com {operation:<passo>, commit:<sha>} quando
  pinned; retomada usa jobId; falha de um passo encerra (evidence por passo)
- tools-bash/test_release_pipeline.sh — suíte 6/6 a estender

## Tarefa

1. release_pipeline.sh: nova suboperação `pipeline <commitSha40>` que ORQUESTRA a
   sequência oficial em bash (curl + python3 -c para extrair jobId do corpo de
   cada passo): test → build → candidate → deploy, cada chamada com
   {operation:<passo>, commit:<sha>}; entre test e build NÃO há espera longa —
   o runner responde sincronamente por passo (o test demora ~2min: timeout da
   chamada test deve ser elevado, env RELEASE_PIPELINE_TIMEOUT_TEST default 240);
   qualquer passo com httpStatus fora de 2xx OU body.error → saia com o erro
   tipado do corpo + o passo (formato: {"ok":false,"step":"build","error":...}).
   Modo retomada (pipeline <jobId-uuid>) permanece como está.
   Modos status/test individuais permanecem.
2. Estenda test_release_pipeline.sh: mock socket fake com as 4 respostas
   encadeadas (prova da sequência completa + ordem dos passos + parada no 1º
   erro). Mantenha as provas antigas passando.
3. Rode a suíte (bash tools-bash/test_release_pipeline.sh) — TODA verde.
4. Escreva RELATORIO-RD-RELPIPE-SEQ-01.md com marker RELPIPE-SEQ-OK e o output
   real da suíte.

## Regras de escrita (GB-FORCA-ESCRITA-01)

- Escrita direta no destino (Write), NUNCA .tmp/.sh + mv/cp; nada em /tmp.
- Todo stop roda `cd /home/worker/wt-RD-QUEUE-INODE-01 &&` primeiro.
- Sem cat/head/tail/ls/find/grep -oE/sed -i/awk soltos: code_find/code_slice/
  file_peek, grep -n COM PIPE, python3 para JSON.
- Máximo 3 linhas de ferramenta por turno.
- Commit como worker com o ID no subject; git add restrito; NUNCA git
  reset/checkout/stash/clean; merge/fecho/deploy em produção é do supervisor.

## Stops (condições de parada)

```harness-stop
cmd cd /home/worker/wt-RD-QUEUE-INODE-01 && test -f RELATORIO-RD-RELPIPE-SEQ-01.md
cmd cd /home/worker/wt-RD-QUEUE-INODE-01 && grep -q -F 'RELPIPE-SEQ-OK' RELATORIO-RD-RELPIPE-SEQ-01.md
cmd cd /home/worker/wt-RD-QUEUE-INODE-01 && bash tools-bash/test_release_pipeline.sh 2>&1 | grep -q 'RESUMO: PASS=.* FAIL=0'
```
