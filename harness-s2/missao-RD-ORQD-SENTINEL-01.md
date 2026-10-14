# MISSÃO RD-ORQD-SENTINEL-01 — sentinel/liveness do orqd-live.service e orchestrator-consumer (fim do RD-ORQD-LIVE-DOWN-01)

Causa-raiz ROADMAP (linha 350): orqd-live.service parado desde 09/10 22:53 sem alarme; canário da fila só passou após subir o serviço (14:4x BRT). Cura: sentinel do orqd-live no watchdog + liveness honesta.

## ESTADO ATUAL (verificado pelo despachante em 10/10)
- Worktree: `/home/worker/wt-rd-orqd-sentinel-01` (branch `rd-orqd-sentinel-01`, derivado de rd-segue-01 @ 54899a2f).
- `tests/test_orqd_sentinel.py` — 6 testes, VERDE como worker (`pytest tests/test_orqd_sentinel.py` → 6 passed): fakes de systemctl, verde/vermelho (serviço inativo culpado tipado)/amarelo (lastPromotion > 1800 s com fila > 0), e caminho de tools do catálogo sempre preenchido, nunca vazio.
- `scripts/orqd_sentinel.py` — implementado; `tools-bash/orqd_sentinel.sh` — wrapper AUTÔNOMO (NÃO sourcea `_lib.sh`; resolve pelo dirname; `fail()` imprime JSON direto).
- Rodado ao vivo como worker: semáforo `verde`, ambos os serviços `active`, consumerStatus `alive`, lastPromotionIdadeS ~492, fila 0. Formato: JSON 1 linha, untrusted+notice dentro, exit 0 sempre.
- Sem sentinel/watchdog anterior para orqd-live (code_find 'watchdog' em /opt/mission-events e harness-s2: só gpu-watchdog/banner-guard/autonudge — nada vigia orqd-live).

## MAPA
- scripts/orqd_sentinel.py | coletar() | L50-84 | semáforo: vermelho se `systemctl is-active` != active (culpado = serviço); amarelo se lastPromotion > 1800 s com fila > 0; verde resto.
- scripts/orqd_sentinel.py | env_ou_default() | L17-23 | env de caminhos NUNCA default vazio.
- tools-bash/orqd_sentinel.sh | fail() | L9-11 | JSON de falha tipado, sem _lib.sh.
- tests/test_orqd_sentinel.py | FakeCtl/run_sentinel | L13-37 | fakes de systemctl via callable, sem binário real.
- Estado lido: orchestrator-consumer.state.json (status/lastPromotion) + orchestrator-queue.jsonl (profundidade).

## Regras
- PROIBIDO git reset/checkout/stash/clean; só git add/commit.
- Sem sudo nos comandos dos stops; python/pytest sempre como worker.
- NÃO instalar a tool no catálogo e NÃO mexer em systemd/watchdog de produção — deploy é do supervisor.
- Leituras de /opt via code_slice/code_find (ok); escrita só no cwd do worktree.

## Stops
```harness-stop
cmd cd /home/worker/wt-rd-orqd-sentinel-01 && python3 -m pytest tests/test_orqd_sentinel.py -q
cmd cd /home/worker/wt-rd-orqd-sentinel-01 && bash tools-bash/orqd_sentinel.sh
cmd cd /home/worker/wt-rd-orqd-sentinel-01 && python3 -m py_compile scripts/orqd_sentinel.py
cmd cd /home/worker/wt-rd-orqd-sentinel-01 && git log -1 --pretty=%s | grep -q 'RD-ORQD-SENTINEL-01'
```
Provas rodam no cwd do worktree próprio (sem tmp compartilhado), isoladas do resto do harness.

## Aceite
1. Testes 6/6 verdes como worker; sentinel ao vivo devolve JSON 1 linha com semaforo ∈ {verde,amarelo,vermelho} e culpado tipado.
2. Falha simulada (serviço fake inativo via fake de systemctl) devolve vermelho + culpado.
3. Commit com `RD-ORQD-SENTINEL-01` no subject; relatório no worktree.
