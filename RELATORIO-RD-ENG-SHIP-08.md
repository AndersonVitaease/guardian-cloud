# RELATORIO RD-ENG-SHIP-08

## Veredito: SHIP-FALHOU

## Corpo da resposta
{"error":"INPUT_INVALID"}

## Detalhes
- Comando: bash tools-bash/release_pipeline.sh pipeline 1696e9baff935bb1a390c2784b9975dd1282f84f
- Wrapper HTTP ok:true, mas corpo contém error INPUT_INVALID → job NÃO enfileirado.
- Sem poll; sem rollback, conforme contrato.
