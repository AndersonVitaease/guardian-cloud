# MISSÃO QUEUE-EYE-01 — tool bash queue_eye.sh: quem consome a fila do orquestrador (0 LLM)

Fonte: ROADMAP.md linha 377.

operatorOrder: diagnosis da fila autorizado pelo operador 10/10.

## MAPA PRÉ-DIGERIDO
- Padrão de forma EXATO: /opt/mission-events/tools-bash/runs_status.sh (L1-8, source _lib.sh, tb_audit L30, tb_fail L64, exit 0 SEMPRE, JSON 1 linha). Leitura de /proc permitida (nada de escrita).
- Situação medida ao vivo (10/10): dois daemons `orqd.daemon` no MESMO workspace w8 — pid 2424807 (`--db /var/lib/orqd-live/orqd.db --sock /run/orqd-live/orqd.sock --queue /opt/mission-events/orchestrator-queue.js*`) e pid 3772362 (`--db /var/lib/orqd/orqd.db --sock /run/orqd.sock --queue /opt/mission-events/orchestrator-queue.jsonl --spool /op...`); consumidor legado orchestrator-consumer.py (1113573) MORTO. A fila canônica é /opt/mission-events/orchestrator-queue.jsonl (catálogo do orquestrador).

## OBJETIVO
Tool `queue_eye.sh` — read-only:
1. Lista processos `orqd.daemon` e `orchestrator-consumer`: pid, user, --db, --queue, --sock (parse do cmdline via /proc).
2. Para cada arquivo de fila em /opt/mission-events (orchestrator-queue.jsonl e variantes .js*): tamanho, mtime (hora BRT), profundidade (linhas que são JSON válido de missão), quantas com `"status":"dispatched"` sem veredito.
3. Lock/offset: lsof nos arquivos de fila (quem tem fd aberto) — sem lsof, tenta /proc/*/fd apontando para o arquivo; campo consumidores:[pid].
4. Saída JSON: {ok, tool, daemons:[], filas:[{arquivo, bytes, mtime_brt, profundidade, dispatched_sem_veredito, consumidores:[]}], duplicado: bool (2+ daemons na mesma fila), modo:"scan"}. `--only daemons|filas` opcional. NUNCA escreve em /opt; NUNCA mata processo.

## TAREFA
1. Ler runs_status.sh; escrever `queue_eye.sh` na raiz do worktree.
2. Teste hermético `test_queue_eye.sh`: fixtures de cmdline fake em arquivo (--proc-dump, mesmo padrão do orq_hygiene.sh se existir no repo instalado /opt/mission-events/tools-bash/orq_hygiene.sh — pode ler) e fila fake em scratch (env QUEUE_EYE_DIR) cobrindo: 2 daemons na mesma fila → duplicado:true; profundidade conta só JSON válido; dispatched sem veredito contado.
3. Commit `QUEUE-EYE-01: queue_eye.sh + test_queue_eye.sh` e `QUEUE-EYE-01: relatorio` (RELATORIO-QUEUE-EYE-01.md, 2 linhas).

## ACEITE
```harness-stop
cmd cd /home/worker/wt-QUEUE-EYE-01 && git log -1 --format=%s | grep -q -F "QUEUE-EYE-01: queue_eye.sh"
cmd cd /home/worker/wt-QUEUE-EYE-01 && bash -n queue_eye.sh
cmd cd /home/worker/wt-QUEUE-EYE-01 && bash test_queue_eye.sh
cmd cd /home/worker/wt-QUEUE-EYE-01 && git ls-files --error-unmatch queue_eye.sh && git -C /home/worker/wt-QUEUE-EYE-01 diff --quiet HEAD -- queue_eye.sh
cmd cd /home/worker/wt-QUEUE-EYE-01 && git ls-files --error-unmatch RELATORIO-QUEUE-EYE-01.md
```

PROIBIDO: git reset/checkout/stash/clean; escrita em /opt; matar processo; tocar routing/bridge.
