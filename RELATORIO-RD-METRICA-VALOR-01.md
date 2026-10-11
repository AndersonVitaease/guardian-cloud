# RELATORIO RD-METRICA-VALOR-01

## Escopo
Bloco "valor" no passo 4 do fecho (missao_fechar.sh): destravou/destravou_ids do
ROADMAP.md (env ROADMAP_PATH, default /opt/mission-events/ROADMAP.md), custo_usd e
turnos de /tmp/resumo-<ID>.json, computed_at ISO. Best-effort: erro tipado
(ROADMAP_AUSENTE / RESUMO_AUSENTE) sem derrubar o fecho (exit 0).

## Prova de logica pura (python3 -c, tabela em memoria)
Tabela com 3 linhas, 2 citando RD-EXEMPLO-01 -> extracao via split("|") indice 1:
`VALOR-OK 2 ['RD-B', 'RD-C']` (exit 0).

## Suite
- tests/test_fecho.py: PASS (exit 0).
- tests/test_ledger_missao.py: FALHA PRE-EXISTENTE no baseline -
  `ModuleNotFoundError: No module named 'scripts'` (test exige PYTHONPATH=.; com
  PYTHONPATH=. passa, exit 0). Nao relacionada a mudanca.

## Commits
- 11798554 RD-METRICA-VALOR-01: bloco valor no passo 4 do ledger

VALOR-OK
