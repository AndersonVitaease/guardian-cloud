# RELATORIO-LEDGER-REOPEN-FIX-01

Data: 12/10/2026 (BRT). Agente: MECÂNICO. Arquivo: `scripts/ledger_missao.py`.

## Diagnóstico confirmado

Em `fechar()`, um resumo vazio (ExecStopPost sem resumo.json) produzia
`veredito = ""` → `status = "failed"` com `veredito: None`. Como `failed`
está em `TERMINAIS`, o fecho posterior com resumo real batia na trava
idempotente e retornava `idempotente: true` sem gravar nada — o ledger
ficava "failed" para sempre, mentindo o briefing.

## Correções (scripts/ledger_missao.py, função fechar)

1. Reabertura: se status atual é `failed` com `veredito is None` e o novo
   resumo tem veredito real, o fecho prossegue e sobrescreve com
   `closed/failed` + veredito + custo_usd + turnos + relatório. A
   idempotência real (depois de fecho legítimo) continua valendo, e
   `failed` legítimo (com veredito) não reabre.
2. Fecho sem veredito no resumo: não grava `failed` cego — grava
   `running_sem_resumo` (não-terminal, fora de TERMINAIS), permitindo o
   fecho posterior normal. Se o ledger já era terminal, mantém
   idempotência.

## Prova (scripts/test_ledger_reopen.py, ledger em tempdir)

15 checks, 3 caminhos + guarda:

- Caminho 1: failed+None + resumo PASS → reabre, status closed,
  veredito PASS, custo 0.42, turnos 12; idempotência após fecho legítimo OK.
- Caminho 2: resumo vazio → running_sem_resumo (não failed); fecho
  posterior com resumo real → closed/PASS.
- Caminho 3: fecho normal → closed com veredito PASS.
- Extra: failed legítimo (veredito FAIL real) não reabre.

Saída: `LEDGER-REOPEN-OK` / `RESUMO: 0 falhas`.

## Entregas

1. ✅ fechar() reabre failed sem veredito quando resumo tem veredito real.
2. ✅ Fecho automático sem resumo grava running_sem_resumo (não-terminal).
3. ✅ Prova hermética 3 caminhos, marcador LEDGER-REOPEN-OK, "RESUMO: 0 falhas".
4. ✅ Este relatório + commit único `LEDGER-REOPEN-FIX-01: fecho reabre failed sem veredito e não grava failed cego`.
