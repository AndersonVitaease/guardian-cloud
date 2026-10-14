# RELATORIO - RD-TOOL-VIGIA-03

Vigia contra as tools REAIS: correcao dos 2 bugs de integracao medidos ao vivo.

## Correcoes (RD-TOOL-VIGIA-03)

1. Vida da run: derivada de `runs_status.sh --only-active` (campos `unit`/`active`/`tab`), sem `systemctl` direto. Se `count:0` para o ID mas `runs_historico.sh` traz `verdict`, o `fim` usa o veredito do historico - corrige Sintoma A (`inicio` nunca emitido) e Sintoma B (`historico sem veredito`).
2. Fim: le `runs_historico.sh` com campos reais - `verdict` (nao `veredito`), `tentativas`, `turnos`, `finished_at` - e causa dominante via `triagem.sh`.
3. Andamento: usa `turn`/`cost_usd`/`stops` do runs_status real; `sem_avanco` quando `turn` nao muda por `--sem-avanco-min` (default 10), com evento `retomou` quando volta a avancar.
4. Fakes atualizados para reproduzir exatamente os JSONs reais medidos.

## Validacao

- `python3 -m unittest tests.test_vigia_run` -> 11 testes OK: seed/aba derivadas do payload (`unit`/`tab`), wrapper autonomo sem `_lib.sh`, `BAD_ARGS` tipado com envelope `untrusted`, `sem_avanco`+`retomou`, run ativa com shape real, run terminada com `verdict: PASS` do historico.
- Sem `systemctl` em `scripts/vigia_run.py`; campo `verdict` presente.

## Proximo passo

Smoke real como worker: `vigia_run.sh <ID>` contra `/opt/mission-events/tools-bash`.
