# MISSÃO ESCADA-EXPLORA-01 — Escada tambem em loop de exploracao: ao chegar na METADE do gatilho de vagueio sem entregavel, subir a run para ESCADA_MODEL (1x) antes de abortar por vagueio

## MAPA
- harness.py | ~12 linhas | No bloco 'VAGUEIO-01' de run_mission (apos vagueio_streak += 1 e vagueio_evid.append(...), ANTES do 'if vagueio_streak >= VAGUEIO_TRIGGER'): if escada and not escalada and vagueio_streak >= max(2, VAGUEIO_TRIGGER // 2): escalada = True; cost_pre_escada = ledger.cost; model_ativo = ESCADA_MODEL; emit({'turno': turn, 'tool': '_escada', 'de': model, 'para': ESCADA_MODEL, 'motivo': 'vagueio_meio', 'vagueio_streak': vagueio_streak, 'cum_usd': round(ledger.cost, 6)}); pane.write(f'escada | {model} -> {ESCADA_MODEL} | vagueio {vagueio_streak}x\n'); pane.flush(). Copie o padrao do bloco da escada por degeneracao (linhas ~1079-1087). O streak NAO zera ao escalar; o abort por vagueio continua valendo no gatilho cheio. Nao mude mais nada.

## Regras
- PROIBIDO git reset/checkout/stash/clean; só git add/commit.
- Checkpoint commit como worker ANTES das edições.
- Não toque em routing/bridge nem no dir de produção root-only.
- Sem sudo nos comandos dos stops.

## Stops
```harness-stop
cmd cd /home/worker/wt-ESCADA-EXPLORA-01 && python3 -m py_compile harness.py
cmd cd /home/worker/wt-ESCADA-EXPLORA-01 && grep -q -F 'vagueio_meio' harness.py
cmd cd /home/worker/wt-ESCADA-EXPLORA-01 && python3 -m unittest tests.test_vagueio tests.test_escada tests.test_nudge_fim 2>&1 | tail -1 | grep -q '^OK'
cmd cd /home/worker/wt-ESCADA-EXPLORA-01 && git diff --quiet HEAD -- harness.py
cmd cd /home/worker/wt-ESCADA-EXPLORA-01 && python3 -m unittest tests.test_vagueio tests.test_escada 2>&1 | tail -1 | grep -q '^OK'
cmd git log -1 --pretty=%s | grep -q 'ESCADA-EXPLORA-01'
```
