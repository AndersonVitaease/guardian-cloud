#!/usr/bin/env bash
# queue_peek.sh — estado verdadeiro da fila do orquestrador lido NO HOST
# (/opt/mission-events): bytes, entradas, ids/tipos, heartbeat do consumer
# (idade s, vivo<=60s), breaker, mtime. Fixtures via env: QUEUE_PATH,
# HEARTBEAT_PATH, BREAKER_PATH. JSON 1 linha; exit 0 sempre.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
start=$(date +%s%N)
OUT=$(python3 - <<'PY'
import json, os, sys, time
qp = os.environ.get("QUEUE_PATH", "/opt/mission-events/orchestrator-queue.jsonl")
hp = os.environ.get("HEARTBEAT_PATH", "/opt/mission-events/orchestrator-consumer.heartbeat.json")
bp = os.environ.get("BREAKER_PATH", "/opt/mission-events/breaker-state.json")

def readj(path):
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                return json.load(f)
        except Exception:
            return None
    return None

bytes_ = os.path.getsize(qp) if os.path.isfile(qp) else 0
items = []
if os.path.isfile(qp):
    try:
        with open(qp, encoding="utf-8", errors="replace") as f:
            for l in f:
                l = l.strip()
                if not l:
                    continue
                try:
                    o = json.loads(l)
                except Exception:
                    continue
                items.append({"id": o.get("id"), "tipo": o.get("tipo")})
    except Exception:
        pass
hb = readj(hp)
age_s = None
alive = False
if isinstance(hb, dict):
    ts = hb.get("tsEpoch")
    if isinstance(ts, (int, float)):
        age_s = round(max(0.0, time.time() - float(ts)), 3)
        alive = age_s <= 60
brk = readj(bp) or {}
print(json.dumps({"ok": True, "tool": "queue_peek",
                  "queue": {"path": qp, "bytes": bytes_, "entries": len(items),
                            "items": items[:100]},
                  "consumer": {"path": hp, "alive": alive, "age_s": age_s},
                  "breaker": brk, "now_epoch": round(time.time(), 1),
                  "mtime": int(os.path.getmtime(qp)) if os.path.isfile(qp) else None},
                 separators=(",", ":")))
PY
)
tb_emit queue_peek "$OUT" "$start"
