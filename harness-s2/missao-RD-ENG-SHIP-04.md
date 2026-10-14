# MISSÃO RD-ENG-SHIP-04 — SHIP do M1-GATE via tool governada (formato corrigido)

Fonte: continuação da RD-ENG-SHIP-03 (INPUT_INVALID) — formato do runner corrigido
na tool: contrato flat operation/jobId/commit (provado pela leitura de
eng-mcp/src/tools.ts:210-211).

## Contexto

A tool bash governada `release_pipeline` (no SEU catálogo) aceita:
- `release_pipeline pipeline <commitSha40>` — pipeline NOVO (envia {operation:"pipeline", commit:"<sha>"})
- `release_pipeline pipeline <deployJobId>` — retomada (envia {operation:"pipeline", jobId:"<uuid>"})

Produção roda 22f073b2 (smoke PASS). Alvo: HEAD
1696e9baff935bb1a390c2784b9975dd1282f84f (BASE44-DECOUPLE-01, inclui o
RD-SUPGUARD-M1-GATE).

## Tarefa

1. Como worker, chame: release_pipeline pipeline 1696e9baff935bb1a390c2784b9975dd1282f84f
2. Acompanhe com release_pipeline status (máx 3 leituras por turno de trabalho
   real entre elas) até: deployStatus PASS + smokeStatus PASS + rollbackRequired
   false OU erro tipado real.
3. NÃO faça rollback; em falha tipada reporte o código exato (veredito SHIP-FALHOU).

## Regras de escrita (GB-FORCA-ESCRITA-01)

- Escrita direta no destino (Write), NUNCA .tmp/.sh + mv/cp; nada em /tmp.
- Todo stop roda `cd /home/worker/wt-RD-ENG-SHIP-01 &&` primeiro.
- Sem cat/head/tail/ls/find/grep -oE/sed -i/awk soltos: code_find/code_slice/
  file_peek, grep -n COM PIPE, python3 para JSON.
- Máximo 3 linhas de ferramenta por turno.
- Commit como worker com o ID no subject; NUNCA git reset/checkout/stash/clean;
  merge/fecho é do supervisor.

## Stops (condições de parada)

```harness-stop
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && test -f RELATORIO-RD-ENG-SHIP-04.md
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && grep -q -F 'RD-ENG-SHIP-04' RELATORIO-RD-ENG-SHIP-04.md
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && grep -q -E 'SHIP-OK|SHIP-FALHOU' RELATORIO-RD-ENG-SHIP-04.md
```
SHIP-OK = deployStatus PASS + smokeStatus PASS no release 1696e9ba.
