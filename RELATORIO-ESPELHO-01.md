# RELATORIO-ESPELHO-01

ESPELHO-01-OK

## O que foi entregue

1. **scripts/espelho.sh** — agente bash da casa de despacho com espelho ao vivo no herdr.
   - `set -euo pipefail`; saída sempre em JSON de 1 linha; nunca morre calado.
   - Uso: `espelho.sh <ID> <arquivo-prompt> [--profile despachante]`
   - Fluxo implementado:
     1. `herdr tab create --label "MISSAO:<ID>" --cwd /home/worker` — tab_id e workspace_id extraídos do JSON via `scripts/_espelho_parse.py` (evita `python3 -c` inline).
     2. `herdr pane list --workspace <ws>` — pane_id da aba nova localizado pelo `tab_id`.
     3. Injeção via `herdr pane send-text` + `send-keys Return` do comando:
        `env HOME=/home/worker /home/worker/bin/hermes chat -q --profile <perfil> "$(cat <arquivo-prompt>)"; echo ESPELHO-EXIT-$?`
        (prefixo `sudo -u worker` só quando o script roda como root; como worker, sudo pede senha e o comando roda direto).
     4. Liveness honesta: `herdr pane wait-output --regex 'ESPELHO-EXIT-[0-9]+' --timeout 7200000`. Regex exige dígito para não casar com o eco do próprio comando. Estado do espelho gravado em `<dir>/<ID>.espelho.json` (tab_id, pane_id, workspace_id, status, timestamps).
     5. No marker: código extraído de `herdr pane read` (0=PASS, outro=FAIL), aba fechada com `herdr tab close`, e POST `/api/notify` no Guardian (`http://127.0.0.1:8140/api/notify`) com `{missionId, veredito, custoUsd:null, ms, link:"herdr:MISSAO:<ID>"}`; token lido de `/home/worker/guardian-app/.env` se existir. Falha de notify (ex. NOTIFY_401 anônimo) é registrada no JSON final mas não quebra o fluxo.
     6. Erros tipados: `TAB_CREATE_FAILED`, `SEND_TEXT_FAILED`, `WAIT_TIMEOUT`, `NOTIFY_*`.
   - `bash -n` limpo (verificado).

2. **tests/test_espelho.sh** — teste hermético: cria aba `TESTE-ESPELHO-<ts>` no herdr real, send-text `echo ESPELHO-EXIT-0`, wait-output verde, extrai código 0, fecha a aba, e prova JSON `ok:true` do espelho.sh com prompt trivial. Última linha `RESUMO: 0 falhas`. `bash -n` limpo (verificado).

3. **scripts/_espelho_parse.py** — helpers de parsing JSON (create/pane/wscreate) usados por ambos.

## Verificação

- `bash -n` limpo nos dois scripts (executado, OK).
- Shape do JSON de `tab create` confirmado contra saída real do herdr 0.9.1 (mesma estrutura de `workspace create`: `result.tab.tab_id` + `result.tab.workspace_id`).
- Servidor herdr 0.9.1 iniciado e responde ao CLI.

## Limitação honesta

Neste ambiente não há sessão herdr TUI anexada (o TUI exige tty e o servidor headless descarta workspaces criados por CLI imediatamente — "no active workspace"). Portanto o teste hermético completo não pôde passar verde aqui; ele deve rodar na sessão mission-ops (`test-harness`) onde há workspace ativo — a mesma condição em que `despachar.sh` opera. A lógica de parsing foi validada contra JSONs reais do herdr.

## Regras respeitadas

- Nada aplicado em /opt; nenhum git reset/checkout/stash/clean; nenhum sudo além do prefixo condicional do comando do worker; nenhuma escrita em /root; nenhum segredo impresso; nenhuma missão real despachada.

## Commit subject

ESPELHO-01: espelho.sh — despacho com aba ao vivo no herdr
