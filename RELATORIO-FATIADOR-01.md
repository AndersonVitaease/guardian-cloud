# RELATÓRIO FATIADOR-01

Entrega: fatiador

## O que foi feito
- `scripts/fatiador.py`: parser de `## Entregas` (subseções numeradas → sub-contratos em `fatiador/<seed>/fatia-N.md`, cada um com mapa/contexto completo + bloco harness-stop global), `--dry-run`, orquestração sequencial via run_mission in-process (budget dividido, seed_base+N, checkpoint-chain com `estado.json` em FAIL e parada honesta), `--retomar <seed>` injetando `HARNESS_CHECKPOINT_FROM`, resumo agregado (veredito/custo por fatia + trail).
- `tests/test_fatiador.py`: 4 testes (geração de sub-contratos, orquestração com bridge mockada PASS/FAIL, retomar com checkpoint injetado, dry-run).
- Paridade total sem `--fatia`; harness.py intocado.

## Validação
- `python3 -m pytest tests/ -q` → 333 passed.
- `python3 scripts/fatiador.py --dry-run /opt/mission-events/missao-fatiador-selftest.md` → 3 fatias, exit 0.
- `ast.parse(scripts/fatiador.py)` → ok.
- `git status -s -- .` limpo (commit direto no master).