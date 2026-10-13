# RELATORIO-SPIKE-DESK-CONN-01

## Pergunta
O conector desktop (futuro app Windows) pode expor tools da máquina local ao Guardian
via padrão REVERSO (conector disca para fora, registra tools, `tools/call` desce até
a máquina local) sobre o gateway MCP atual?

## Verdict
VALIDATED — a prova E2E hermética passou integralmente
(`SPIKE-DESK-CONN-01-PROVA-OK`).

## O que foi construído (throwaway, stdlib apenas, `spike/`)
- `spike/gateway.js` — mini-gateway Node (http stdlib): `/mcp` com JSON-RPC 2.0,
  Bearer token e erros tipados `MCP_SEM_TOKEN`/`MCP_TOKEN_INVALIDO`/
  `MCP_TOOL_DESCONHECIDA`; rotas de conector (`/conector/registrar|poll|responder|bye`)
  com registro dinâmico por tenant, long-poll de 1s, correlação por id de chamada,
  timeout 5s → `CONECTOR_OFFLINE`, watchdog 3s → tool sai do `tools/list`.
- `spike/conector.py` — falso app desktop (Python stdlib): disca para fora, registra
  `proc_list` (ps) e `echo_local`; encerra com SIGTERM respondendo `bye`.
- `spike/prova-SPIKE-DESK-CONN-01.py` — sobe gateway + conector em portas dinâmicas,
  valida: tools/list contém as 2 tools; call proc_list retorna saída de ps;
  call echo_local("x") → "LOCAL: x"; token inválido → MCP_TOKEN_INVALIDO;
  conector morto → CONECTOR_OFFLINE e tool some do tools/list.

## Resultados da prova
```
OK tools/list: ['proc_list', 'echo_local']
OK proc_list (amostra):       1 systemd
OK echo_local
OK MCP_TOKEN_INVALIDO
OK CONECTOR_OFFLINE + tools/list limpa
SPIKE-DESK-CONN-01-PROVA-OK
```

## Surpresas
- O padrão reverso é uma camada de roteamento sobre o gateway, não uma reescrita:
  o contrato `/mcp` permanece idêntico; só a resolução da tool muda.

## Recomendação para o build real
- WebSocket real (push imediato, ping/pong para queda) com long-poll como fallback.
- Registro dinâmico no `mcp-gateway.js` real: registry por tenant preenchido no
  handshake WS; `tools/list` faz merge server-side + registry; `tools/call` remota
  enfileira no WS com timeout e erro tipado `CONECTOR_OFFLINE`.
- Token próprio de escopo "desktop" para o canal do conector.

## Stops
Todos os stop-conditions verificados: arquivos presentes, sintaxe OK (`node --check`,
`py_compile`), prova OK, README com `## Verdict`, relatório na raiz, commit com a
mensagem exigida e worktree limpo.