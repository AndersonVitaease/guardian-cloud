# RELATORIO-GB-DESP-CLEAN-01

## Entregável
- `scripts/despachar_missao.py`: `verificar_unit_com_aba(unit)` (unit ativa sem pane viva no herdr → `systemctl stop` + fail tipado `UNIT_SEM_ABA`), chamada em todos os caminhos de saída (UNIT_JA_ATIVA, pré-spawn, pós-spawn, avisos); `limpar_orfaos(mid)` no início de todo despacho (ledger `running_sem_resumo` sem unit viva → `archive-ledger-<id>-<ts>.json` + espelho `.espelho.pousado.json` removido; missão com unit viva intocada); campo novo `aba_verificada: true` na saída.
- `prova-GB-DESP-CLEAN-01.py`: prova hermética (herdr/systemctl fakes em tmpdir, env overrides, sem sudo/rede).

## Prova
(a) unit ativa sem pane → recusa `UNIT_SEM_ABA` + unit parada ✓
(b) ledger órfão arquivado + espelho removido ✓
(c) despacho normal (dry-run) ok ✓
Saída: `GB-DESP-CLEAN-01-PROVA-OK`.

## Stops
py_compile ok; prova ok; relatório ok; commit com subject exigido; worktree limpo.