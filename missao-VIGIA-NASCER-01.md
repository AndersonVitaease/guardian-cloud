# MISSÃO VIGIA-NASCER-01 — aviso de nascimento de missão (nasce com aviso, morre com veredito)

Worktree real: `/home/worker/wt-VIGIA-NASCER-01` (branch `rd-vigia-nascer-01`). Contexto: o operador hoje só é avisado da MORTE de missão; quer aviso no NASCIMENTO, e o aviso deve "viver enquanto a missão vive" (par nascimento/morte 1:1). O transporte de aviso ao chat do operador é `POST http://127.0.0.1:8642/v1/chat/completions` com `Authorization: Bearer <key>` e `X-Hermes-Session-Id` — o bearer real fica em credencial root-only que o supervisor aplica depois: o worker NUNCA o lê e NUNCA chama a rota real. Tudo é testado com MOCK local.

## MAPA PRÉ-DIGERIDO
- `scripts/vigia_run.py` — roda junto com toda missão (spawn do despachar_missao.py ~L163-180), grava eventos JSONL em `/tmp/vigia-<ID>.jsonl`: `inicio`, `andamento`, `fim` (fim já dedupado pela VIGIA-DEDUPE-01: 1x por (veredito,tentativa)).
- `tools-bash/_lib.sh` — helpers existentes das tools (tb_emit estilo, JSON 1 linha).
- Produção viva: endpoint local na porta 8642 com credencial root-only — fora do alcance do worker; supervisor aplica e conecta depois do PASS.

## Entregas (NOVOS arquivos em `tools-bash/`)
1. `notify_missao.sh` — envia 1 aviso por chamada. Uso: `notify_missao.sh <arquivo-json-do-evento>` (o JSON é o evento do vigia: inicio/andamento/fim). Lê o bearer de `NOTIFY_BEARER_FILE` (env; o SUPERVISOR injeta o caminho real — você NUNCA lê paths do operador) e o endpoint de `NOTIFY_URL` (default `http://127.0.0.1:8642/v1/chat/completions`). Formata o summary: `inicio` → `🛰️ NASCEU: missao <id> — seed <seed> — budget <budget> (aba RUN:<id>#s<seed>)`; `fim` → `✅ MORREU: missao <id> — veredito <veredito> — custo US$<custo> — turnos <turnos>`; `andamento` → NÃO notifica (exit 0 silencioso). Sem bearer/sem rota → JSON `{ok:false,error:SEM_BEARER|ROTA_OFFLINE}` exit 0 (fail-open, nunca trava missão). Timeout de rede 5s.
2. `test_notify_missao.sh` — suíte com MOCK: sobe um `python3 -m http.server` custom (handler que captura o POST, porta dinâmica 9200-9399) como `NOTIFY_URL`; casos: inicio formata certo (contém NASCEU, id, seed), fim formata certo (contém MORREU, veredito, custo), andamento não chama a rede, sem bearer → SEM_BEARER, rota morta → ROTA_OFFLINE, nunca exit != 0.
3. `prova-VIGIA-NASCER-01.py` (em `scripts/`): fixture completa — mock server capturando POSTs, bearer fake em tempdir; grava eventos de inicio/fim/andamento em jsonl de tempdir, roda notify_missao.sh para cada, asserta exatamente 2 POSTs (1 nascimento + 1 morte), corpos com os textos esperados, e imprime `VIGIA-NASCER-01-PROVA-OK` na última linha.

## Regras
- Sem sudo, sem rede externa (mock local apenas), sem `cat/head/ls`. Estilo JSON 1 linha das tools.
- NÃO mexa em vigia_run.py, despachar_missao.py, mission_run.py (a fiação final é do supervisor).

```harness-stop
cmd cd /home/worker/wt-VIGIA-NASCER-01 && python3 -m pytest tools-bash/test_notify_missao.py -q
cmd cd /home/worker/wt-VIGIA-NASCER-01 && python3 scripts/prova-VIGIA-NASCER-01.py 2>&1 | tail -1 | grep -q -F 'VIGIA-NASCER-01-PROVA-OK'
cmd cd /home/worker/wt-VIGIA-NASCER-01 && git log --format=%s -1 | grep -q -F 'VIGIA-NASCER-01'
cmd cd /home/worker/wt-VIGIA-NASCER-01 && test $(stat -c%s scripts/prova-VIGIA-NASCER-01.out) -gt 200
cmd cd /home/worker/wt-VIGIA-NASCER-01 && test -z "$(git status -s -- tools-bash/ scripts/)"
```
