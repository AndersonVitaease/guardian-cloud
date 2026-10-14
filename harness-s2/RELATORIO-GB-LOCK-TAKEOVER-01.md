# RELATORIO GB-LOCK-TAKEOVER-01

## Takeover automatico de lock de dono morto/zumbi + mensagem PT-BR com retry

### Causa (diagnostico pronto, ROADMAP.md:469)
Um par TUI/gateway orfao (processo vivo, sem atividade) segurava o lease da sessao;
o outro processo pediu o turno, `_lease_not_acquired_result` (linha ~353 do .ref)
devolveu "Stopped waiting for another Hermes process on this session" e o chat
"morreu" para o usuario (fuga de app). O modulo ja cobria stale/reclaim por TTL
(linhas ~87-156) mas nao o caso "dono VIVO porem zumbi".

### Entrega
1. **lock-takeover.patch** — unified diff contra `turn_facade_lease.py.ref`:
   - Helpers novos (`_pid_alive`, `_lease_owner_info`, `_owner_progress_age_seconds`,
     `_owner_is_stale`, `_release_stale_lease`, `_stamp_lease_heartbeat`,
     `_try_acquire_now`, `_attempt_lease_takeover`) + constantes de env
     `LOCK_STEAL_MIN` (default 120s), `LOCK_RETRY_MAX` (default 3),
     `LOCK_RETRY_BACKOFF_SECONDS` (default 5s).
   - **(a) Takeover**: antes de recusar o turno em `admit_durable_turn_lease`, checa o
     dono atual. PID morto (`os.kill(pid,0)` -> `ProcessLookupError`) OU dono vivo sem
     progresso ha > `LOCK_STEAL_MIN` (heartbeat; leases antigos sem o campo caem em
     `acquired_at`/idade) => libera o lease stale pelo caminho de release existente e
     re-tenta o acquire (1 retry imediato). So recusa se o retry tambem falhar.
   - **(b) Fail-closed**: dono vivo COM atividade recente nunca tem o lease roubado.
     Nesse caso emite "Outra janela esta usando esta conversa agora. Tentando novamente
     em Xs..." e re-tenta ate `LOCK_RETRY_MAX` com backoff 5s; erro final em PT-BR
     ("Outra janela esta usando esta conversa e nao a liberou a tempo. Sua mensagem nao
     foi processada; tente novamente em instantes.") substitui a mensagem de stop.
   - Heartbeat e gravado no acquire/refresh (best-effort, compativel com leases antigos
     sem o campo).
2. **prova-GB-LOCK-TAKEOVER-01.py** — prova hermetica: aplica o patch com `patch -p1`
   sobre copia do .ref em tempdir, importa o modulo com stubs (sem rede, sem hermes
   real) e cobre: (a) dono morto => takeover; (b) dono zumbi (heartbeat antigo) =>
   takeover; (c) dono ativo => nao rouba, mensagem PT-BR com retry, respeita
   LOCK_RETRY_MAX, erro final PT-BR; (d) lease sem heartbeat usa idade
   (acquired_at) e, sem qualquer idade, fail-closed. **RESUMO: 0 falhas.**

### Restricoes respeitadas
- Patch gerado exclusivamente contra o `.ref`; nada aplicado na instalacao real.
- Nenhum toque em server.js, app.js, /opt, /root; nenhum git reset/checkout/stash/
  clean/push.
