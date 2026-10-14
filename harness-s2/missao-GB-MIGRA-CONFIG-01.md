# MISSÃO GB-MIGRA-CONFIG-01 — artefatos de migração das 16 config para a rota mecanico

Entrega: MIGRACAO-CONFIG/ (unit mecanico-missao@.service, patch-consumer.md com dead-letter tipado, patch-ordens-guard.md alinhado à ORD-MECANICO-ROTA-01, inventario.json).

```harness-stop
cmd cd /home/worker/harness-s2 && test -f MIGRACAO-CONFIG/mecanico-missao@.service
cmd cd /home/worker/harness-s2 && grep -q dead_letter MIGRACAO-CONFIG/patch-consumer.md
```
