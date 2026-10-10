#!/usr/bin/env python3
# prova_lens.py - prova da missao RD-ORQD-LENS-01 (roda como worker).
import json, subprocess, sys

def last_json_line(cmd, timeout=20):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    lines = [l for l in (p.stdout or "").splitlines() if l.strip()]
    if not lines:
        raise RuntimeError("stdout vazio (exit=%d)" % p.returncode)
    return json.loads(lines[-1])

try:
    d = last_json_line(["bash", "tools-bash/orq_status.sh"])
except Exception as e:
    print("FALHA orq_status: %s" % e); sys.exit(1)
if not d.get("ok"):
    print("FALHA orq_status ok!=true: %s" % d); sys.exit(1)
if d.get("total", 0) < 1:
    print("FALHA orq_status total<1: %s" % d); sys.exit(1)
states_ok = ("running", "queued", "passed", "needs_human", "cancelled")
if not any(v > 0 for k, v in d.get("por_state", {}).items() if k in states_ok):
    print("FALHA orq_status sem state conhecido: %s" % d); sys.exit(1)
print("orq_status por_state: %s" % json.dumps(d.get("por_state")))

try:
    r = last_json_line(["bash", "tools-bash/runs_status.sh"])
except Exception as e:
    print("FALHA runs_status: %s" % e); sys.exit(1)
if not r.get("ok"):
    print("FALHA runs_status ok!=true: %s" % r); sys.exit(1)
runs = r.get("runs") or []
if not any(x.get("orq") is True for x in runs):
    print("FALHA runs_status sem entrada orq=true: %s" % r); sys.exit(1)
print("runs_status: encontrou run orq- (orq:true)")

print("PROVA-ORQD-LENS-01-OK")
sys.exit(0)
