# MISSÃO RUN-STREAM-01 — tool bash run_stream.sh: filme da run no herdr (0 LLM)

Fonte: ROADMAP.md linha 380.

operatorOrder: streamer de run autorizado pelo operador 10/10.

## MAPA PRÉ-DIGERIDO
- Padrão de forma EXATO: /opt/mission-events/tools-bash/runs_status.sh (L1-8, source _lib.sh, tb_audit L30, tb_fail L64, exit 0 SEMPRE, JSON 1 linha). One-shot de trilha existente: /opt/mission-events/tools-bash/trail_tail.sh (ler; ele imprime JSON cru das últimas N linhas).
- Situação: `herdr pane run <pane> <cmd>` imprime stdout do comando na pane do operador ao vivo — o streamer é o comando. run dir resolver igual run_close.sh (ledger cwd → layout tentativa-N/run-*; trail em harness-trail.jsonl dentro do run dir).
- Formato de evento da trilha (medido ao vivo): linhas JSON com campos de turno (hora BRT, turno, rótulo tipo AGIR/_vagueio/_close_reprompt, custo, stops ok/N) e linha final VEREDITO com motivo/turnos/custo.

## OBJETIVO
Tool `run_stream.sh <ID|run-dir> [--follow] [N]`:
1. Sem --follow: snapshot — últimas N linhas de evento (default 15) formatadas UMA linha por turno: `[HH:MM:SS BRT] turno K | ROTULO | $custo | ok=X/Y`; linha VEREDITO final quando existir; erros tipados INVALID_MISSION_ID, RUN_DIR_NAO_ENCONTRADO, SEM_TRAIL (com dica de pane).
2. --follow: `tail -n 0 -f` no trail com o MESMO filtro; **termina sozinho** ao imprimir a linha VEREDITO (grep final; sem loop de sleep). Nunca é daemon eterno.
3. Filtra ruído: imprime SÓ eventos de estado (turno/rótulo/custo/stops/veredito); tool_calls e conteúdo de mensagens NUNCA saem. Linhas que não casam evento são descartadas.
4. Saída para pane (texto multi-linha legível), mas exit 0 sempre e tb_audit UMA vez (nos snapshots usa tb_join). Custo acumulado calculado pelo próprio streamer (soma dos deltas do trail).
5. BRT em toda hora (UTC-3), formato HH:MM:SS.

## TAREFA
1. Ler runs_status.sh e trail_tail.sh; escrever `run_stream.sh` na raiz do worktree.
2. Teste hermético `test_run_stream.sh`: trail fake em scratch (fixture com 6 eventos + veredito + 3 linhas de ruído gigante) via env RUN_STREAM_TRAIL: snapshot mostra 6 eventos formatados e 0 ruído; custo acumulado correto; hora BRT correta (fixture com UTC conhecido); --follow simulado com arquivo que ganha linha VEREDITO após 1s (background + wait com timeout, vagueio=False no teste); SEM_TRAIL quando arquivo falta.
3. Commit `RUN-STREAM-01: run_stream.sh + test_run_stream.sh` e `RUN-STREAM-01: relatorio` (RELATORIO-RUN-STREAM-01.md, 2 linhas).

## ACEITE
```harness-stop
cmd cd /home/worker/wt-RUN-STREAM-01 && git log -1 --format=%s | grep -q -F "RUN-STREAM-01: run_stream.sh"
cmd cd /home/worker/wt-RUN-STREAM-01 && bash -n run_stream.sh
cmd cd /home/worker/wt-RUN-STREAM-01 && bash test_run_stream.sh
cmd cd /home/worker/wt-RUN-STREAM-01 && git ls-files --error-unmatch run_stream.sh && git -C /home/worker/wt-RUN-STREAM-01 diff --quiet HEAD -- run_stream.sh
cmd cd /home/worker/wt-RUN-STREAM-01 && git ls-files --error-unmatch RELATORIO-RUN-STREAM-01.md
```

PROIBIDO: git reset/checkout/stash/clean; escrita em /opt e /root; loop de sleep; daemon eterno (sem --follow, sai após snapshot).
