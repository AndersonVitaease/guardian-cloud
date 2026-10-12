# MISSÃO RD-ENG-SHIP-07 — SHIP do M1-GATE (tool sincronizada no worktree)

Fonte: continuação da SHIP-06 — causa da falha eliminada: a tool bash governada
release_pipeline.sh agora EXISTE neste worktree (branch sincronizada com
rd-segue-01, suíte 6/6 provada pelo supervisor 00:08 BRT).

## Contexto

Produção roda 22f073b2 (deploy PASS, smoke PASS). Alvo: HEAD
1696e9baff935bb1a390c2784b9975dd1282f84f (BASE44-DECOUPLE-01, inclui o
RD-SUPGUARD-M1-GATE).

## Tarefa

1. Como worker, a partir deste worktree, invoque:
   bash tools-bash/release_pipeline.sh pipeline 1696e9baff935bb1a390c2784b9975dd1282f84f
2. Acompanhe: bash tools-bash/release_pipeline.sh status (máx 3 leituras por
   turno de trabalho real entre elas) até deployStatus PASS + smokeStatus PASS +
   rollbackRequired false OU erro tipado real (reporte o código exato).
3. NÃO faça rollback por conta própria.

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
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && test -f RELATORIO-RD-ENG-SHIP-07.md
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && grep -q -F 'RD-ENG-SHIP-07' RELATORIO-RD-ENG-SHIP-07.md
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && grep -q -E 'SHIP-OK|SHIP-FALHOU' RELATORIO-RD-ENG-SHIP-07.md
```
SHIP-OK = deployStatus PASS + smokeStatus PASS no release 1696e9ba.
