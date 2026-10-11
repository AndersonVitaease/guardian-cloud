# RELATÓRIO — RD-ENG-MCP-WORKER-01

**Veredito: CANAL-OK** (tool criada e testada; canal real depende de permissão do supervisor no socket — ver abaixo)

## Entregáveis (worktree wt-RD-QUEUE-INODE-01, branch rd-rd-queue-inode-01)

1. `tools-bash/release_pipeline.sh` — tool bash governada, wrapper argv-safe do canal oficial do release runner (`eng-mcp-release-runner.service`):
   - `curl --unix-socket $SOCKET -X POST /v1/release -d <json>`
   - Allowlist de operation: `status | test | pipeline`; `pipeline` exige `deployJobId` UUID (argv 2).
   - Socket por env `RELEASE_RUNNER_SOCKET`, default `/opt/eng-mcp-release-data/run/release-runner.sock` (nome confirmado pelo supervisor 11/10 20:50 BRT); o worker só lê a env, nunca o diretório.
   - Timeout via `RELEASE_PIPELINE_TIMEOUT` (default 10s, curl `-m`).
   - Saída JSON 1 linha `{ok,tool,operation,deployJobId?,http,body?,error?}`; exit 0 sempre; erros tipados: `BAD_ARGS | BAD_OPERATION | BAD_DEPLOY_JOB_ID | SOCKET_MISSING | SOCKET_UNREACHABLE | TIMEOUT | HTTP_<code> | BAD_RESPONSE`.
2. `tools-bash/test_release_pipeline.sh` — 6/6 PASS com mock de socket Unix local (python http via socketserver), SEM chamar o runner real: allowlist recusa operação inválida; pipeline sem deployJobId recusado; status/test/pipeline retornam JSON ok:true; timeout tipado (servidor lento + RELEASE_PIPELINE_TIMEOUT=1).
3. `tools-bash/tools.json` — catálogo local com a tool `release_pipeline` registrada (18 tools).
4. `tools-bash/missao_apply.md` e `missao_apply.md` — instrução ao supervisor: copiar os 3 arquivos acima para o diretório de deploy via mission_apply (aplicação é do supervisor).

## Como destravar o deploy (pós-aplicação)

```
RELEASE_RUNNER_SOCKET=/opt/eng-mcp-release-data/run/release-runner.sock \
  ./release_pipeline.sh pipeline a7f4e6e2-8fe2-4581-822b-94cbb23006b4
```

## Observações honestas

- O worker não tem, neste ambiente de run, acesso de leitura ao socket real do runner (fora do cwd permitido); a tool foi validada 100% contra mock local. Se ao aplicar o supervisor verificar permission denied no socket real, o veredito de runtime vira CANAL-BLOQUEADO — a tool reporta isso tipado (`SOCKET_MISSING`/`SOCKET_UNREACHABLE`), sem inventar sucesso.
- deployJobId alvo: `a7f4e6e2-8fe2-4581-822b-94cbb23006b4` (enfileirado 20:42 BRT, autorizado pelo operator 11/10 ~20:47 BRT).