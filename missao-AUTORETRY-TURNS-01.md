# MISSÃO AUTORETRY-TURNS-01 — --auto-retry sem --max-turns nao pode mais derrubar a unit com NoneType+int: usar default 30 turnos

## MAPA
- mission_run.py | ~3 linhas | No bloco 'if args.auto_retry > 0:' (linha ~229-233), na chamada rodar_com_retry troque max_turns=args.max_turns por max_turns=(args.max_turns if args.max_turns is not None else 30) # AUTORETRY-TURNS-01: default 30 (antes NoneType+int derrubava a unit). Nao mude mais nada. Maximo 2 turnos de leitura: o mapa acima basta.

## Regras
- PROIBIDO git reset/checkout/stash/clean; só git add/commit.
- Checkpoint commit como worker ANTES das edições.
- Não toque em routing/bridge nem no dir de produção root-only.
- Sem sudo nos comandos dos stops.

## Stops
```harness-stop
cmd cd /home/worker/wt-AUTORETRY-TURNS-01 && python3 -m py_compile mission_run.py
cmd cd /home/worker/wt-AUTORETRY-TURNS-01 && grep -q -F 'AUTORETRY-TURNS-01' mission_run.py
cmd cd /home/worker/wt-AUTORETRY-TURNS-01 && git diff --quiet HEAD -- mission_run.py
cmd cd /home/worker/wt-AUTORETRY-TURNS-01 && python3 -m py_compile mission_run.py
cmd git log -1 --pretty=%s | grep -q 'AUTORETRY-TURNS-01'
```
