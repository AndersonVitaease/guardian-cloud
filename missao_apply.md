# missao_apply — RD-ENG-MCP-WORKER-01

Copiar para o diretório de deploy do supervisor (via mission_apply) os 3 arquivos do worktree `wt-RD-QUEUE-INODE-01/tools-bash/`:

1. `tools-bash/release_pipeline.sh` — tool governada do canal oficial do release runner (curl --unix-socket, allowlist status|test|pipeline, timeout, JSON 1 linha).
2. `tools-bash/test_release_pipeline.sh` — testes (6/6 PASS, mock local, sem tocar o runner real).
3. `tools-bash/tools.json` — catálogo com a nova tool `release_pipeline` registrada.

Após aplicar, o worker pode destravar o deployJobId `a7f4e6e2-8fe2-4581-822b-94cbb23006b4` chamando:
`RELEASE_RUNNER_SOCKET=/opt/eng-mcp-release-data/run/release-runner.sock ./release_pipeline.sh pipeline a7f4e6e2-8fe2-4581-822b-94cbb23006b4`