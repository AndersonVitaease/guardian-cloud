# RELATORIO RD-HARN-DEBUGINFRA-01

DEBUGINFRA-OK

## Entregas
- `--modo debug` em mission_run.py: janela crua de contexto turnos 12-40 (tool_results ate 12000 chars), sumario turnos 60-120, tool-results 4000-12000 chars; default off (no-op sem a flag).
- `--memoria <trail.jsonl>`: injeta bloco DIAGNOSTICO PREVIO no kickoff (ultimos vereditos, motivos, tool_results do trail anterior); ausente sem a flag.
- `scripts/debug_infra.py`: funcoes puras `janela_debug`, `sumario`, `diag_previo`.
- `tests/test_debug_infra.py`: hermetico, fixtures tmp — 9 passed.

## Uso
```
python3 mission_run.py --modo debug ...
python3 mission_run.py --memoria runs/<run>/harness-trail.jsonl ...
```

## Suíte
`python3 -m pytest tests/test_debug_infra.py -q` → 9 passed.
