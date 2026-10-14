# RELATORIO WATCHDOG-CTL-01

Missao: watchdog.d generico (sweep + governanca + timer systemd).

Entregaveis:
- scripts/watchdog_sweep.sh: sweep silencioso, ordem alfabetica, timeout WATCHDOG_TIMEOUT=120s, captura em /tmp/watchdog-<nome>-ultima.txt (0600), JSON 1 linha, exit 0 sempre.
- scripts/watchdog_ctl.sh: list|enable|disable|timer-install|timer-status, dry-run default, tb_audit inline, JSON no --apply.
- watchdog.d/10-tab-reap.sh: wrapper 3 linhas chamando tab_reap --apply.
- patches/08-watchdog-timer.sh: unit+timer systemd watchdog-sweep (OnCalendar=*:0/10, Persistent=true), dry-run default, criacao do WATCHDOG_D_DIR e migracao do 10-tab-reap. Execucao e do supervisor no fecho (worker nao toca systemctl).
- tests/test_watchdog.py: 8 testes pytest com fakes em tmpdir (sweep falha isolada, pulo de desabilitado, timeout, ctl dry-run nao muta, enable chmod, JSON 1 linha).

Validacao: bash -n ok nos 3 scripts; pytest tests/ = 601 passed, 2 skipped.

Escalacao registrada: tentativa de systemctl mutate recusada pelo harness (BARRERA) — correto, pois execucao do timer cabe ao supervisor no fecho.
