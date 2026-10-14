# GB-MIGRA-CONFIG-01 — PATCH consumer (aplicar no orchestrator-consumer.py):
# no caminho CONSUMER_DISPATCH / --executar: NAO spawnar mission_run.
# Em vez disso, gravar dead-letter tipado e seguir:
#   {"kind":"dead_letter","motivo":"ROTA_ANTIGA_DESATIVADA","usar":"despachar-mecanico.sh"}
# A fila orchestrator-queue.jsonl fica SOMENTE para itens com mec_prova no payload.
