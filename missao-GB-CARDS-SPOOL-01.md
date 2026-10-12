# MISSAO GB-CARDS-SPOOL-01

Fonte: ROADMAP.md linha 470 (ordem operator 12/10: os cards "Recentes" do Guardian mostram so as missoes do orchestrator (RD-*, shadow eterno) e nunca as missoes despachadas direto pelo harness — o operator ve "missoes diferentes no guardian vs herdr").

Diagnostico pronto (nao investigue de novo):
- /api/missions/recent (guardian-app server.js ~1772) le o SPOOL do orchestrator (env GUARDIAN_SPOOL_PATH, default o spool.jsonl do mission-events): eventos JSONL com {ts, kind: mission_start|mission_end|..., missionId, data:{veredito, custo_usd, budget_usd}}.
- As missoes despachadas via despachar_missao.py + missao_fechar (harness) NAO gravam no spool → invisiveis nos cards.
- O spool tambem acumula missoes shadow do orqd (RD-ORCH-ENV-01) que ficam "EM VOO" eternas (nunca recebem mission_end).

Entrega (harness-s2 — arquivo UNICO: scripts/ledger_missao.py OU o ponto central onde o fecho grava o ledger; NAO server.js, NAO app.js):
1. No fecho (o mesmo caminho que grava o ledger fechado — ache via code_slice no repo; o missao_fechar chama ledger_missao.py fechar), emita 2 eventos no spool:
   - mission_start: no despacho (ache o ponto do despachar_missao.py que registra a missao; se for outro arquivo, integre via subprocess python3 one-liner chamando ledger_missao.py spool-event --kind mission_start --mission-id X --budget Y para nao abrir um segundo arquivo).
   - mission_end: no fechar, com data {veredito, custo_usd, budget_usd, turnos}.
   - Escrita fail-open: append JSONL com flock (flock nao obrigatorio se o spool ja e append-only concorrente — siga o padrao que o spool usa hoje; leia 10 linhas dele via file_peek antes, sao dados). Caminho do spool vem de env GUARDIAN_SPOOL_PATH com o mesmo default do server.js. Trunca NUNCA: append only.
2. Shadow: eventos com campo shadow:true no spool existem; o card RD-ORCH-ENV-01 fica "EM VOO" eterno porque o orqd shadow nao emite fim. NAO mexa no orqd; apenas garanta que seus eventos novos carregam "fonte":"harness" no data (para o supervisor diferenciar depois no guardian; sem mudanca no server.js nesta missao).
3. Prova hermetica (prova-GB-CARDS-SPOOL-01.sh, tempdir: spool fake via env GUARDIAN_SPOOL_PATH): despacho fake + fecho fake => spool ganha mission_start e mission_end tipados; spool ausente/inacessivel => fail-open sem crash. RESUMO: 0 falhas.

MAPA:
- scripts/ledger_missao.py (leitura: ache a funcao fechar e o ponto de gravacao final)
- scripts/despachar_missao.py (leitura: ache onde registra ledger inicial)
- Dados: linhas do spool real de producao — o supervisor cola 3 linhas de exemplo no fim deste arquivo se voce pedir via relatorio; NAO adivinhe o schema: copie o parse do server.js (padrao do evento descrito acima).

Stops (4):
```harness-stop
cmd cd /home/worker/wt-GB-CARDS-SPOOL-01 && bash scripts/prova-GB-CARDS-SPOOL-01.sh
cmd cd /home/worker/wt-GB-CARDS-SPOOL-01 && bash -n scripts/ledger_missao.py || python3 -m py_compile scripts/ledger_missao.py
cmd cd /home/worker/wt-GB-CARDS-SPOOL-01 && test -f RELATORIO-GB-CARDS-SPOOL-01.md
cmd cd /home/worker/wt-GB-CARDS-SPOOL-01 && test "$(git log -1 --format=%s)" = "GB-CARDS-SPOOL-01: fecho e despacho emitem mission_start/end no spool do guardian"
```

Restricoes: SO scripts do harness-s2 neste worktree. Nao toque em server.js/app.js (streamer e rota estao em outras missoes), NAO em /opt ou /root em runtime (o spool real so o supervisor toca). Proibido: git reset, checkout, stash, clean, push — nunca.
