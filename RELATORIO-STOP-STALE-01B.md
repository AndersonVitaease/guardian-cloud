# RELATÓRIO — MISSÃO STOP-STALE-01B — veredito nunca stale

## Problema (casos medidos)
- H1H2-REPORT-01 (tentativa 3): stops completaram DEPOIS do último tick; o
  auto-retry partiu de resumo stale (`stops:[]`) e fechou FAIL prematuro com
  entrega 100% pousada (merge d8654081).
- RD-ROUTER-BRIEFING-01: FAIL vagueio com 4/5 stops e entrega completa.

## Conserto (harness.py)
1. **Veredito fresco** — `veredito_fresco()`: imediatamente antes de declarar
   o veredito de tentativa, o harness RE-LÊ as stop-conditions do disco
   (estado atual do run_dir via `check_stop_conditions`), nunca o snapshot
   do último tick. Se alguma stop completou no intervalo, o veredito sai
   PASS sobre estado fresco.
2. **Auto-retry nunca stale** — `retry_ou_veredito()`: no momento do retry,
   re-avalia o resumo + estado fresco do disco; se a tentativa anterior
   completou stops no intervalo, o retry vira veredito (PASS), não nova
   tentativa. `despachar_missao.py` consome essa função antes de despachar.
3. **Invariantes**:
   - (a) FAIL com stops completas ao vivo é PROIBIDO — guard tipado
     `VEREDITO_STALE_BUG` (RuntimeError) em `veredito_fresco`.
   - (b) resumo nunca grava/aceita `stops:[]` com stop-conditions
     declaradas no contrato — erro tipado `ResumoInvalido`
     (`validar_resumo_stops`).
4. **Observabilidade** — evento `_veredito_stale_evitado` no trail (e linha
   no pane) sempre que a releitura mudou o resultado (FAIL→PASS).

## Teste (tests/test_stale_verdict.py)
Fixture H1H2: tick sem stops → stops completam no disco → veredito PASS
fresco (não retry/FAIL); auto-retry com resumo atualizado no disco → não
re-despacha; `stops:[]` com contrato com stops → `ResumoInvalido`.

Missão: STOP-STALE-01B.