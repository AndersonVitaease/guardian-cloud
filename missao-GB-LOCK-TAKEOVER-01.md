# MISSAO GB-LOCK-TAKEOVER-01

Fonte: ROADMAP.md linha 469 (ordem operator 12/10: usuarios nao podem ver o chat "parar" com "Stopped waiting for another Hermes process on this session" — fuga de app; cura = takeover automatico de lock de dono morto + mensagem amigavel).

Diagnostico pronto (nao investigue de novo):
- O arquivo .ref deste worktree e o turn_facade_lease.py REAL do Hermes core (versao em producao no servidor, copiado pelo supervisor — so leitura para voce; seu trabalho produz PATCH, nao edita o .ref).
- Causa do incidente: um par TUI/gateway ORFAO (processo vivo, sem atividade) segurava o lease da sessao; o outro processo pediu o turno, _lease_not_acquired_result (linha ~353) devolveu a mensagem de recusa e o chat "morreu" para o usuario.
- O modulo ja tem nocoes de stale/reclaim (linhas ~87-156) mas o caso "dono VIVO porem zumbi" (processo existe, nao ha progresso ha minutos) nao e coberto.

Entrega (harness-s2, arquivos NOVOS neste worktree — patch e prova):
1. lock-takeover.patch — unified diff contra turn_facade_lease.py (.ref) que adiciona:
   a. ANTES de recusar o turno: checar o dono atual do lease. Se o PID do dono nao existe mais (os.kill(pid,0) -> ProcessLookupError) OU o dono existe mas esta SEM progresso ha > LOCK_STEAL_MIN segundos (env, default 120; progresso = heartbeat/timestamp que o modulo ja grava — se nao existir campo de heartbeat, adicione um no acquire, compativel com leases antigos sem o campo), então: liberar o lease stale (o caminho de reclaim que o modulo ja tem) e TENTAR adquirir de novo (1 retry); so recusar se o retry tambem falhar.
   b. Fail-closed para seguranca: NUNCA roubar o lease de um dono vivo COM atividade recente (chat de verdade em outra janela). Nesse caso, em vez da mensagem atual de stop, devolver mensagem PT-BR amigavel com auto-retry curto: "Outra janela esta usando esta conversa agora. Tentando novamente em Xs..." — e o chamador re-tenta ate LOCK_RETRY_MAX (env, default 3) com backoff 5s antes do erro final (que tambem sai em PT-BR).
2. prova-GB-LOCK-TAKEOVER-01.py — prova hermetica (importa o modulo COM O PATCH aplicado sobre copia em tempdir; sem rede, sem hermes real):
   (a) dono morto (pid inexistente) => takeover, turno adquirido no retry;
   (b) dono vivo com heartbeat antigo (> LOCK_STEAL_MIN fake) => takeover;
   (c) dono vivo com heartbeat recente => NAO rouba; mensagem PT-BR com retry; apos esgotar retries, erro final PT-BR;
   (d) leases antigos sem campo de heartbeat => tratados como sem progresso conhecido (usa mtime/idade do lease) — compatibilidade.
   RESUMO: 0 falhas no fim.

MAPA (tudo no arquivo .ref deste worktree, leitura):
- turn_facade_lease.py:238 (admit_durable_turn_lease)
- turn_facade_lease.py:353-399 (_lease_not_acquired_result e a mensagem "Stopped waiting")
- turn_facade_lease.py:87-156 (stale-turn cleanup/reclaim, watchdog, stale claim)

Stops (4):
```harness-stop
cmd cd /home/worker/wt-GB-LOCK-TAKEOVER-01 && test -f lock-takeover.patch
cmd cd /home/worker/wt-GB-LOCK-TAKEOVER-01 && python3 prova-GB-LOCK-TAKEOVER-01.py
cmd cd /home/worker/wt-GB-LOCK-TAKEOVER-01 && test -f RELATORIO-GB-LOCK-TAKEOVER-01.md
cmd cd /home/worker/wt-GB-LOCK-TAKEOVER-01 && test -z "$(git status --porcelain '*.py' '*.patch')" && test "$(git log -1 --format=%s)" = "GB-LOCK-TAKEOVER-01: takeover de lock de dono morto e mensagem PT-BR com retry"
```

Restricoes: patch contra o .ref SOMENTE (a aplicacao na instalacao real e do supervisor). Nao toque em server.js, app.js, /opt, /root. Proibido: git reset, checkout, stash, clean, push — nunca.
