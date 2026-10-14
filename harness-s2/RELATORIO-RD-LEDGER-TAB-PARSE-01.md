# RELATORIO — RD-LEDGER-TAB-PARSE-01

## O bug
`ledger_missao.py` (`_procurar_aba`) lia os tabs no topo do JSON do `herdr tab list`, mas a saída real aninha em `result.tabs`. A aba nunca era achada: `registrar` esperava 60s (=`espera_s` default) e o `despachar_missao.py` cortava em 60s (rc 124, fail-open); o `fechar` nunca fechava aba.

## O fix (2 mudanças)
1. `_procurar_aba` (L64-67): lê `result.tabs` com fallback para o formato antigo (tabs no topo).
2. `registrar` (L91): `espera_s` 60 → 20 (20s < timeout de 60s do chamador).

## Prova
- `python3 -m pytest tests/test_ledger_tab_parse.py -q` → **3 passed** (funções: `test_achar_aba_result_tabs`, `test_compat_tabs_no_topo`, `test_espera_default_menor_que_timeout_chamador`).
- Commit: fix + teste no mesmo commit (`RD-LEDGER-TAB-PARSE-01: fix leitura result.tabs com fallback e espera_s=20`).
- Deploy: feito pelo supervisor (`/opt`/ledger path já aponta para o harness-s2 — o fix entra no próximo checkout/deploy do ledger_missao.py).

## Histórico
- 8 tentativas no total (3 pela fila ORQD + 4 diretas + esta fecho por supervisor): as perdas foram vagueio/leituras recusadas/commit travado — o código técnico esteve pronto desde a tentativa 2 da fila.
