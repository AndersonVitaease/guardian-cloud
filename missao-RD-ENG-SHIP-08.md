# MISSÃO RD-ENG-SHIP-08 — SHIP do M1-GATE com verificação de CORPO e currentCommitSha

Fonte: continuação da SHIP-07 — o ok:true do wrapper é só HTTP; o corpo da resposta
(e o currentCommitSha do release) é que decide.

## Contexto

Produção: 22f073b2 (deployStatus PASS, smoke PASS). Alvo:
1696e9baff935bb1a390c2784b9975dd1282f84f (BASE44-DECOUPLE-01, com o
RD-SUPGUARD-M1-GATE). Nenhum job do alvo consta no estado do runner até agora.

## Tarefa

1. Como worker, a partir deste worktree:
   bash tools-bash/release_pipeline.sh pipeline 1696e9baff935bb1a390c2784b9975dd1282f84f
2. CAPTURE O CORPO completo da resposta e registre-o VERBATIM no relatório
   (campo "## Corpo da resposta"). O que decide:
   - se body contém accepted:true e/ou jobId → job enfileirado; vá ao passo 3;
   - se body contém error (ex.: INPUT_INVALID, ...) → veredito SHIP-FALHOU com o
     erro verbatim (não rode mais nada).
3. Poll: bash tools-bash/release_pipeline.sh status — SHIP-OK SÓ quando
   currentCommitSha == 1696e9baff935bb1a390c2784b9975dd1282f84f E deployStatus
   PASS E smokeStatus PASS. (deployStatus PASS sozinho é o release ANTIGO — não
   vale.) Máx 3 leituras por turno de trabalho real entre elas.
4. NÃO faça rollback; em falha tipada reporte o código e pare.

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
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && test -f RELATORIO-RD-ENG-SHIP-08.md
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && grep -q -F 'RD-ENG-SHIP-08' RELATORIO-RD-ENG-SHIP-08.md
cmd cd /home/worker/wt-RD-ENG-SHIP-01 && grep -q -E 'SHIP-OK|SHIP-FALHOU' RELATORIO-RD-ENG-SHIP-08.md
```
SHIP-OK = currentCommitSha 1696e9ba + deployStatus PASS + smokeStatus PASS.
