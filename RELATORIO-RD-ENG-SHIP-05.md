# RELATÓRIO RD-ENG-SHIP-05 — SHIP do M1-GATE

## Veredito: SHIP-FALHOU

## Invocação
- Tool: `release_pipeline` (catálogo tools.json do TOOLS_BASH_DIR do harness).
- Env `TOOLS_BASH_DIR` não definida no shell do worker (exit 127 nas tentativas com nome solto e com `$TOOLS_BASH_DIR`); usado o caminho completo do catálogo conforme prova da RD-ENG-MCP-WORKER-01:
  `bash /home/worker/harness-s2/tools-bash/release_pipeline.sh pipeline 1696e9baff935bb1a390c2784b9975dd1282f84f`

## Evidência
- `pipeline 1696e9baff935bb1a390c2784b9975dd1282f84f` →
  `{"ok":true,"tool":"release_pipeline","operation":"pipeline","deployJobId":"1696e9baff935bb1a390c2784b9975dd1282f84f","body":{"error":"INPUT_INVALID"}}`
- Erro tipado real do release runner: **INPUT_INVALID** — o deployJobId passado (commit SHA 1696e9baff935bb1a390c2784b9975dd1282f84f) não é um UUID válido; o contrato da tool exige `pipeline <deployJobId UUID>`.
- `status` (4 leituras) → success:true, exitCode 0; estado atual: deployStatus PASS, smokeStatus PASS, rollbackRequired false, mas para o release `eng-mcp-candidate:commit-22f073b23fea895f9ebbae845fd5fc760becf414` (produção 22f073b2), NÃO para o alvo 1696e9ba. Nenhum deploy do alvo foi iniciado.

## Conclusão
- deployStatus (alvo 1696e9ba): não iniciado (INPUT_INVALID no pipeline)
- smokeStatus (alvo 1696e9ba): não iniciado
- rollbackRequired: false (rollback NÃO executado, conforme contrato)
- O SHIP do alvo 1696e9baff935bb1a390c2784b9975dd1282f84f FALHOU com erro tipado `INPUT_INVALID`: o identificador do alvo é um SHA de commit, não um deployJobId UUID aceito pelo release runner. Produção permanece em 22f073b2 (PASS).