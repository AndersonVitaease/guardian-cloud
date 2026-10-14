# RELATÓRIO RD-ENG-SHIP-02 — SHIP do M1-GATE (deploy do eng-mcp)

## Veredito: SHIP-FALHOU

## Contexto
- Alvo: commit 1696e9ba (BASE44-DECOUPLE-01, /opt/memoryos), SHA completo resolvido via python3/git rev-parse: `1696e9baff935bb1a390c2784b9975dd1282f84f`.
- Canal: tool bash governada `release_pipeline` (/opt/mission-events/tools-bash/release_pipeline.sh), operações allowlist: status | test | pipeline; pipeline exige deployJobId (argv 2, UUID).

## Ações executadas (como worker, sem operatorOrder)
1. `release_pipeline.sh pipeline <uuid4>` (deployJobId b0b66e2c-f5fe-4448-a5b6-471afee16a9d e 231f818d-873a-465b-a822-20d036abbceb) → resposta: `{"error":"INPUT_INVALID"}`.
2. `release_pipeline.sh pipeline 1696e9baff935bb1a390c2784b9975dd1282f84f` (SHA 40-hex como deployJobId) → resposta: `{"error":"INPUT_INVALID"}` (2 tentativas).
3. `release_pipeline.sh status` (3 leituras, dentro do limite) → success:true, exitCode 0; estado do runner mostra testSourceHash 6800aa05..., testImageId sha256:d523c18d..., expectedToolCount 150 — canal operante, mas nenhum job de pipeline aceito.

## Erro tipado real
- `INPUT_INVALID` retornado pelo release runner em TODAS as chamadas `pipeline` (com UUID e com SHA). Não é erro do wrapper (ok:true, HTTP ok); é o runner rejeitando o payload. O contrato do wrapper não lista INPUT_INVALID entre seus motivos tipados (BAD_ARGS/BAD_OPERATION/BAD_DEPLOY_JOB_ID/SOCKET_MISSING/SOCKET_UNREACHABLE/TIMEOUT/HTTP_<code>/BAD_RESPONSE), mas é o erro real observado do backend.

## Estado final
- deployStatus: NÃO EXECUTADO (pipeline nunca iniciado — INPUT_INVALID).
- smokeStatus: NÃO EXECUTADO.
- rollbackRequired: false (nenhum deploy ocorreu; rollback NÃO executado, conforme regra 3).

## Conclusão
SHIP-FALHOU: o pipeline do commit 1696e9ba não foi disparado; o release runner rejeita todas as invocações `pipeline` com INPUT_INVALID. Nenhum rollback executado. Necessária intervenção do supervisor para corrigir o contrato de entrada do runner (formato de deployJobId esperado) antes de nova tentativa.