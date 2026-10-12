# MISSÃO RD-ENG-SHIP-03 — SHIP do M1-GATE via tool governada (formato corrigido)

Fonte: continuação da RD-ENG-SHIP-02 (veredito interno SHIP-FALHOU por INPUT_INVALID
— formato de entrada corrigido pelo supervisor no mesmo script).

## Contexto

A tool bash governada `release_pipeline` (no SEU catálogo) agora aceita dois modos
corrigidos e provados (suíte 6/6):
- `release_pipeline pipeline <commitSha40>` — pipeline NOVO (envia
  commitSha + acknowledgeRelease:true)
- `release_pipeline pipeline <deployJobId>` — retomada de job enfileirado

Produção roda 22f073b2 (deploy 23:43 BRT, smoke PASS). Alvo: HEAD
1696e9baff935bb1a390c2784b9975dd1282f84f (BASE44-DECOUPLE-01, inclui o
RD-SUPGUARD-M1-GATE).

## Tarefa

1. Como worker, chame: release_pipeline pipeline
   1696e9baff935bb1a390c2784b9975dd1282f84f
2. A resposta pode ser assíncrona (job aceito/queued) — nesse caso chame
   release_pipeline status e acompanhe até: deployStatus PASS + smokeStatus PASS
   + rollbackRequired false OU erro tipado real. Máximo 3 leituras de status por
   turno de trabalho real entre elas (sem loop de polling).
3. NÃO faça rollback por conta própria; em falha tipada, reporte o código exato
   (veredito SHIP-FALHOU).
4. O deploy traz o gate de operatorOrder para produção: a missão em si é
   worker/missão registrada — seu canal não muda.

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
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && test -f RELATORIO-RD-ENG-SHIP-03.md
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && grep -q -F 'RD-ENG-SHIP-03' RELATORIO-RD-ENG-SHIP-03.md
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && grep -q -E 'SHIP-OK|SHIP-FALHOU' RELATORIO-RD-ENG-SHIP-03.md
```
SHIP-OK = deployStatus PASS + smokeStatus PASS no release 1696e9ba.
