#!/usr/bin/env bash
# code_slice.sh arquivo, ini, fim — fatia de arquivo (max 120 linhas) com
# total_lines. Realpath nas raizes (bloqueia symlink fora); recusa binario e
# segredo (.env,*key*,*secret*,*token*,*credential*,auth*.json). Envelope
# anti-injecao em lines (untrusted/notice, neutralizacao).
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
start=$(date +%s%N)
ARGS=("$@")
f="${1:-}"; ini="${2:-}"; fim="${3:-}"
fail(){ tb_fail code_slice "$1" "$start" "${ARGS[@]}"; }
case "$ini" in ''|*[!0-9]*) fail INVALID_RANGE;; esac
case "$fim" in ''|*[!0-9]*) fail INVALID_RANGE;; esac
[ "$ini" -ge 1 ] || fail INVALID_RANGE
[ "$fim" -ge "$ini" ] || fail INVALID_RANGE
OUT=$(python3 - "$f" "$ini" "$fim" <<'PY'
import json, os, sys
f, ini, fim = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])

def fail(code):
    print(json.dumps({"ok": False, "tool": "code_slice", "error": code}, separators=(",", ":")))
    sys.exit(0)

roots = [os.path.realpath(r) for r in os.environ.get(
    "ALLOWED_ROOTS",
    "/root/.hermes/plugins:/opt/mission-events:/home/worker:/opt/memoryos:/root/.hermes/notes:/root/.hermes/cache/delegation:/root/.hermes/agent-hooks").split(":") if r]
if not os.path.isfile(f):
    fail("FILE_NOT_FOUND")
rp = os.path.realpath(f)
if not any(rp == r or rp.startswith(r + os.sep) for r in roots):
    fail("PATH_OUTSIDE_ROOTS")
base = os.path.basename(rp).lower()
if (base == ".env" or base.endswith(".env") or any(s in base for s in
        ("key", "secret", "token", "credential")) or base.startswith("auth") and base.endswith(".json")):
    fail("SECRET_FILE")
with open(rp, "rb") as fh:
    raw = fh.read(200000)
if b"\0" in raw:
    fail("BINARY_FILE")
with open(rp, encoding="utf-8", errors="replace") as fh:
    all_lines = fh.read().splitlines()
total = len(all_lines)
requested_end = fim
truncated = False
if fim - ini + 1 > 120:
    fail("RANGE_TOO_LARGE")
try:
    sys.path.insert(0, os.environ.get("TB_LIB_PATH", ""))
    from _lib import tb_neutralize as neutral, tb_notice
    notice = tb_notice()
except Exception:
    def neutral(s):
        return "".join(c for c in s if c in "\n\t" or not ord(c) < 32)
    notice = ""
lines = [neutral(all_lines[i - 1]) for i in range(ini, min(fim, total) + 1)]
print(json.dumps({"ok": True, "tool": "code_slice", "file": rp, "start": ini, "end": fim,
                  "total_lines": total, "truncated": truncated, "requested_end": requested_end, "untrusted": True, "notice": notice,
                  "lines": lines}, separators=(",", ":")))
PY
)
tb_emit code_slice "$OUT" "$start" "${ARGS[@]}"
