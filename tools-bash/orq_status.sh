#!/usr/bin/env bash
# orq_status.sh — estado das missoes do ORQD via db (socket unix, somente leitura).
# Uso: orq_status.sh [SOCK] — sock default /run/orqd-live/orqd.sock, env ORQD_SOCK override.
# JSON 1 linha; exit 0 sempre; falha tipada {ok:false,error:ORQD_INDISPONIVEL}.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
start=$(date +%s%N)
OUT=$(python3 - "$@" <<'PY'
import json, os, sys

def fail(detail):
    msg = str(detail).replace("\n", " ")[:200]
    print(json.dumps({"ok": False, "tool": "orq_status",
                      "error": "ORQD_INDISPONIVEL", "detail": msg},
                     separators=(",", ":")))
    sys.exit(0)

sock = os.environ.get("ORQD_SOCK") or "/run/orqd-live/orqd.sock"
if len(sys.argv) > 1:
    sock = sys.argv[1]

try:
    sys.path.insert(0, "/home/worker/orqd")
    from orqd import api
    resp = api.request(sock, {"cmd": "list"})
except PermissionError as e:
    fail(e)
except OSError as e:
    fail(e)
except Exception as e:
    fail(e)

if not isinstance(resp, dict) or not resp.get("ok"):
    fail("api_sem_ok")

missions = resp.get("missions") or []
por_state = {}
for m in missions:
    st = m.get("state") or "unknown"
    por_state[st] = por_state.get(st, 0) + 1
ativas = [m for m in missions if m.get("state") in ("running", "queued")]
try:
    ativas.sort(key=lambda m: m.get("created_at") or "", reverse=True)
except Exception:
    pass
ativas = [{"id": m.get("id"), "state": m.get("state"), "unit": m.get("unit"),
           "detail": m.get("detail")} for m in ativas[:20]]
print(json.dumps({"ok": True, "tool": "orq_status", "sock": sock,
                  "total": len(missions), "por_state": por_state,
                  "ativas": ativas}, separators=(",", ":")))
PY
)
tb_emit orq_status "$OUT" "$start"
