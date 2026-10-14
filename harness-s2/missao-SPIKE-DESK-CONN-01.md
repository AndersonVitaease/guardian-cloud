# MISSÃO SPIKE-DESK-CONN-01 — Spike: conector desktop com conexão reversa no gateway MCP

## Pergunta de factibilidade
O conector desktop do usuário (futuro app Windows) precisa expor tools da MÁQUINA LOCAL
ao Guardian. O gateway MCP atual (`mcp-gateway.js` no guardian-app, GB-MCP-EXT-01) é
INBOUND: só serve tools definidas server-side. Este spike valida o padrão REVERSO:
conector disca PARA FORA, registra tools, e um `tools/call` desce até a máquina local.

## Tudo aqui é THROWAWAY (spike) — código simples, hardcode, zero dependências externas
Diretório `spike/` no worktree. NÃO tocar guardian-app, /mcp de produção, nada fora do
worktree. Portas dinâmicas acima de 20000, nunca 8140/8113/8103.

## Componentes a construir (stdlib apenas: node http + python http/urllib)
1. `spike/gateway.js` — mini-gateway Node (stdlib http):
   - POST /mcp: JSON-RPC 2.0 (initialize, tools/list, tools/call) — espelha o contrato do
     mcp-gateway.js real: auth Bearer por token, erros tipados MCP_SEM_TOKEN,
     MCP_TOKEN_INVALIDO, MCP_TOOL_DESCONHECIDA.
   - Registro dinâmico: quando um conector conecta (ver item 2), as tools dele entram no
     tools/list daquele tenant; tools/call de tool remota é REPASSADA ao conector e a
     resposta volta. Conector caiu → tool sai do tools/list (sem pendurar o call: erro
     tipado CONECTOR_OFFLINE).
2. `spike/conector.py` — FALSO app desktop (Python stdlib), roda na MESMA VPS mas no
   papel do Windows: disca para fora (long-poll de 1s no gateway — NÃO precisa de WS,
   long-poll serve para o spike), registra 2 tools:
   - `proc_list`: roda `ps -eo pid,comm --no-headers | head -20` e devolve texto.
   - `echo_local <texto>`: devolve o texto prefixado com `LOCAL:`.
   - Para cancelar: só encerra ao receber SIGTERM (gateway repõe o long-poll na hora).
3. `spike/prova-SPIKE-DESK-CONN-01.py` — prova E2E hermética:
   - sobe gateway + conector, gera 2 tokens (tenant A válido, token B inválido);
   - GIVEN token A, WHEN tools/list THEN contém `proc_list` e `echo_local`;
   - GIVEN token A, WHEN tools/call proc_list THEN resultado contém saída de ps;
   - GIVEN token A, WHEN tools/call echo_local("x") THEN "LOCAL: x";
   - GIVEN token B, WHEN qualquer chamada THEN MCP_TOKEN_INVALIDO;
   - GIVEN conector morto (SIGTERM), WHEN tools/call THEN CONECTOR_OFFLINE e
     proc_list NÃO aparece mais no tools/list;
   - marca final `print('SPIKE-DESK-CONN-01-PROVA-OK')`.

## REGRA ANTI-VAGUEIO
Comando falhou 2× → NÃO repita o mesmo comando; `ls` e adapte. Escrita de arquivo:
`cd /home/worker/wt-SPIKE-DESK-CONN-01 && python3 - <<'EOF' ... EOF` (heredoc).
Write/Edit com path absoluto PROIBIDO.

## Entregáveis
- `spike/README.md` com veredito no formato do spike (VALIDATED / PARTIAL / INVALIDATED,
  o que funcionou, o que não, surpresas, recomendação para o build real — ex.: long-poll
  vs WebSocket real, onde o registro dinâmico entra no mcp-gateway.js real).
- `RELATORIO-SPIKE-DESK-CONN-01.md` na raiz do worktree.

## Stops
```harness-stop
cmd cd /home/worker/wt-SPIKE-DESK-CONN-01 && test -f spike/gateway.js && test -f spike/conector.py && test -f spike/prova-SPIKE-DESK-CONN-01.py
cmd cd /home/worker/wt-SPIKE-DESK-CONN-01 && node --check spike/gateway.js && python3 -m py_compile spike/conector.py
cmd cd /home/worker/wt-SPIKE-DESK-CONN-01 && python3 spike/prova-SPIKE-DESK-CONN-01.py 2>&1 | grep -q -F 'SPIKE-DESK-CONN-01-PROVA-OK'
cmd cd /home/worker/wt-SPIKE-DESK-CONN-01 && grep -q -F '## Verdict' spike/README.md && test -s RELATORIO-SPIKE-DESK-CONN-01.md
cmd cd /home/worker/wt-SPIKE-DESK-CONN-01 && test "$(git log -1 --format=%s)" = "SPIKE-DESK-CONN-01: spike conector desktop conexao reversa no gateway MCP (gateway.js + conector.py + prova E2E)"
cmd cd /home/worker/wt-SPIKE-DESK-CONN-01 && test -z "$(git status --porcelain)"
```

## MAPA (fontes consultadas)
- arquivo mcp-gateway.js no worktree da missão de gateway MCP — contrato JSON-RPC 2.0
  + tokens + erros tipados a espelhar no spike (REFERÊNCIA, não editar).
- o relatório da missão de gateway MCP — formato das mensagens de erro.

## Regras
- Budget US$0,20. Prova em portas dinâmicas; sem sudo; sem tocar produção.
