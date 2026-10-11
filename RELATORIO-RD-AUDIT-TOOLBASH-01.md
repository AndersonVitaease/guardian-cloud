# RELATORIO RD-AUDIT-TOOLBASH-01 - Auditoria independente da Pista-2 TOOLS

Data: 2026-10-11 ~03:40 BRT. Auditor: worker delegado (ORD-010). Read-only fora do cwd; escrita apenas neste relatorio + cache gerado pelo proprio executor.

## 1. Guardas em scripts/toolbash.py (codigo lido integralmente, linhas 1-159)

- Dedupe por hash - dedupe_key() L34-40: chave explicita ou sha256 de {tool,args,caller} sort_keys; cache lido em _cache_get L77-82 antes de executar; hit retorna resultado cacheado com dedupeHit:True e audita dedupe_hit (turnosPoupados=1) L83-88. CONFIRMADO.
- Financeiro/aprovacao NUNCA executam - OPERATOR_REQUIRED = {"deploy_janela.sh","tools_install.sh","verificar.sh"} L27-28; _run_one L52-58 retorna operatorRequired sem spawnar subprocess e audita a recusa. CONFIRMADO.
- TOOLBASH_ENABLED=0 desliga - enabled() L31-32; checado no topo de _run_one L49-50 e em handle_intents L134-135 (retorna toolbash_disabled para toda a leva). CONFIRMADO.
- Timeout por tool - TOOL_TIMEOUTS = {"trail_tail.sh":20,"mission_cost.sh":20,"code_find.sh":30} L25, default 30s L24; aplicado em subprocess.run(..., timeout=timeout) L110-112; TimeoutExpired capturado L117-119 e resultado de erro tambem e cacheado (liveness honesta) L120-124. CONFIRMADO.

## 2. Prova E2E propria (executor rodado pelo auditor, 4 intents: 2 leituras + repeticoes)

```json
[
 {"ok":true,"tool":"code_find.sh","dedupeKey":"b044fe3a908e9a84abeb3af393ee0fea","dedupeHit":true,"latenciaMs":95,"exitCode":0},
 {"ok":true,"tool":"trail_tail.sh","dedupeKey":"ab099ebdd225a04faee8c9e2d4f01c13","dedupeHit":true,"latenciaMs":86,"exitCode":0},
 {"ok":true,"tool":"code_find.sh","dedupeKey":"b044fe3a908e9a84abeb3af393ee0fea","dedupeHit":true,"latenciaMs":95,"exitCode":0},
 {"ok":true,"tool":"code_find.sh","dedupeKey":"b044fe3a908e9a84abeb3af393ee0fea","dedupeHit":true,"latenciaMs":95,"exitCode":0}
]
```

Trilha apos a prova: {"eventos": 24, "dedupeHits": 13, "turnosPoupados": 20}. code_find.sh e trail_tail.sh executaram ok (exit 0) com padrao/missionId validos; a mesma intent repetida caiu no cache (dedupeHit=true) - dedupe provado independentemente do supervisor.

## 3. Fio no consumer (scripts/orchestrator-consumer.py ~1322-1340)

- Entrada type=tool_intent interceptada antes das pistas legadas; importa toolbash e chama handle_intents([payload]) (L1327-1330).
- Resultado NAO volta pra fila: a entrada e consumida (consumed_fps.add(_entry_fingerprint(entry)) L1337) e o resultado vai para o result-summary do ciclo (action:"promoted", campo toolbash com o retorno completo, L1331-1336). Em excecao: action:"gated" com TOOLBASH_ERROR (liveness honesta, L1338-1341).
- Flag de desligar respeitada indiretamente: com TOOLBASH_ENABLED=0 o executor retorna toolbash_disabled (ok=false) e a entrada ainda e consumida como promoted com reason toolbash=toolbash_disabled - a pista nao executa nada, mas a entrada sai da fila (comportamento aceitavel, documentar).

## 4. Veredito honesto

A pista funciona como desenhada: guardas presentes e eficazes, dedupe comprovado em execucao real, trilha de auditoria consistente, erro real propagado sem mascarar. Porem NAO esta em producao: o patch do consumer e scripts/toolbash.py estao UNCOMMITTED (git status -s: M scripts/orchestrator-consumer.py, ?? scripts/toolbash.py, ?? toolbash-audit.jsonl) e o consumer legado em execucao (PID 2483531) roda codigo sem o patch - ate commit + restart controlado, nenhuma tool_intent da fila e processada pela pista.

Riscos encontrados:
1. Race em _cache_put sob paralelismo: na primeira leva paralela do auditor, os.replace falhou com FileNotFoundError no .tmp (dir runs/toolbash-cache ausente/recriado concorrentemente entre makedirs e replace), derrubando a intent com excecao nao tratada em handle_intents (f.result() propaga). Recomendo: makedirs sob o _lock e try/except OSError em _cache_put. Falha real de concorrencia.
2. Cache em disco sem TTL/invalidacao: resultado de leitura pode ficar defasado para sempre sob a mesma dedupeKey.
3. Chave de dedupe explicita colide trivialmente entre callers diferentes se reutilizada.
4. Entradas tool_intent malformadas (sem tool) retornam unknown_tool e sao consumidas como promoted - silenciosamente descartadas da fila.

Marcador: AUDIT-TOOLBASH-OK (pista integra em codigo; pendencias: commit do patch, restart do consumer, correcao da race do cache).
