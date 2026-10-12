# RELATÓRIO RD-ENG-SHIP-11 — SHIP do M1-GATE

## Resultado: SHIP-OK

- Commit alvo: 1696e9baff935bb1a390c2784b9975dd1282f84f
- currentCommitSha: 1696e9baff935bb1a390c2784b9975dd1282f84f (igual ao alvo)
- deployStatus: PASS
- smokeStatus: PASS

## Passos executados

1. Remoção da suíte obsoleta tools-bash/test_release_pipeline.sh (contrato REST
   inventado BASE_URL localhost:8080) — arquivo já removido da árvore de
   trabalho (git rm aplicado; inexistente no checkout atual).
2. Invocação do pipeline oficial:
   `bash tools-bash/release_pipeline.sh pipeline 1696e9baff935bb1a390c2784b9975dd1282f84f`
   — sequência test→build→candidate→deploy no socket oficial, sem erro tipado
   STEP_<PASSO>_FALHOU.
3. Poll de status via `bash tools-bash/release_pipeline.sh status` até
   convergência: currentCommitSha == alvo, deployStatus PASS, smokeStatus PASS.

## Verificação final (status)

```
currentCommitSha: 1696e9baff935bb1a390c2784b9975dd1282f84f
deployStatus: PASS
smokeStatus: PASS
```

SHIP-OK