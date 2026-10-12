# RELATÓRIO GB-OFFICE-VIDA-02 — prova E2E contra office real

## Veredito: PASS

## O que foi entregue

1. **prova-GB-OFFICE-VIDA-02.sh** — prova E2E de verdade, o novo padrão de aceite da ponte:
   - Sobe uma office REAL de teste (`python3 run.py --port <efemera>`) com `HERMES_HOME` em tempdir (nunca a 8113 de produção).
   - Roda a ponte (`ponte_office.py --once`) apontada pra ela, com espelho fake + `sessao.log` com 3 linhas de tipos diferentes.
   - **Ciclo 1 (atividade nova):** asserta no `GET /state` da office de teste: agente presente com `status=working`, `tool=write_file` preenchido, `activity=typing`, `detail` com preview PT-BR visível. **NUNCA idle logo após tool_start.**
   - **Ciclo 2 (sem atividade nova, janela curta):** asserta que NADA sobrescreve — status continua `working`, 0 eventos injetados.
   - **Ciclo 2b (sem atividade na janela de pausa):** espera a janela vencer (sleep 1.5s; `pause_interval()` tem piso de 1.0s) e asserta `session_idle` => `status=idle` (comportamento desejado da pausa).
   - **Ciclo 3 (pousado):** rename do espelho para `.espelho.pousado.json` => `--once` de novo => asserta que o agente SAI do `/state` (gone/ausente).
   - Resultado: **PASS** em 2 execuções seguidas (portas efêmeras 59659 e 60791).

2. **ponte_office.py** — sem alteração de lógica necessária: a prova E2E contra a office REAL de teste mostra que a sequência atual (session_start → tool_start com dados do trail → session_idle só após a janela de pausa sem linha nova → session_end no pouso, idempotente) produz exatamente o estado esperado no `/state`. O diagnóstico de que "o GET /state mostra idle" não se reproduz contra uma office limpa em porta efêmera com `HERMES_HOME` tempdir.

## Notas para o supervisor (não alterei state_model.py/run.py/event_*)

- O sintoma de produção (idle no 8113 mesmo com tool_start chegando) **não se reproduz** na office de teste limpa. Hipóteses a investigar no ambiente de produção, fora do escopo deste worktree:
  - estado persistido antigo no `HERMES_HOME` de produção (agentes fantasmas GB-STREAM-CRU-01, GB-SESSAO-GUARD-01 continuam no piso com status idle — a varredura retroativa de fantasmas da ponte só marca `ended` as sessões que ELA iniciou; sessões injetadas pela ponte antiga sem json running podem não ser cobertas se o `st["started"]` em disco não as lista);
  - concorrência: outra instância da ponte (antiga) rodando em paralelo contra a 8113 emitindo `session_idle` em sequência;
  - `session_idle` emitido no MESMO ciclo de uma atividade nova — a ponte atual já evita isso (o idle só sai se `now - last_change_ts >= pause_interval()`, e `last_change_ts` é atualizado a cada linha nova), mas se a office de produção estiver com `pause_interval` configurado menor que o intervalo de varredura, o idle pode vencer a corrida. Não alterei nada aqui porque a prova E2E contra office real limpa passa.

## Não quebrado (verificado pela prova)

- session_start (agente nasce na sala): OK ciclo 1.
- Pausa GB-SALA-PISO-02 (idle só sem linha nova na janela): OK ciclo 2b.
- Pouso (agente sai do /state): OK ciclo 3.
- Tradução PT-BR no preview: visível no `detail` do ciclo 1.
- Fail-open: ponte não derruba a office em nenhum ciclo (0 eventos quando não há mudança).