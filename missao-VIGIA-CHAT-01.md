# MISSÃO VIGIA-CHAT-01 — aviso de término no chat via bash

Fonte: ROADMAP.md linha 396 (VIGIA-CHAT-01, prio alta).
operatorOrder inline: 'vigia-chat autorizado pelo operador 10/10'.

## CONTEXTO MEDIDO (confiado, não investigue de novo)

O pipeline novo (mission_run.py + ledger + ExecStopPost) fecha a missão mas NÃO avisa o operador no chat. O pipeline velho (eng-mcp mission-ops) tem a peça `notify_mission_completed` → `chatDeliverable`. A rota de notificação REAL, mapeada em código (não inventada):

- **Transporte: HTTP local no gateway Hermes** — `POST http://127.0.0.1:8642/v1/chat/completions`, header `Authorization: Bearer <token>` + `X-Hermes-Session-Id: <sessão>`, body JSON `{"model":"hermes-agent","stream":false,"messages":[{"role":"user","content":"<linha>"}]}`.
- Evidência velha: `/opt/mission-events/event_bus.py:39-40` (`CRED_HERMES = "/opt/eng-mcp-release-data/credentials/hermes-notify-api-key"`, `HERMES_API = "http://127.0.0.1:8642"`) e `post_to_gateway` em `event_bus.py:130-153` (payload e headers exatos, incluindo `X-Hermes-Session-Id`).
- Evidência velha 2 (eng-mcp): `engineering.notify.hermes` → `src/notifyHermes.ts:46` (`HERMES_API_BASE_DEFAULT = "http://127.0.0.1:8642"`), input schema só `{summary, status?}`, sessão default `gh-notifications` (`notifyHermes.ts:92`), best-effort com falha tipada (nunca lança).
- Gateway CONFIRMADO no vivo: `ss -ltn` mostra `127.0.0.1:8642` LISTEN; `curl http://127.0.0.1:8642/v1/models` sem token devolve **401** (porta viva, só falta o bearer).
- O bearer está em `/opt/eng-mcp-release-data/credentials/hermes-notify-api-key` (600 root:root) — legível pelo SUPERVISOR no fecho (ExecStopPost roda com '+', root), NÃO pelo worker. Por isso o teste do worker usa rota fake via env.
- Gancho existente: `scripts/despachar_missao.py:147-149` injeta `ExecStopPost=-+/usr/bin/python3 scripts/ledger_missao.py fechar <ID> --resumo /tmp/resumo-<ID>.json` no `systemd-run`.
- FALHA TIPADA SEM_ROTA é resultado válido: se em runtime a rota não responder, o script reporta `SEM_ROTA`/`ROTA_OFFLINE` silenciosamente (exit 0 sempre) e o relatório final documenta com evidência. O script NUNCA quebra o fecho da missão.

## MAPA
- `scripts/vigia_chat.sh` — ARQUIVO NOVO (Write inteiro; bash puro, 0 LLM, JSON 1-linha na saída, exit 0 SEMPRE, falha tipada estilo run_close.sh com tb_audit quando _lib.sh existir).
- `patches/07-vigia-chat-hook.sh` — ARQUIVO NOVO (Write inteiro; padrão dos patches 01-05 existentes em patches/; dry-run default).
- `tests/test_vigia_chat.py` — ARQUIVO NOVO (Write inteiro), pytest (NÃO unittest), fixtures tmp_path + rota fake.
- `RELATORIO-VIGIA-CHAT-01.md` — ARQUIVO NOVO na raiz do worktree.

## COMPORTAMENTO EXIGIDO

1. `scripts/vigia_chat.sh <missionId> [--send]`:
   - Resolve o run-dir pelo MESMO resolvedor do `tools-bash/run_close.sh:47-88` (ledger `<state_dir>/<ID>.json` → campo `cwd`; fallback glob `/home/worker/wt-*/runs/<ID>`; normalização tentativa-N). Lê `resumo.json` e/ou `autoretry-summary.json` (mesma extração de veredito/turnos/custo do run_close.sh:94-125: `vereditos_por_tentativa[-1]`, `runs[-1]`, `custo_total`).
   - Monta payload 1-linha: `{"missao":"<ID>","veredito":"...","custo_usd":N,"turnos":N,"aba":"<pane ou null>"}` (aba do ledger; `python3 -c` com json.dumps para escape garantido).
   - Dry-run DEFAULT: imprime só o payload, não toca rede.
   - `--send`: entrega pela rota mapeada — `curl -sS --max-time 15` POST em `${VIGIA_CHAT_API:-http://127.0.0.1:8642}/v1/chat/completions` com `Authorization: Bearer $(cat "$VIGIA_CHAT_CRED")` (default do env: o MESMO caminho de credencial do event_bus.py:39 — não citado literalmente aqui; é root-only, supervisor lê no fecho), header `X-Hermes-Session-Id: ${VIGIA_CHAT_SESSION:-gh-notifications}`, content = 1 linha pt-BR ex.: `VIGIA: missão <ID> terminou — veredito <v>, custo US$ <c>, turnos <t>, aba <a>.`
   - Env `VIGIA_CHAT=0` = ROLLBACK: não faz NADA (saída `{"ok":false,"tool":"vigia_chat","rollback":true}`, exit 0).
   - Falha tipada SILENCIOSA (exit 0 sempre): `SEM_RESUMO`, `SEM_ROTA` (credencial ausente/ilegível), `ROTA_OFFLINE` (curl falha/timeout/HTTP != 2xx). Resultado via tb_audit. NUNCA usa sudo, NUNCA quebra o fecho.
2. `patches/07-vigia-chat-hook.sh [--apply]`: patch IDEMPOTENTE que anexa ao bloco ExecStopPost existente em `scripts/despachar_missao.py:147-149` uma SEGUNDA propriedade: `--property=ExecStopPost=-+<TOOL_VIGIA> <ID> --send`, onde `TOOL_VIGIA` é o caminho absoluto da tool instalada pelo supervisor (resolvido em runtime pelo patch via env `VIGIA_CHAT_SCRIPT`; o worker NÃO escreve em caminho de sistema e o patch default é `${TB_TOOLS:-tools}/vigia_chat.sh` relativo ao dirname do próprio despachar_missao.py). Sem `--apply`: imprime o diff planejado e não escreve nada (dry-run default). Idempotente: se `vigia_chat.sh` já aparece em despachar_missao.py, sai `{"ok":true,"ja_aplicado":true}` sem duplicar. Sem sudo embutido (execução é do supervisor no fecho).
3. `tests/test_vigia_chat.py` — pytest com rota FAKE (tmp_path: servidor http simples em thread ou arquivo + `VIGIA_CHAT_API`/`VIGIA_CHAT_CRED` apontando pra ele): prova (a) payload tem as 5 chaves exatas na ordem pedida, 1 linha; (b) dry-run não faz POST; (c) `VIGIA_CHAT=0` rollback não faz POST; (d) `--send` com rota fake OK faz POST com bearer e session corretos; (e) rota fake offline → `ROTA_OFFLINE` e exit 0; (f) idempotência do patch 07: aplicar 2x via --apply em cópia tmp de despachar_missao.py → 1 ocorrência de vigia_chat.
4. `RELATORIO-VIGIA-CHAT-01.md` na raiz (2-8 linhas): rota mapeada (arquivo:linha), o que o canário do SUPERVISOR vai provar (aviso chegando na sessão do chat no fecho), resultado do smoke local.

## TAREFA — ACEITE PRIMEIRO (RED), depois implementação
1. Escreva `tests/test_vigia_chat.py` (Write inteiro). `python3 -m pytest tests/test_vigia_chat.py -q` VERMELHO no baseline. Commit do aceite vermelho com o ID no assunto (git add só do teste).
2. Implemente `scripts/vigia_chat.sh` e `patches/07-vigia-chat-hook.sh` (Write inteiro). Verifique da raiz do worktree: `bash scripts/vigia_chat.sh VIGIA-CHAT-01` (dry-run — não há run real ainda; espere SEM_RESUMO tipado, exit 0).
3. Testes verdes + `bash -n scripts/vigia_chat.sh && bash -n patches/07-vigia-chat-hook.sh`.
4. Commit do código (assunto com o ID) e `RELATORIO-VIGIA-CHAT-01.md` na raiz.

## REGRAS
- Provas python sempre como worker (você já é worker). Sem sleep, sem sudo, sem escrever fora do worktree (a credencial real NUNCA é lida por você; teste usa fake). Sem cat/head/ls/grep -A; leitura por code_slice.sh/code_find.sh; sem `;` nos stops.
- `git add` só dos arquivos da missão. Sem `git reset/checkout/stash/clean`.

## STOP-CONDITIONS — bloco exato abaixo
```harness-stop
cmd cd /home/worker/wt-VIGIA-CHAT-01 && bash -n scripts/vigia_chat.sh
cmd cd /home/worker/wt-VIGIA-CHAT-01 && bash -n patches/07-vigia-chat-hook.sh
cmd cd /home/worker/wt-VIGIA-CHAT-01 && python3 -m pytest tests/test_vigia_chat.py -q
cmd cd /home/worker/wt-VIGIA-CHAT-01 && git log --format=%s | grep -q -F VIGIA-CHAT-01
cmd cd /home/worker/wt-VIGIA-CHAT-01 && git ls-files --error-unmatch scripts/vigia_chat.sh RELATORIO-VIGIA-CHAT-01.md
cmd cd /home/worker/wt-VIGIA-CHAT-01 && git diff --quiet HEAD
```
