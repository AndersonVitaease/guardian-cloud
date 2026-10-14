# SPIKE-DESK-CONN-01 — Conector desktop com conexão reversa no gateway MCP

## Verdict
VALIDATED

## O que funcionou
- Conector disca PARA FORA (long-poll 1s em `/conector/poll`), registra 2 tools
  (`proc_list`, `echo_local`) via `/conector/registrar` — sem porta de entrada aberta.
- `tools/list` do tenant reflete dinamicamente as tools registradas; conector caiu
  (SIGTERM/bye ou watchdog 3s sem poll) → tool some do `tools/list`.
- `tools/call` de tool remota é repassada ao conector (id de correlação) e a resposta
  volta pelo canal `/conector/responder`; timeout 5s → `CONECTOR_OFFLINE`.
- Contrato espelhado do mcp-gateway.js real: JSON-RPC 2.0, Bearer token,
  `MCP_SEM_TOKEN` / `MCP_TOKEN_INVALIDO` / `MCP_TOOL_DESCONHECIDA`.
- Prova E2E hermética (`prova-SPIKE-DESK-CONN-01.py`) cobre todos os cenários
  (list, call proc_list, call echo_local, token inválido, conector morto) e imprime
  `SPIKE-DESK-CONN-01-PROVA-OK`.

## O que não funcionou / limitações
- Long-poll de 1s adiciona latência média ~0,5s por call (aceitável para spike).
- Watchdog de 3s é heurístico; um poll em voo pode mascarar queda por até 1 ciclo.
- Sem autenticação do canal do conector além do mesmo token (spike, hardcode).

## Surpresas
- O padrão reverso cabe quase inteiro como camada de roteamento sobre o gateway
  existente: o `/mcp` não muda de contrato, só a resolução de tool muda de
  "handler server-side" para "fila pendente + resposta do conector".

## Recomendação para o build real
- **WebSocket real** em vez de long-poll: elimina latência média, dá push imediato
  de `tools/call` e detecção de queda por ping/pong (o long-poll serve como fallback).
- No `mcp-gateway.js` real, o registro dinâmico entra como um registry por tenant
  preenchido no handshake WS do conector; `tools/list` faz merge de tools
  server-side + tools do registry; `tools/call` consulta registry e, se remota,
  enfileira no WS do conector com timeout e erro tipado `CONECTOR_OFFLINE`.
- Autenticar o canal do conector com token próprio (escopo "desktop") e expirar
  registro se o WS cair >N segundos.