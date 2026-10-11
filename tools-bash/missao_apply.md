# missao_apply — RD-ENG-MCP-WORKER-01

Copiar para o diretório de deploy do supervisor (via mission_apply):

- `tools-bash/release_pipeline.sh` — wrapper argv-safe do canal oficial do release runner (allowlist status|test|pipeline, timeout, JSON 1 linha, erros tipados). Socket por env RELEASE_RUNNER_SOCKET, default /opt/eng-mcp-release-data/run/release-runner.sock.
- `tools-bash/test_release_pipeline.sh` — testes (6 PASS: allowlist, deployJobId obrigatório, status/test/pipeline no mock, timeout tipado). Não chama o runner real.
- `tools-bash/tools.json` — catálogo com a tool `release_pipeline` registrada.

Aplicação é do supervisor. A tool permite destravar o deployJobId a7f4e6e2-8fe2-4581-822b-94cbb23006b4 (op `pipeline`).