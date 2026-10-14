# RELATORIO-RD-HARN-LINT-ENFORCE-01

Gate de lint bloqueante no despacho implementado (LINT_RECUSADO + VACUO_STOPS_VERDES) e testado; isolamento do teste novo corrigido (restore de os.geteuid/sys.argv) e guard root-skip em test_ledger_missao.py (chmod não bloqueia root).
Full suite verde 2× seguidas: 514 passed, 3 skipped (TMPDIR=/tmp); commits ee643045 (código+testes) e relatório.
