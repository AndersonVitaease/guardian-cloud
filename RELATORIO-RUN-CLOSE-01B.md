# RUN-CLOSE-01B

Mudou: run_close.sh normaliza o run_dir (sobe de tentativa-N/run-* ao ancestral com resumo.json/autoretry-summary.json) e extrai veredito/tentativas/turnos/custo_usd/stops do schema real do autoretry-summary.json (vereditos_por_tentativa, runs[].turnos, custo_total, stop_conditions[].cmd/ok); test_run_close.sh estendido a 5 casos.
Prova: bash run_close.sh RUN-CLOSE-01 -> ok:true, veredito:"PASS", tentativas:1, turnos:17, custo_usd:0.032885, 4 stops ok:true; bash test_run_close.sh -> "casos ok: 5/5".
