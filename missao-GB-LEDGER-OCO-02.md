# MISSÃO GB-LEDGER-OCO-02 — PASS_OCO honesto: status próprio + reconciliação pelo resumo

## Problema (ordem do operador 13/10 — aconteceu 2x hoje)
Quando o veredito do resumo é PASS mas a verificação de entrega rebaixa para
PASS_OCO, o ledger grava status "failed" — PERDENDO o PASS real (obrigou
sobrescrita manual do ledger 2x hoje: GB-CORTES-LINK-01 e GB-DESP-CLEAN-01).
Inconsistente com liveness honesta: "PASS com ressalva de entrega" não é FAIL.

## Escopo (fecha sozinho)
1. `scripts/ledger_missao.py:259`: PASS_OCO deixa de herdar status failed —
   grava status próprio `pass_oco` (não "failed"), preservando campos
   `veredito: PASS_OCO` + campo `entrega` com o motivo (rastreabilidade total).
2. **Reconciliação no fecho** (`missao_fechar.sh` via ledger): se
   /tmp/resumo-<id>.json tem veredito PASS e a entrega verify re-executada dá ok
   → ledger sobe para PASS (status closed). Se entrega falha de novo → mantém
   pass_oco. NUNCA rebaixa PASS para failed quando o resumo é PASS.
3. Nada muda para FAIL/FAIL-vagueio (veredito honesto intacto).

## MAPA (âncoras reais)
- scripts/ledger_missao.py:259 (veredito = "PASS_OCO") e o mapeamento
  veredito→status logo abaixo (buscar "failed").
- o relatório da missão RD-PASS-OCO-01 (no repo, arquivo do outro ID — só
  REFERÊNCIA de leitura: comportamento original: entrega ok:false rebaixa para
  PASS_OCO + status failed — é exatamente isso a corrigir).
- tests/test_ledger_pass_oco.py (14 tests existentes — atualizar, não quebrar).
CÓPIA no worktree (scripts/); ship aplica no vivo via âncoras mínimas.

## PROVA (stop)
`prova-GB-LEDGER-OCO-02.py` hermética (mktemp/tmpdir para ledger e state): (a) resumo PASS + entrega ok → ledger
closed/PASS; (b) resumo PASS + entrega falha → ledger closed/pass_oco com campo
entrega preenchido (NUNCA failed); (c) resumo FAIL → failed (regressão zero);
(d) test_ledger_pass_oco.py atualizado passa. Saída `GB-LEDGER-OCO-02-PROVA-OK`.

## STOPS
```harness-stop
cmd cd /home/worker/wt-GB-LEDGER-OCO-02 && python3 -m py_compile scripts/ledger_missao.py
cmd cd /home/worker/wt-GB-LEDGER-OCO-02 && python3 prova-GB-LEDGER-OCO-02.py 2>&1 | grep -q -F 'GB-LEDGER-OCO-02-PROVA-OK'
cmd cd /home/worker/wt-GB-LEDGER-OCO-02 && test -s RELATORIO-GB-LEDGER-OCO-02.md
cmd cd /home/worker/wt-GB-LEDGER-OCO-02 && test "$(git log -1 --format=%s)" = "GB-LEDGER-OCO-02: PASS_OCO honesto (status proprio) + reconciliacao pelo resumo no fecho"
cmd cd /home/worker/wt-GB-LEDGER-OCO-02 && test -z "$(git status --porcelain)"
```

## REGRAS
Prova em PRIMEIRO plano (nunca nohup/&). Sem sudo. Sem git reset/checkout/stash.
Comando falhou 2x → NÃO repita: leia e adapte. Budget US$0,25. Turnos max 35.
