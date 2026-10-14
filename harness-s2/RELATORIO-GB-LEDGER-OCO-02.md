# RELATORIO-GB-LEDGER-OCO-02 — PASS_OCO honesto + reconciliação pelo resumo no fecho

## Problema
Veredito PASS rebaixado por entrega ok:false gravava status "failed" no ledger,
perdendo o PASS real (2 sobrescritas manuais hoje: GB-CORTES-LINK-01,
GB-DESP-CLEAN-01).

## Correções (scripts/ledger_missao.py)
1. `fechar()` (~linha 216): veredito PASS_OCO grava status próprio `pass_oco`
   (não "failed"), preservando `veredito: PASS_OCO` e campo `entrega` com o
   motivo (rastreabilidade total).
2. Reconciliação no fecho: veredito PASS re-executa entrega_verify — ok →
   closed/PASS; falha → pass_oco. `pass_oco` não é terminal (excluído do
   early-return idempotente), então fecho seguinte com entrega ok sobe para
   closed/PASS. PASS nunca rebaixa para failed.
3. FAIL/FAIL-vagueio inalterados (veredito honesto intacto).

## Prova (prova-GB-LEDGER-OCO-02.py, hermética, tmpdir)
- (a) resumo PASS + entrega ok → closed/PASS ✓
- (b1) resumo PASS + entrega falha → pass_oco, campo entrega preenchido, nunca failed ✓
- (b2) reconciliação: fecho seguinte com entrega ok → closed/PASS ✓
- (c) resumo FAIL → failed (regressão zero) ✓
- (d) tests/test_ledger_pass_oco.py passa ✓
Saída: GB-LEDGER-OCO-02-PROVA-OK