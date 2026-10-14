# RELATORIO-HARNESS-DAG-01

Entrega: despachante de DAG (spawner systemd-run respeitando deps topológicas).

## Continuação da run HARNESS-DAG-01 (seed 3927, FAIL por max_turns)

Insumo: run dir `/home/worker/harness-s2/runs/HARNESS-DAG-01/run-20261008-115756-seed3927-691999/`
(`scripts/despachante.py`, `tests/test_despachante.py`, 17 passed / 1 failed).

## Correção aplicada

`test_aguardar_politica_parar` expunha bug real: em `aguardar`, o early-return
`if politica_parou(plano): break` saía antes de os dependentes pendentes serem
marcados como `BLOQUEADA`. Fix em duas partes:
1. `politica_parou` agora bloqueia transitivamente (fixpoint): qualquer
   `PENDENTE` com dep em `POUSADA_FAIL`/`BLOQUEADA` vira `BLOQUEADA`.
2. No ramo de early-return de `aguardar`, `despachar(...)` é reavaliado antes
   do `break`, propagando `BLOQUEADA` antes de retornar (spawner chamado 1x).

## Provas

- `python3 -m pytest tests/test_despachante.py -q` → **18 passed**, exit 0.
- `python3 scripts/despachante.py --dry-run plano.json` → ordem topológica
  SC-1 → SC-2, SC-3 → SC-4 com comandos systemd-run, exit 0.

## Ordem do operator

1. Corrigir `test_aguardar_politica_parar` (bug de política FAIL/parar).
2. Suite completa verde (pytest, exit 0).
3. Prova viva do `--dry-run` com plano de exemplo respeitando deps.
4. Copiar `scripts/despachante.py` e `tests/test_despachante.py` para o repo
   `/home/worker/harness-s2` (scripts/, tests/) + este RELATORIO.
5. Commit como worker em branch `HARNESS-DAG-01`, sem push.

## Arquivos

- `scripts/despachante.py` — despachante (ler_plano, ordem_topologica,
  despachar, aguardar, politica_parou, resultado, CLI --dry-run).
- `tests/test_despachante.py` — 18 testes.
