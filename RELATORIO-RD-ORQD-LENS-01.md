# RELATORIO RD-ORQD-LENS-01

Commit: ee4bb9b6 (branch rd-orqd-lens-01) - 3 arquivos: tools-bash/runs_status.sh, tools-bash/orq_status.sh (novo), prova_lens.py (novo).

## TAREFA 1 - runs_status.sh lista orq-*
- Segunda listagem `systemctl list-units --all --no-legend orq-*` apos a de harness-*; nomes normalizados com sufixo .service; conjunto orq_units mesclado em units (loop existente percorre ambos).
- Para units em orq_units: missionId derivado da UNIT (remove `orq-` e sufixo `-a<NUM>`); campo "orq": true; demais "orq": false. Nenhum campo existente alterado; ordem preservada.

## TAREFA 2 - tools-bash/orq_status.sh
- Modelado em runs_status.sh/_lib.sh: set -u, source _lib.sh, start=$(date +%s%N), corpo python3 heredoc, tb_emit orq_status "$OUT" "$start".
- Sock default /run/orqd-live/orqd.sock, override por arg 1 ou env ORQD_SOCK. Chama orqd.api.request(sock, {"cmd":"list"}) com timeout 5s, try/except (PermissionError/OSError/Exception).
- OK: {"ok":true,"tool":"orq_status","sock","total","por_state","ativas":[running|queued, created_at desc, max 20]}. Falha: {"ok":false,"error":"ORQD_INDISPONIVEL","detail"} exit 0, sem stack trace. Somente leitura.

## TAREFA 3 - prova_lens.py
- Roda orq_status.sh e runs_status.sh (timeout 20s), valida ok:true, total>=1, states validos, >=1 entrada orq:true; imprime por_state e marcador PROVA-ORQD-LENS-01-OK.

## STOP-CONDITIONS - todas verdes
- grep '"orq"' em runs_status.sh: OK
- grep ORQD_INDISPONIVEL em orq_status.sh: OK
- python3 prova_lens.py: PROVA-ORQD-LENS-01-OK (exit 0; por_state {"running":1,"passed":38,"needs_human":19,"cancelled":18}; runs_status mostra orq-CAN-DEPS-A3-01-a1 com orq:true)

Obs.: units orq-* sao transient e aparecem em list-units so quando ativas; a prova passou com a run viva orq-CAN-DEPS-A3-01-a1. Runs vivas nao foram tocadas.
