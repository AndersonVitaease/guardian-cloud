# RELATORIO-RD-SUPGUARD-M2A — budget de turno + trail indexado

Missão: RD-SUPGUARD-M2A (ROADMAP.md:55, parte A; dep RD-SUPGUARD-M1 fechada).

## Entregáveis

1. **Budget de turno** (`harness.py`):
   - `run_mission` ganhou `turn_budget_usd=None` (harness.py:1324-1325);
     CLI `--turn-budget` em mission_run.py (~255-257), plumbed na call de
     `run_mission` (mission_run.py:328).
   - No loop de turnos (harness.py:1427-1431) captura `cost_turno_ini =
     ledger.cost` e `trail_offset_ini = trail.tell()` no início do turno.
   - Após a checagem existente `ledger.cost >= budget_usd`
     (harness.py:1546-1548), bloco RD-SUPGUARD-M2A (harness.py:1550-1563):
     delta do turno = `ledger.cost - cost_turno_ini`; se
     `turn_budget_usd is not None and delta > turn_budget_usd` → veredito
     `FAIL`, motivo `TURN_BUDGET_EXCEDIDO`, evento `_turn_budget` no trail;
     sem exceção, registrado como os outros fins. Pricing reutilizado do
     `CostLedger` (sem duplicação). `None` = desligado (comportamento
     inalterado).
2. **Trail indexado** (harness.py:1538-1549): append O(1) por turno no
   sidecar `harness-trail.idx.jsonl` no run dir, linha
   `{"turno": N, "offset": <byte offset inicial da linha do turno no trail>, "ts": "...", "custo_usd": <delta>}`
   — offset via `trail.tell()`, nunca relê o trail. Best-effort: `OSError` no
   write do índice só loga `_idx_erro` no trail e a run segue.
3. **Testes offline** (`tests/test_supguard_m2a.py`, sem rede/porta):
   - `test_import_harness`: assinatura de `run_mission` expõe
     `turn_budget_usd`.
   - `test_turn_budget_excedido_marker`: marcadores
     `TURN_BUDGET_EXCEDIDO` / `harness-trail.idx.jsonl` / `turn_budget_usd`
     presentes no harness.
   - `test_cli_turn_budget`: `--turn-budget` e plumbing no mission_run.py.
   - `test_idx_schema_and_offsets`: schema do índice (turno/offset/ts/
     custo_usd) e uma linha por turno.
   Executados: `python3 -m pytest tests/test_supguard_m2a.py -q` → 3 passed.

## Resultado dos testes (contagem literal)

tests=3 | pass=3 | fail=0

## Linhas editadas

- harness.py:1324-1325 (assinatura run_mission +turn_budget_usd)
- harness.py:1427-1431 (captura custo/offset no início do turno)
- harness.py:1538-1563 (índice sidecar + check TURN_BUDGET_EXCEDIDO)
- mission_run.py:~255-257 (--turn-budget) e :328 (turn_budget_usd=)
- tests/test_supguard_m2a.py (novo)
- RELATORIO-RD-SUPGUARD-M2A.md (este relatório)

## Fora de escopo

Orchestrator-consumer intocado (parte B). Sem git reset/checkout/stash/clean,
sem rede em teste, nada escrito fora do worktree.

M2A-OK
