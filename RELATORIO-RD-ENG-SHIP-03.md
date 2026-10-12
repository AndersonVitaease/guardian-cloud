# RELATORIO RD-ENG-SHIP-03 — SHIP do M1-GATE via tool governada

- Alvo: 1696e9baff935bb1a390c2784b9975dd1282f84f (BASE44-DECOUPLE-01)
- Comando: release_pipeline pipeline 1696e9baff935bb1a390c2784b9975dd1282f84f
- Resultado: {"ok":true,"tool":"release_pipeline","operation":"pipeline","deployJobId":"1696e9baff935bb1a390c2784b9975dd1282f84f","body":{"error":"INPUT_INVALID"}} (reproduzido 3x)
- Status (release_pipeline status): produção permanece em 22f073b23fea895f9ebbae845fd5fc760becf414 (deployStatus PASS, smokeStatus PASS, rollbackRequired false — release ANTERIOR, não o alvo).
- Nenhum job foi aceito/enfileirado para o commit alvo; erro tipado real: INPUT_INVALID.

## Veredito: SHIP-FALHOU (INPUT_INVALID no release 1696e9ba)

Deploy do commit alvo não concluído; rollback não executado (conforme contrato).