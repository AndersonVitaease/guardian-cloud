# MISSÃO STOP-STALE-01B — veredito nunca stale (re-checar stops do disco no veredito e no retry)

Fonte: ROADMAP.md (STOP-STALE-01, 3 tentativas FAIL vagueio sem WIP). operatorOrder: continuação autorizada pelo operador 10/10 noite ("despache as missões"). A régua de progresso real (VAGUEIO-PROMPT-01B) já está MERGIDA na base — este worktree nasce com ela.

## CONTEXTO MEDIDO (confie, não re-investigue)
- Caso H1H2-REPORT-01: tentativa 3 entrou em SO_EXPLORACAO, stops completaram DEPOIS do último tick, o auto-retry partiu de resumo stale (stops:[]) e fechou FAIL prematuro com entrega 100% pousada (merge d8654081).
- Caso RD-ROUTER-BRIEFING-01: FAIL vagueio com 4/5 stops e entrega completa (merge na base feito pelo supervisor).
- harness.py: pontos relevantes = avaliação de stop-conditions por tick (_stop_check), veredito por tentativa, auto-retry (despachar_missao.py lê resumo/autoretry-summary). NÃO mude a régua de vagueio (já pousada).

## MAPA
- harness.py — funções de avaliação de stop-conditions e veredito por tentativa (localize com code_find 'stop_conditions' e 'veredito').
- despachar_missao.py — leitura de resumo/autoretry-summary para o auto-retry.
- tests/ — fixtures de tick/trail para o teste novo.

## TAREFA
1. No veredito de tentativa: ANTES de declarar veredito, RELER as stop-conditions do disco (estado atual do run dir/trail) — se alguma stop mudou desde o último tick, reavaliar AGORA (veredito sobre estado fresco, nunca sobre snapshot do tick).
2. No auto-retry: o retry NUNCA parte de resumo stale — re-ler resumo/trail do disco no momento do retry; se a tentativa anterior completou stops no intervalo, o retry vira fecho/veredito, não nova tentativa.
3. Invariantes: (a) veredito FAIL com stops completos ao vivo é PROIBIDO (se ocorrer, é bug tipado); (b) resumo nunca grava stops:[] quando existem stop-conditions declaradas no contrato; (4) log do evento 'veredito_stale_evitado' quando a releitura mudou o resultado (observabilidade do conserto).
4. TESTE tests/test_stale_verdict.py: fixture H1H2 — simule tick sem stops → stops completam no disco → veredito: deve sair PASS fresco (não retry/FAIL); auto-retry com resumo atualizado no disco → não re-despacha; stops:[] com contrato com stops → erro tipado RESUMO_INVALIDO.

## REGRAS
Português/BRT; git como worker; sem sudo; sem sleep; leitura por code_slice/code_find; git add só dos arquivos da missão; sem git reset/checkout/stash.
## STOP-CONDITIONS — bloco exato abaixo
```harness-stop
cmd cd /home/worker/wt-STOP-STALE-01B && python3 -m py_compile harness.py
cmd cd /home/worker/wt-STOP-STALE-01B && TMPDIR=/tmp python3 -m pytest tests/test_stale_verdict.py -q | grep -q passed
cmd cd /home/worker/wt-STOP-STALE-01B && TMPDIR=/tmp python3 -m pytest tests/ -q | tail -1 | grep -q passed
cmd cd /home/worker/wt-STOP-STALE-01B && git log --format=%s | grep -q -F STOP-STALE-01B
cmd cd /home/worker/wt-STOP-STALE-01B && grep -q -F STOP-STALE-01B RELATORIO-STOP-STALE-01B.md
```
