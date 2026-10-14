# MISSÃO GB-SALA-ESPELHO-02

Fonte: ROADMAP fila do operador (escritorio). Gap provado 13/10: missoes
despachadas pelo caminho do harness (despachar_missao.py com mount-espelho)
NAO gravam espelho em /tmp/ag-live/ — a ponte do escritorio (porta 8113)
nao as ve, e a sala do Guardian fica so com fantasmas. O fecho JAH sabe
fechar espelho (scripts/fechar_mirror.py renomeia para .espelho.pousado.json
— provado pelos pousos de ontem). Repo harness-s2, este worktree (base
gb-backup-01). Despachar_missao.py e worker-owned no worktree.

## TAREFA 1 — despachar_missao.py grava espelho de nascimento
Apos o bloco do mount-espelho ter SUCESSO (tab != None), grave
atomicamente /tmp/ag-live/<MID>.espelho.json (dir pode nao existir: crie;
owner worker; se escrita falhar, apenas avise — fail-open, nunca derrube o
despacho):
  {"id": MID, "tab_id": <tab>, "pane_id": <tab>, "workspace_id": <primeira
   parte de tab antes de ':'>, "status": "running", "started_at": ISO com TZ}
Formato EXATAMENTE o dos fixtures tests/fixtures/TESTE-ESPELHO-*.espelho.json.
Comente com GB-SALA-ESPELHO-02. Se /tmp/ag-live ja tiver <MID>.espelho.json,
sobrescreva (retry de despacho nao deve enfileirar session_start duplicado
na ponte — a ponte deduplifica por id).

## TAREFA 2 — fechamento: confirme o ciclo
fechar_mirror.py (scripts/) deve tratar /tmp/ag-live/<MID>.espelho.json ->
renomear para .espelho.pousado.json quando a missao fechar (PASSE ou FAIL).
Se ele jah faz isso para o dir usado na 01 (confira o caminho no codigo),
aponte-o tambem para /tmp/ag-live (env AG_LIVE_DIR default /tmp/ag-live,
overridavel para prova). Fail-open.

## TAREFA 3 — testes/test_sala_espelho.py (unittest hermetico, stdlib)
Fakes: tmpdir como AG_LIVE_DIR. Casos: (1) gravacao do espelho no formato do
fixture; (2) sobrescrita em retry; (3) fail-open quando dir ilegivel;
(4) fechar_mirror renomeia para .pousado e a ponte (que observa o rename)
nao ve mais running; (5) fecho de missao sem espelho = noop tipado.
Suite toda verde -> print GB-SALA-ESPELHO-02-PROVA-OK.

## TAREFA 4 — RELATORIO-GB-SALA-ESPELHO-02.md
O ciclo completo (nascimento -> sala -> pouso -> sai da sala), e como a
missao viva de hoje (GB-THUMB-03) aparece na sala apos a aplicacao.

## MAPA
- scripts/despachar_missao.py:222-242 (bloco mount-espelho — grave APOS o
  sucesso, perto de onde tab fica != None)
- scripts/fechar_mirror.py:58 (fechar_mirror — renomeia espelho no pouse)
- tests/fixtures/TESTE-ESPELHO-20261012112709.espelho.json:1 (formato exato)
- /tmp/ag-live/ (dir que a ponte drena; owner worker)

## PROVA (stop)
```harness-stop
cmd cd /home/worker/wt-GB-SALA-ESPELHO-02 && python3 -m unittest tests.test_sala_espelho -v 2>&1 | grep -q -F 'GB-SALA-ESPELHO-02-PROVA-OK'
cmd cd /home/worker/wt-GB-SALA-ESPELHO-02 && grep -q -F 'ag-live' scripts/despachar_missao.py && grep -q -F 'GB-SALA-ESPELHO-02' scripts/despachar_missao.py
cmd cd /home/worker/wt-GB-SALA-ESPELHO-02 && git log -1 --format=%s | grep -q -F 'GB-SALA-ESPELHO-02'
cmd cd /home/worker/wt-GB-SALA-ESPELHO-02 && test -z "$(git status --porcelain)"
```

## REGRAS
Proibido git reset/checkout/stash/clean; sem sudo; sem Write com path
absoluto; unittest stdlib (sem pytest); comando falhou 2x -> le e adapte.
Duvida do spec: ask_ai_service e pare. Budget US$0,20. Turnos max 35.