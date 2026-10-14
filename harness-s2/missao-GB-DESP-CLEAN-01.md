# MISSÃO GB-DESP-CLEAN-01 — Invariante "unit viva ⇔ aba viva" no despachante

## Problema (ordem do operador 13/10)
O hard-fail PANE_AUSENTE (RD-DESP-TAB-SILENT-01) só protege o caminho que INAUGURA a
unit. No caminho UNIT_JA_ATIVA (despacho duplicado após falha anterior) e nos erros
posteriores ao spawn, ninguém verifica se a unit ativa tem aba viva → run headless
nasce sem recusa (aconteceu com GB-THUMB-03 s137: run viva, invisível no herdr).

## Escopo (pequeno, fecha sozinho)
1. `verificar_unit_com_aba(unit)` — lista panes do herdr pelo mesmo caminho do
   mount-espelho; chamada em TODOS os caminhos de saída do despachar_missao.py
   (sucesso, UNIT_JA_ATIVA, avisos, exceções): unit ativa sem pane → `systemctl stop`
   + fail tipado `UNIT_SEM_ABA`.
2. `limpar_orfaos(mid)` no início de TODO despacho: ledger /root/.hermes/mission-state/
   <id>.json em running_sem_resumo sem unit viva → mover para archive-ledger-<id>-<ts>.json;
   espelho /tmp/ag-live/<id>.espelho.pousado.json → remover. NUNCA remover espelho/ledger
   de missão com unit viva. Determinístico, sem interativo.
3. Nenhuma mudança de protocolo/JSON de saída além de campo novo `aba_verificada: true`.

## MAPA (âncoras reais)
- scripts/despachar_missao.py:243-267 (bloco espelho/aba + PANE_AUSENTE existente) e o
  caminho do erro UNIT_JA_ATIVA (buscar UNIT_JA_ATIVA).
- scripts/mount-espelho.sh (como a aba é montada/verificada).
O despachar_missao.py VIVO fica em /home/worker/harness-s2/scripts/ — trabalhe numa
CÓPIA scripts/ dentro deste worktree; o ship aplica no vivo via âncoras mínimas.

## PROVA (stop)
`prova-GB-DESP-CLEAN-01.py` (hermética, porta dinâmica): (a) unit ativa SEM pane
simulada → despacho recusa `UNIT_SEM_ABA` e unit é parada; (b) ledger running_sem_resumo
sem unit → arquivada por limpar_orfaos; (c) despacho normal continua ok (aba nasce).
Saída: `GB-DESP-CLEAN-01-PROVA-OK`.

## STOPS
```harness-stop
cmd cd /home/worker/wt-GB-DESP-CLEAN-01 && python3 -m py_compile scripts/despachar_missao.py
cmd cd /home/worker/wt-GB-DESP-CLEAN-01 && python3 prova-GB-DESP-CLEAN-01.py 2>&1 | grep -q -F 'GB-DESP-CLEAN-01-PROVA-OK'
cmd cd /home/worker/wt-GB-DESP-CLEAN-01 && test -s RELATORIO-GB-DESP-CLEAN-01.md
cmd cd /home/worker/wt-GB-DESP-CLEAN-01 && test "$(git log -1 --format=%s)" = "GB-DESP-CLEAN-01: invariante unit viva <=> aba viva no despachante + limpeza de orfaos"
cmd cd /home/worker/wt-GB-DESP-CLEAN-01 && test -z "$(git status --porcelain)"
```

## REGRAS
Prova em PRIMEIRO plano (nunca nohup/&). Sem sudo. Sem git reset/checkout/stash.
Comando falhou 2x → NÃO repita: leia e adapte. Budget US$0,25. Turnos max 40.
