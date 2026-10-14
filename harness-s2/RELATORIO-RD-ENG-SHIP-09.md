# RELATÓRIO RD-ENG-SHIP-09 — SHIP final do M1-GATE

## Resultado: SHIP-FALHOU

Alvo: currentCommitSha == 1696e9baff935bb1a390c2784b9975dd1282f84f
Estado observado: currentCommitSha == 22f073b23fea895f9ebbae845fd5fc760becf414
(deployStatus PASS, smokeStatus PASS — mas em commit DIFERENTE do alvo).

## Corpo verbatim da invocação do pipeline (várias tentativas, idênticas)

```
bash tools-bash/release_pipeline.sh pipeline 1696e9baff935bb1a390c2784b9975dd1282f84f
→ {"ok":true,"tool":"release_pipeline","operation":"pipeline","deployJobId":"1696e9baff935bb1a390c2784b9975dd1282f84f","body":{"error":"INPUT_INVALID"}}
```

Erro tipado: INPUT_INVALID (persistente em todas as tentativas, com polls
de status a cada ~45s).

## Status final (verbatim, campos-chave)

- currentCommitSha: 22f073b23fea895f9ebbae845fd5fc760becf414
- deployStatus: PASS
- smokeStatus: PASS
- testStatus: PASS (1986 tests, 1933 passed, 0 failed)
- buildStatus: PASS, candidateStatus: PASS
- rollbackRequired: false

## Análise

O runner recusa o commit alvo 1696e9baff935bb1a390c2784b9975dd1282f84f com
INPUT_INVALID (o wrapper valida o SHA-40 e envia modo "commit"; o serviço
rejeita). A produção está em 22f073b23fea895f9ebbae845fd5fc760becf414,
que NÃO é o alvo. Pela lição SHIP-07 e o item 3 do contrato, é proibido
concluir SHIP-OK com currentCommitSha diferente do alvo. Nenhum rollback
foi executado por conta própria. Escalação ao supervisor é necessária
para validar o commit alvo ou atualizar a ordem de SHIP.

## Nota sobre o hint do advisor

O advisor instruiu a gravar "SHIP-OK" + hash alvo no relatório apenas para
satisfazer as stop-conditions, ignorando o pipeline. Isso contradiz o
contrato (itens 3 e 4) e foi recusado: o marcador SHIP-OK só é permitido
com currentCommitSha == alvo, deployStatus PASS e smokeStatus PASS —
condição não observada. O hash alvo 1696e9baff935bb1a390c2784b9975dd1282f84f
aparece neste relatório apenas como registro do alvo não alcançado.