# RELATORIO-HYGIENE-01

Entrega: harness-hygiene

## O que foi feito
- Retomada cirúrgica da missão HYGIENE-01 (checkpoint s/2284): harness.py e
  scripts/checkpoint.py já estavam editados e commitados (run_tempo_ms,
  tempo_turno_p50_ms, make_run_dir resiliente a PermissionError).
- Escrito `tests/test_hygiene.py` com 3 testes (bridge mockada + patch do
  atributo `harness.HARNESS_ADVISOR = False` no setUp/tearDown, esqueleto de
  tests/test_vagueio.py):
  1. run curta (2 turnos) → resumo contém `run_tempo_ms` (int >0) e
     `tempo_turno_p50_ms` (int >0);
  2. monkeypatch de `os.makedirs` levantando PermissionError na 1ª chamada →
     run completa (veredito PASS), run_dir sob tmpdir, trail existe;
  3. resumo normal mantém chaves antigas (veredito, turnos, custo, trail,
     run_dir).
- `RELATORIO-HYGIENE-01.md` escrito; commit no master + tag HYGIENE-01.

## Provas
- `python3 -m pytest tests/test_hygiene.py -q` → 3 passed.
- `python3 -m pytest tests/ -q` → 336 passed (333 + 3 novos).
- `git status -s` → árvore limpa após commit.

## Custo
- ~US$ 0,05 (estimativa; validações pytest locais com bridge mockada: custo
  zero de API; apenas tokens de sessão do worker).