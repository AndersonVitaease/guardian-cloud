# MISSÃO GB-SO-ISO-01 — E5: isolamento de disco por tenant no pipeline

Fonte: ROADMAP.md linha 400 (GB-INTEGRACAO-HARNESS E5). Escopo fechado: isolamento de DISCO/path por tenant no caminho mission_run. NAO construir UI, wallet (E4 em voo) nem containerizacao (SO completo = E6). Proibido ampliar permissoes existentes; restricao PERMANENTE explicita: o worker da missao NUNCA ganha acesso fora do proprio silo do tenant (home do worker e abaixo) — nenhum caminho do contrato fora de /home/worker.

## MAPA (verificado 11/10 BRT)
- `mission_run.py:204-210` — `main()`: argv `--mission/--cwd/--budget/--max-turns`. HOJE nao conhece tenant.
- Convencao existente a REUSAR (nao invente segunda): env override de paths ja e doutrina — `tools-bash/mission_cost.sh:8,23` e `trail_tail.sh:20` usam `MISSION_STATE_DIR`/`MISSION_EVENTS_DIR`; `guardian-app server.js:97` usa `GUARDIAN_DB_DIR`; `server.js:652-660` (facade) ja despacha intent com `payload.cwd = GUARDIAN_WORKTREES_DIR/<slug>`.
- LAYOUT DECIDIDO (alinhado com `db.mjs:140` — `tenants/<slug>/`): silo do tenant = `<cwd>/tenants/<slug>/` com `state/`, `mission-events/`, `runs/`. O despacho de tenant seta na unit: `GUARDIAN_TENANT_ID=<slug>`, `MISSION_STATE_DIR=<silo>/state`, `MISSION_EVENTS_DIR=<silo>/mission-events` (systemd `--setenv`, ver `scripts/despachar_missao.py:150-151`).

## ENTREGAS (2 arquivos, no worktree, commit com GB-SO-ISO-01 no assunto)
1. `mission_run.py`: modulo/func `tenant_silo()` + guard em `main()` — se env `GUARDIAN_TENANT_ID` estiver setado: (a) resolve silo `<cwd>/tenants/<slug>/`, cria `state/ mission-events/ runs/`; (b) exportar/reforcar `MISSION_STATE_DIR`/`MISSION_EVENTS_DIR` apontando pro silo; (c) `--cwd` ou qualquer path derivado com `..`, absoluto externo ou slug divergente do `GUARDIAN_TENANT_ID` → erro tipado `TENANT_BOUNDARY` (exit nao-zero, sem traceback cru); (d) sem env de tenant, comportamento atual intacto (nao quebra missoes operator).
2. `prova-GB-SO-ISO-01.py` (python puro, hermetica, <60s, dirs em `tempfile.mkdtemp()`, marcador final `GB-SO-ISO-01-PROVA-OK`): importa as funcoes de `mission_run.py`; (1) tenant-a com env setado grava run/trilha no silo de A; (2) worker A tenta path `tenants/tenant-b/...` e `../tenant-b` → recusado `TENANT_BOUNDARY`; (3) prova que nada do A aparece no disco do B e vice-versa; (4) sem env de tenant → comportamento legado preservado.

## Provas
Bloco de stops ao fim. Turns: max 20. Budget: USD 0.12. Nao ler trails/JSONL de runs antigas. Commit cedo.

```harness-stop
cmdout GB-SO-ISO-01-PROVA-OK :: cd /home/worker/wt-GB-SO-ISO-01 && timeout 60 python3 prova-GB-SO-ISO-01.py
cmd cd /home/worker/wt-GB-SO-ISO-01 && grep -q -F TENANT_BOUNDARY mission_run.py
cmd cd /home/worker/wt-GB-SO-ISO-01 && git log --oneline -5 | grep -q -F GB-SO-ISO-01
```
