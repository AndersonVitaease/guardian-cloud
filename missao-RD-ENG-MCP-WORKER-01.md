# MISSÃO RD-ENG-MCP-WORKER-01 — canal oficial worker→release runner + retomada do deploy

Fonte: ordem operator 11/10 ~20:47 BRT ("autorizado, faça na sequência que você
determinar"); destrava o deployJobId a7f4e6e2-8fe2-4581-822b-94cbb23006b4
(enfileirado desde 20:42 BRT) e dá ao worker o caminho SHIP para sempre.

## Contexto (mapa cravado)

- O release runner oficial (eng-mcp-release-runner.service) é chamado por canal
  Unix socket oficial; o container eng-mcp roda em network host com bind de
  /opt/eng-mcp-release-data/run (docker inspect memoryos-eng-mcp — mounts).
- O harness dá ao worker tools Bash governadas por catálogo: harness.py ~L302-320
  (TOOLS_BASH_DIR default /opt/mission-events/tools-bash; build_tools(); catálogo
  tools.json = lista {name, command} — comandos argv-safe, sem shell).
- O worker NÃO pode chamar MCP engmcp-local (comprovado na RD-ENG-SHIP-01) nem
  docker/shell direto no container. O que falta: UMA tool bash governada que fale
  o canal oficial do runner.

## Tarefa

1. Neste worktree (tools-bash/): crie release_pipeline.sh — wrapper argv-safe do
   canal oficial do runner: `curl --unix-socket <SOCKET> -X POST /v1/release -d
   <json>` com operation permitida por allowlist (status, test, pipeline com
   deployJobId), timeout e saída JSON 1 linha; SOCKET resolvido por env
   RELEASE_RUNNER_SOCKET com default /opt/eng-mcp-release-data/run/<nome do
   socket> — DESCOBRIR o nome real do socket com file_peek/code_find no diretório
   (o runner roda no host: procure também em
   /opt/mission-events/tools-bash/_lib*.sh e no doc do plugin se precisar do
   padrão de chamada usado pelo supervisor).
2. Registre a tool no catálogo local tools.json do worktree (name:
   release_pipeline, command: release_pipeline.sh) e escreva test
   test_release_pipeline.sh com a paridade do padrão dos testes irmãos
   (test_*.sh): prova de allowlist (operação fora da lista → erro tipado), prova
   de timeout, prova de JSON bem-formado. SEM chamar o runner real — mock via
   socket fake local (socat/python http.server unix) se necessário.
3. Escreva missao_apply.md curto dizendo ao supervisor qual arquivo copiar para
   /opt/mission-events/tools-bash (via mission_apply) — APLICAÇÃO é do supervisor.
4. Se o socket não for alcançável pelo worker (permission denied), reporte o erro
   verbatim e o veredito vira CANAL-BLOQUEADO (honesto) — não invente sucesso.

## Regras de escrita (GB-FORCA-ESCRITA-01)

- Escrita direta no destino (Write), NUNCA .tmp/.sh + mv/cp; nada de código em /tmp.
- Todo stop roda `cd /home/worker/wt-RD-QUEUE-INODE-01 &&` primeiro.
- Sem cat/head/tail/ls/find/grep -oE/sed -i/awk soltos: code_find/code_slice/
  file_peek, grep -n COM PIPE, python3 para JSON.
- Máximo 3 linhas de ferramenta por turno.
- Commit como worker com o ID no subject; git add restrito; NUNCA git
  reset/checkout/stash/clean; merge/fecho/deploy é do supervisor.

## Stops (condições de parada)

```harness-stop
cmd cd /home/worker/wt-RD-QUEUE-INODE-01 && test -f RELATORIO-RD-ENG-MCP-WORKER-01.md
cmd cd /home/worker/wt-RD-QUEUE-INODE-01 && grep -q -F 'RD-ENG-MCP-WORKER-01' RELATORIO-RD-ENG-MCP-WORKER-01.md
cmd cd /home/worker/wt-RD-QUEUE-INODE-01 && grep -q -E 'CANAL-OK|CANAL-BLOQUEADO' RELATORIO-RD-ENG-MCP-WORKER-01.md
cmd cd /home/worker/wt-RD-QUEUE-INODE-01 && bash tools-bash/test_release_pipeline.sh 2>&1 | grep -q 'PASS\|OK'
```
