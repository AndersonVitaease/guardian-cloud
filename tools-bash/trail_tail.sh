#!/usr/bin/env bash
# trail_tail.sh missionId, N=10 — últimas N linhas da trilha da missão +
# veredito do ledger. JSON 1 linha, exit 0 sempre, falha tipada.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
start=$(date +%s%N)
ARGS=("$@")
mid="${1:-}"; n="${2:-10}"
fail(){
  local e="$1"
  tb_audit trail_tail "$(tb_join "${ARGS[@]}")" 0 "$e" "$start" || :
  printf '{"ok":false,"tool":"trail_tail","missionId":"%s","error":"%s"}\n' "$mid" "$e"
  exit 0
}
[ -n "$mid" ] && [ ${#mid} -le 64 ] || fail INVALID_MISSION_ID
case "$mid" in *[!A-Za-z0-9._-]*) fail INVALID_MISSION_ID;; esac
case "$n" in ''|*[!0-9]*) fail INVALID_N;; esac
[ "$n" -ge 1 ] && [ "$n" -le 1000 ] || fail INVALID_N
SD=$(tb_state_dir)
ED="${MISSION_EVENTS_DIR:-/opt/mission-events}"
OUT=$(python3 - "$mid" "$n" "$SD" "$ED" <<'PY'
import json, os, sys
mid, n, sd, ed = sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4]
def fail(code):
    print(json.dumps({"ok": False, "tool": "trail_tail", "missionId": mid,
                      "error": code}, separators=(",", ":")))
    sys.exit(0)
led = os.path.join(sd, mid + ".json")
if not os.path.isfile(led):
    fail("LEDGER_NOT_FOUND")
try:
    with open(led, encoding="utf-8", errors="replace") as fh:
        d = json.load(fh)
except Exception:
    fail("LEDGER_UNREADABLE")
ev = os.path.join(sd, "events.jsonl")
mev = os.path.join(sd, mid + ".events.tail.jsonl")
lines = []
src = "events"
if not os.path.isfile(ev) and os.path.isfile(mev):
    ev = mev
if os.path.isfile(ev):
    with open(ev, errors="replace") as fh:
        lines = [l.rstrip("\n") for l in fh if mid in l]
if not lines:
    # fallback: harness-trail.jsonl mais recente em tentativa-*/run-*/
    # sob runs/<mid> a partir do cwd do ledger (sobe ate runs/<mid>).
    cwd = d.get("cwd")
    cands = []
    if isinstance(cwd, str) and cwd.strip():
        base = os.path.join(os.path.realpath(cwd), "runs", mid)
        if os.path.isdir(base):
            for t in sorted(os.listdir(base)):
                tdir = os.path.join(base, t)
                if not (t.startswith("tentativa-") and os.path.isdir(tdir)):
                    continue
                for r in sorted(os.listdir(tdir)):
                    rdir = os.path.join(tdir, r)
                    if not (r.startswith("run-") and os.path.isdir(rdir)):
                        continue
                    p = os.path.join(rdir, "harness-trail.jsonl")
                    if os.path.isfile(p):
                        try:
                            cands.append((os.stat(p).st_mtime, p))
                        except OSError:
                            pass
    if cands:
        cands.sort()
        p = cands[-1][1]
        with open(p, errors="replace") as fh:
            raw = [l.rstrip("\n") for l in fh if l.strip()]
        wrapped = []
        for l in raw[-n:]:
            try:
                obj = json.loads(l)
            except Exception:
                obj = None
            if isinstance(obj, dict):
                obj["source"] = "harness-trail"
                wrapped.append(json.dumps(obj, separators=(",", ":")))
            else:
                wrapped.append(json.dumps({"source": "harness-trail", "raw": l},
                                          separators=(",", ":")))
        if wrapped:
            lines = wrapped
            src = "harness-trail"
verdict = None
ve = d.get("verified_e2e")
if isinstance(ve, dict):
    verdict = ve.get("verdict")
tail = lines[-n:]
print(json.dumps({"ok": True, "tool": "trail_tail", "missionId": mid,
                  "lines": tail, "count": len(tail), "source": src,
                  "status": d.get("status"), "verdict": verdict},
                 separators=(",", ":")))
PY
)
tb_emit trail_tail "$OUT" "$start" "${ARGS[@]}"
