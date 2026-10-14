#!/usr/bin/env bash
# flights.sh — runs vivos (pgrep claude|harness|mission) como lista JSON.
# [{pid,cmd}] + count. JSON 1 linha; exit 0 sempre; falha tipada PGREP_FAILED.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
start=$(date +%s%N)
OUT=$(python3 - <<'PY'
import json, subprocess, sys
try:
    p = subprocess.run(["pgrep", "-l", "-f", "claude|harness|mission"],
                       capture_output=True, text=True, timeout=5)
except Exception:
    print(json.dumps({"ok": False, "tool": "flights", "error": "PGREP_FAILED"},
                     separators=(",", ":")))
    sys.exit(0)
runs = []
for line in (p.stdout or "").splitlines():
    pid, _, cmd = line.partition(" ")
    if pid.isdigit():
        runs.append({"pid": int(pid), "cmd": cmd[:200]})
print(json.dumps({"ok": True, "tool": "flights", "runs": runs,
                  "count": len(runs)}, separators=(",", ":")))
PY
)
tb_emit flights "$OUT" "$start"
