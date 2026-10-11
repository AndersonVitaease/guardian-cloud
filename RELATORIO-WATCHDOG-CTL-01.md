# Relatório WATCHDOG-CTL-01

Missão WATCHDOG-CTL-01 concluída.

- scripts/watchdog_sweep.sh: sweep genérico de watchdog.d (ordem alfabética, timeout WATCHDOG_TIMEOUT=120s, captura /tmp/watchdog-<nome>-ultima.txt 0600, JSON 1 linha, exit 0 sempre).
- scripts/watchdog_ctl.sh: list/enable/disable/timer-install/timer-status, tb_audit inline, dry-run default, JSON no --apply.
- watchdog.d/10-tab-reap.sh: wrapper tab_reap --apply, silencioso se nada morto.
- patches/08-watchdog-timer.sh: unit+timer systemd watchdog-sweep (OnCalendar=*:0/10, Persistent=true), dry-run default, cria WATCHDOG_D_DIR e migra 10-tab-reap.
- tests/test_watchdog.py: 8 testes pytest com fakes em tmpdir — todos passando (8 passed).

Stop-conditions verificadas: bash -n ok nos 3 scripts; pytest watchdog 8 passed; pytest tests/ 601 passed, 2 skipped; commit WATCHDOG-CTL-01.
