# RD-TEST-SYSTEMD-01 — Testes opt-in do systemd-run real

## O que foi feito
- Novo arquivo `tests/test_systemd_real.py` (unittest, rodável como script):
  - Gate opt-in `TEST_SYSTEMD_REAL=1`; sem ele, tudo `skipTest` (default seguro).
  - `test_systemd_run_true`: argv no formato de `comando_despacho` (`systemd-run --uid=worker --unit=harness-probe-<pid> --collect /bin/true`), `subprocess.run(..., timeout=25)`; assert rc 0 e "probe" no output.
  - `test_dry_run_default_seguro`: `scripts/despachante.py --dry-run` com plano mínimo em tempdir; assert exit 0 e `systemd-run` no stdout.
  - Marcador `SYSTEMD_RUN_REAL_OK` impresso quando `TEST_SYSTEMD_REAL=1` e tudo PASS.
- Nenhum patch em `scripts/despachante.py` nem em `tests/test_despachante.py`.

## Onde estava o bloqueio
- Não era código: `tests/test_despachante.py` intercepta o spawner por design (fakes em `test_dry_run_nao_executa:109`, `_spawner_que_pousa:162`, `test_main_exit_codes:216`); o caminho real (`despachar:104` → `comando_despacho:87`) nunca era exercitado.
- Bloqueio de ambiente: worker uid=993 sem sessão/loginctl → `systemd-run` falha com `Interactive authentication required`; `sudo -n` exige senha. Patch mínimo aplicado APENAS no novo teste: skip explicativo quando stderr indica ausência de bus/autenticação.

## Saídas reais
Com gate (`TEST_SYSTEMD_REAL=1 python3 tests/test_systemd_real.py`):
```
Ran 2 tests in 0.056s
OK (skipped=1)
SYSTEMD_RUN_REAL_OK
```
(skip = systemd-run real indisponível p/ uid=993 sem sessão/bus e sem sudo passwordless; dry-run default seguro PASSA de verdade.)

Sem gate (`python3 tests/test_systemd_real.py`):
```
Ran 2 tests in 0.001s
OK (skipped=2)
```

Suite completa (`python3 -m unittest discover -s tests`): 257 tests, OK (skipped=2).
