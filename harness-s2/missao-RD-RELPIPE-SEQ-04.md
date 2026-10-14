# MISSÃO RD-RELPIPE-SEQ-04 — sequência test→build→candidate→deploy no wrapper

Fonte: continuação SEQ-01/02/03 (INPUT_INVALID: o runner não tem "pipeline").

## ORDEM DE EXECUÇÃO (obedeça na ordem, sem leitura extra)

1º TURNO — ESCREVA (Write direto, sem ler nada antes):
  a) tools-bash/release_pipeline.sh — acrescente, para `pipeline <commitSha40>`:
     loop dos passos test → build → candidate → deploy, payload por passo
     {"operation":"<passo>","commit":"<sha>"} (flat), parando no 1º passo com
     httpStatus fora de 2xx → erro tipado STEP_<PASSO>_FALHOU com o corpo.
     Env CURL_BIN (default curl); teste com stub injetado. Mantenha status/
     test/jobId funcionando (contrato atual em release_pipeline.sh:29-63).
  b) tools-bash/test_release_pipeline.sh — 4 testes novos via stub curl
     (CURL_BIN apontando para fixture): 2xx no passo segue; não-2xx para com
     STEP_<PASSO>_FALHOU; ordem test→build→candidate→deploy respeitada.
2º TURNO — RODE: bash tools-bash/test_release_pipeline.sh (como worker).
3º TURNO — RELATÓRIO: RELATORIO-RD-RELPIPE-SEQ-04.md com marcador RELPIPE-SEQ-OK
  e as contagens reais da suíte.
4º TURNO — COMMIT worker (ID no subject), git add restrito aos 3 arquivos.

Proibições: NÃO use Read (dá erro); NÃO rode code_slice/code_find mais de 2x
por arquivo; NÃO coloque payload de runner na linha de comando Bash; sem git
reset/checkout/stash/clean; se algo sair do roteiro, escreva a dificuldade no
relatório e termine com o que tem — vagueio custa FAIL.

## Stops Vermelhos na baseline (NÃO corrija as stops)

```harness-stop
cmd cd /home/worker/wt-RD-QUEUE-INODE-01 && grep -q -F 'STEP_DEPLOY_FALHOU' tools-bash/release_pipeline.sh
cmd cd /home/worker/wt-RD-QUEUE-INODE-01 && grep -q -F 'CURL_BIN' tools-bash/test_release_pipeline.sh
cmd cd /home/worker/wt-RD-QUEUE-INODE-01 && test -f RELATORIO-RD-RELPIPE-SEQ-04.md && grep -q -F 'RELPIPE-SEQ-OK' RELATORIO-RD-RELPIPE-SEQ-04.md
```
