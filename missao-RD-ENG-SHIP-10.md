# MISSÃO RD-ENG-SHIP-10 — SHIP do M1-GATE (tool real, sequência oficial, limpeza do stub)

Fonte: continuação SEQ-04/SHIP-09. A tool release_pipeline FOI REESCRITA pelo
supervisor com o contrato REAL do runner (POST /v1/release no unix socket, corpo
flat; o modo `pipeline <sha>` orquestra test→build→candidate→deploy com parada
tipada STEP_<PASSO>_FALHOU). A suíte antiga test_release_pipeline.sh testava um
contrato REST inventado (BASE_URL localhost:8080) — está obsoleta e vermelha.

## MAPA (arquivo:linha, branch rd-rd-eng-ship-01 sincronizada em 4cd645bb)

- tools-bash/release_pipeline.sh:29-40 — modos pipeline (commit 40-hex via argv 2)
- tools-bash/release_pipeline.sh:47-79 — sequência oficial test→build→candidate→deploy
  (payload flat por passo no socket oficial; parada STEP_<PASSO>_FALHOU)
- tools-bash/test_release_pipeline.sh:1-64 — suíte obsoleta (contrato REST
  inventado BASE_URL localhost:8080) — a remover pela missão
- Referência do comportamento real: /opt/memoryos/eng-mcp/src/tools.ts:322-340
  (runOfficialReleasePipeline)

## Tarefa (nesta ordem)

1. Remova tools-bash/test_release_pipeline.sh (git rm; obsoleto — testava
   contrato que não existe no runner).
2. Como worker, invoque: bash tools-bash/release_pipeline.sh pipeline
   1696e9baff935bb1a390c2784b9975dd1282f84f
   - A tool roda os 4 passos oficiais no socket; qualquer passo fora de 2xx
     retorna STEP_<PASSO>_FALHOU com o corpo — reporte verbatim.
3. Poll de status (a cada ~45s): bash tools-bash/release_pipeline.sh status —
   até currentCommitSha == 1696e9baff935bb1a390c2784b9975dd1282f84f. NUNCA
   conclua SHIP-OK com currentCommitSha diferente (lição SHIP-07).
4. RELATORIO-RD-ENG-SHIP-10.md: marcador SHIP-OK (só com currentCommitSha igual
   ao alvo + deployStatus PASS + smokeStatus PASS) ou SHIP-FALHOU (erro tipado
   verbatim + o corpo da resposta). Sem rollback por conta própria.
5. Commit worker com o ID no subject (git add: relatório + remoção da suíte).

## Stops Vermelhos na baseline (NÃO corrija as stops)

```harness-stop
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && test -f RELATORIO-RD-ENG-SHIP-10.md
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && grep -q -F 'SHIP-OK' RELATORIO-RD-ENG-SHIP-10.md
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && grep -q -F '1696e9baff935bb1a390c2784b9975dd1282f84f' RELATORIO-RD-ENG-SHIP-10.md
```
