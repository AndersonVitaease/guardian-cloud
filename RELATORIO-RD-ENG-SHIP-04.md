# RELATORIO RD-ENG-SHIP-04 - SHIP do M1-GATE via tool governada

## Veredito: SHIP-FALHOU

## Comando executado
release_pipeline pipeline 1696e9baff935bb1a390c2784b9975dd1282f84f

## Resultado
- A tool release_pipeline NAO esta disponivel no ambiente deste worker: "release_pipeline: not found" (exit 127), reproduzido 2x no turno 1.
- Evidencia historica (RELATORIO-RD-ENG-SHIP-03.md, linha 5): a mesma chamada retornou {"ok":true,"tool":"release_pipeline","operation":"pipeline","deployJobId":"1696e9baff935bb1a390c2784b9975dd1282f84f","body":{"error":"INPUT_INVALID"}} (3x).
- Status (release_pipeline status, conforme relatorio anterior): producao permanece em 22f073b23fea895f9ebbae845fd5fc760becf414 (deployStatus PASS, smokeStatus PASS, rollbackRequired false - release ANTERIOR, nao o alvo).

## Conclusao
O ship do commit alvo 1696e9baff935bb1a390c2784b9975dd1282f84f NAO ocorreu. A tool governada release_pipeline nao e invocavel neste ambiente do worker (comando inexistente, exit 127), e a ultima evidencia registrada da chamada correta e o erro tipado INPUT_INVALID. Producao segue no release anterior 22f073b2... Nenhum rollback foi executado (conforme regra da missao).

Veredito final: SHIP-FALHOU - pipeline do alvo nao concluido; codigo de erro tipado observado: INPUT_INVALID; condicao atual do ambiente: tool ausente (release_pipeline: not found).
