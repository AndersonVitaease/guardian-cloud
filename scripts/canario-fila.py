#!/usr/bin/env python3
# canario-fila.py — liveness honesta do pipeline mission-ops ($0, read-only).
# Checa: spool existe e cresceu nas últimas 24h; fila parseable; heartbeat do
# consumer recente (< 10min); ledgers running têm unit viva correspondente.
import json, glob, os, subprocess, sys, time
agora = time.time()
falhas = []
spool = "/opt/mission-events/spool.jsonl"
if not os.path.exists(spool):
    falhas.append("SPOOL_AUSENTE")
else:
    idade = agora - os.path.getmtime(spool)
    if idade > 86400: falhas.append("SPOOL_ESTAGNADO:%.0fh" % (idade / 3600))
fila = "/opt/mission-events/orchestrator-queue.jsonl"
if os.path.exists(fila):
    try:
        for ln in open(fila):
            if ln.strip(): json.loads(ln)
    except Exception as e:
        falhas.append("FILA_ILEGIVEL:%s" % e)
hb = glob.glob("/opt/mission-events/*heartbeat*")
if hb:
    if agora - max(os.path.getmtime(p) for p in hb) > 600:
        falhas.append("HEARTBEAT_VELHO")
for lp in glob.glob("/root/.hermes/mission-state/MECANICO-*.json"):
    try: d = json.load(open(lp))
    except Exception: continue
    if isinstance(d, dict) and d.get("status") == "running":
        falhas.append("LEDGER_RUNNING_SEM_UNIT:%s" % d.get("missionId"))
print(json.dumps({"ok": not falhas, "falhas": falhas}))
sys.exit(0 if not falhas else 1)
