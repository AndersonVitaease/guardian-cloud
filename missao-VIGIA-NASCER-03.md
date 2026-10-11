# MISSÃO VIGIA-NASCER-03 — gatilho do aviso de nascimento no despacho (continuação 01)

CONTINUAÇÃO de VIGIA-NASCER-01 (PASS). Falta a LIGAÇÃO: o `vigia_run.py` emite o evento `inicio` no `/tmp/vigia-<ID>.jsonl` (provado ao vivo hoje), mas NINGUÉM consome — o aviso de nascimento nunca chega ao chat. A morte já chega (canal do mission-ops). Worktree real: `/home/worker/wt-VIGIA-NASCER-01` (branch `rd-vigia-nascer-01`).

## Problema
O operador quer: missão nasce → aviso "🛰️ NASCEU" chega no chat; missão morre → aviso com veredito. O par nascendo/morrendo com a missão.

## MAPA (harness-s2/scripts, branch rd-vigia-nascer-01)
- `despachar_missao.py` — roda como ROOT; após o spawn bem-sucedido (onde obtém `pane` e `run_dir`, procure "espelho: espera o run dir nascer") é o ponto de gatilho.
- Bearer do gateway: arquivo em `/opt/eng-mcp-release-data/credentials/hermes-notify-api-key` (600 root:root — legível pelo despachar que roda como root; NÃO hardcode no repo, leia via env `HERMES_NOTIFY_BEARER_FILE` com default esse caminho — no CONTRATO cite apenas a variável).
- Endpoint: `POST http://127.0.0.1:8642/v1/chat/completions` (X-Hermes-Session-Id gh-notifications; body {"model":"hermes","messages":[...]}). Prova de vida: o supervisor entregou avisos por esse canal hoje.
- `scripts/vigia_run.py` — já emite `inicio` com horario_brt/unit/tab.

## Entregas
1. Em `despachar_missao.py`, após o spawn OK: POST do aviso de nascimento ao gateway (texto "🛰️ NASCEU: missão <ID> em voo — aba <tab>, seed <seed>, budget <budget>"). Chamada com timeout 5s, best-effort: qualquer falha (sem bearer, rota offline) = log no stderr e NÃO falha o despacho (fail-open; JSON de saída da tool ganha campo "aviso_nascimento":"ok|falho").
2. helper reutilizável `scripts/notify_hermes.sh` (bash puro, JSON 1-linha, exit 0 sempre, falha tipada SEM_BEARER/ROTA_OFFLINE) que lê o texto de stdin e faz o POST — usado pelo despachar e reutilizável pelo supervisor.
3. Testes herméticos: servidor HTTP de mentira em tempdir (socket) — verifica payload (tem ID/seed/budget), timeout, sem bearer → SEM_BEARER, exit 0 sempre.
4. Prova E2E: `prova-VIGIA-NASCER-03.py` — sobe server de mentira, aponta env para ele, executa o helper com texto de nascimento, afirma POST recebido com o texto; marcador `VIGIA-NASCER-03-PROVA-OK` no .out >200 bytes.
5. O aviso de MORTE não é seu escopo (já chega pelo canal do mission-ops) — não duplique.

## Regras
- Commits `VIGIA-NASCER-03:`. Sem sudo. Sem cat/head/ls/grep -r (leitura por code_slice/grep -n). Sem git reset/checkout/stash/clean. Sem internet (o server de mentira é local).
- NÃO hardcode bearer/segredos; só env.

## Stops
```harness-stop
cmd cd /home/worker/wt-VIGIA-NASCER-01 && python3 -m pytest tests/test_notify_hermes.py -q
cmd cd /home/worker/wt-VIGIA-NASCER-01 && python3 scripts/prova-VIGIA-NASCER-03.py
cmd cd /home/worker/wt-VIGIA-NASCER-01 && test $(stat -c%s scripts/prova-VIGIA-NASCER-03.out 2>/dev/null || echo 0) -gt 200
cmd cd /home/worker/wt-VIGIA-NASCER-01 && git log --format=%s -1 | grep -q -F 'VIGIA-NASCER-03'
cmd cd /home/worker/wt-VIGIA-NASCER-01 && test -z "$(git status -s -- .)"
```
