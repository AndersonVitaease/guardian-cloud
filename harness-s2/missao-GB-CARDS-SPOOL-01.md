# MISSAO GB-CARDS-SPOOL-01

Fonte: ROADMAP.md linha 470 (ordem operator 12/10: os cards "Recentes" do Guardian mostram so as missoes do orchestrator (RD-*, shadow eterno) e nunca as missoes despachadas direto pelo harness — o operator ve "missoes diferentes no guardian vs herdr").

Diagnostico pronto (nao investigue de novo):
- /api/missions/recent (guardian-app server.js ~1772) le o SPOOL do orchestrator (env GUARDIAN_SPOOL_PATH, default o spool.jsonl do mission-events): eventos JSONL com {ts, kind: mission_start|mission_end|..., missionId, data:{veredito, custo_usd, budget_usd}}.
- O mission_start JA EXISTE no despacho: despachar_missao.py:165-173 (GB-DASH-REAL-01) grava no spool real.
- O mission_end NAO existe: ledger_missao.py fechar (linha 196) grava o ledger fechado mas nao emite evento no spool → os cards mostram missoes "EM VOO" eternas (as RD-* shadow) e nunca veem o fecho das missoes do harness.

Entrega (harness-s2 — arquivo UNICO: scripts/ledger_missao.py; NAO server.js, NAO app.js, NAO despachar_missao.py):
1. Na funcao fechar (ledger_missao.py:196), depois de gravar o ledger fechado, emita mission_end no spool:
   - evento JSONL append: {"ts": <epoch>, "kind": "mission_end", "missionId": <id>, "data": {"veredito": ..., "custo_usd": ..., "budget_usd": ..., "turnos": ..., "fonte": "harness"}}
   - caminho do spool: env GUARDIAN_SPOOL_PATH com o mesmo default do server.js (spool.jsonl do mission-events).
   - append-only, fail-open (spool ausente/inacessivel = pula sem crash, loga em stderr).
   - NUNCA truncar o spool; sem reescrever linhas existentes.
2. Prova hermetica (prova-GB-CARDS-SPOOL-01.sh, tempdir com spool fake via env GUARDIAN_SPOOL_PATH): fechar uma missao fake => spool ganha mission_end tipado com veredito/custo; spool ausente => fail-open. RESUMO: 0 falhas.

MAPA:
- scripts/ledger_missao.py:196 (def fechar — ponto de insercao do mission_end)
- scripts/ledger_missao.py:265 (def main — o subcomando fechar passa aqui)
- scripts/despachar_missao.py:165-173 (mission_start existente — COPIE o formato exato do evento daqui; leitura)


Stops (4):
```harness-stop
cmd cd /home/worker/wt-GB-CARDS-SPOOL-01 && bash scripts/prova-GB-CARDS-SPOOL-01.sh
cmd cd /home/worker/wt-GB-CARDS-SPOOL-01 && bash -n scripts/ledger_missao.py || python3 -m py_compile scripts/ledger_missao.py
cmd cd /home/worker/wt-GB-CARDS-SPOOL-01 && test -f RELATORIO-GB-CARDS-SPOOL-01.md
cmd cd /home/worker/wt-GB-CARDS-SPOOL-01 && test "$(git log -1 --format=%s)" = "GB-CARDS-SPOOL-01: fecho e despacho emitem mission_start/end no spool do guardian"
```

Restricoes: SO scripts do harness-s2 neste worktree. Nao toque em server.js/app.js (streamer e rota estao em outras missoes), NAO em /opt ou /root em runtime (o spool real so o supervisor toca). Proibido: git reset, checkout, stash, clean, push — nunca.
