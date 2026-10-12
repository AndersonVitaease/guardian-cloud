# MISSÃO RD-ENG-SHIP-06 — SHIP do M1-GATE (invocação correta da tool)

Fonte: continuação da RD-ENG-SHIP-04 (SHIP-FALHOU: "release_pipeline: not found"
exit 127 — o nome solto não está no PATH do worker; a invocação correta é
bash + caminho completo, como a RD-ENG-MCP-WORKER-01 provou nos seus testes).

## Contexto

A tool governada existe no ambiente do worker (catálogo tools.json do
TOOLS_BASH_DIR do harness) e foi provada 6/6. Produção roda 22f073b2 (PASS).
Alvo: HEAD 1696e9baff935bb1a390c2784b9975dd1282f84f (BASE44-DECOUPLE-01,
inclui o RD-SUPGUARD-M1-GATE).

## Tarefa

1. Como worker, invoque com caminho completo a partir da env do harness:
   bash "$TOOLS_BASH_DIR"/release_pipeline.sh pipeline 1696e9baff935bb1a390c2784b9975dd1282f84f
2. Acompanhe com: bash "$TOOLS_BASH_DIR"/release_pipeline.sh status
   (máx 3 leituras por turno de trabalho real entre elas) até deployStatus PASS
   + smokeStatus PASS + rollbackRequired false OU erro tipado real.
3. NÃO faça rollback; em falha tipada reporte o código exato (veredito
   SHIP-FALHOU).
4. Se a env TOOLS_BASH_DIR não existir, use o caminho relativo do SEU catálogo
   conforme a prova da WORKER-01 e documente qual usou.

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
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && test -f RELATORIO-RD-ENG-SHIP-06.md
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && grep -q -F 'RD-ENG-SHIP-06' RELATORIO-RD-ENG-SHIP-06.md
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && grep -q -E 'SHIP-OK|SHIP-FALHOU' RELATORIO-RD-ENG-SHIP-06.md
```
SHIP-OK = deployStatus PASS + smokeStatus PASS no release 1696e9ba.
