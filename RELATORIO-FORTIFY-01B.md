# RELATORIO-FORTIFY-01B

Entrega: fortify

## Entrega 1 — tests/test_bridge_golden.py (source-scan)
Asserts sobre `/opt/gpu-bridge/proxy.mjs` (skipTest se inacessível):
1. Nenhuma linha com `audit(` contém `model: ROLE_MODEL.worker`.
2. Nenhuma linha `message_start` contém `model: ROLE_MODEL.worker`.
3. `ESCADA_OK` honra `z-ai/glm-5.3`.
4. ≥2 ocorrências de `model: payload.model` em contextos audit/resp.

## Entrega 2 — evento `_config` no trail (harness.py)
- `run_mission` emite `{"turno":0,"tool":"_config","model":...,"escada":...,"vagueio":...,"budget_usd":...,"max_turns":...,"checkpoint_from":HARNESS_CHECKPOINT_FROM}` após resolver escada/vagueio.
- 1ª linha do pane via `_pane_line` com branch `tool == "_config"`: `[config] model=<m> escada=<e> vagueio=<v> budget=$<b>` — com suporte a `pane_prefix` (batch `[s<k>]`), corrigindo o teste de prefixo do batch.
- Teste: `tests/test_config_header.py` (bridge mockada, padrão test_escada.py).

## Validação
- `python3 -m pytest tests/ -q` → 329 passed.
- `python3 -m pytest tests/test_bridge_golden.py tests/test_config_header.py -q` → passed.
- Branch `FORTIFY-01B` criado; working tree limpa.
