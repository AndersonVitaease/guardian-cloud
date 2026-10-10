#!/usr/bin/env bash
# file_peek.sh arquivo - leitura de arquivo (max 2048 bytes) nas raizes
# permitidas (mesmas de code_slice.sh). Realpath nas raizes; recusa binario e
# segredo (.env,*key*,*secret*,*token*,*credential*,auth*.json). Envelope
# anti-injecao em content (untrusted/notice).
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
start=$(date +%s%N)
ARGS=("$@")
f="${1:-}"
fail(){ tb_fail file_peek "$1" "$start" "${ARGS[@]}"; }
[ -n "$f" ] || fail FILE_NOT_FOUND
OUT=$(python3 - "$f" <<'PY'
import json, os, sys
f = sys.argv[1]

def fail(code):
    print(json.dumps({"ok": False, "tool": "file_peek", "error": code}, separators=(",", ":")))
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
    fail("SECRET_PATH")
try:
    raw = open(rp, "rb").read(2049)
except OSError:
    fail("FILE_NOT_READABLE")
if len(raw) > 2048:
    fail("FILE_TOO_LARGE")
if b"\0" in raw:
    fail("FILE_BINARY")
content = raw.decode("utf-8", errors="replace")
try:
    sys.path.insert(0, os.environ.get("TB_LIB_PATH", ""))
    from _lib import tb_neutralize as neutral, tb_notice
    notice = tb_notice()
except Exception:
    def neutral(s):
        return "".join(c for c in s if c in "\n\t" or not ord(c) < 32)
    notice = ""
content = neutral(content)
print(json.dumps({"ok": True, "tool": "file_peek", "path": rp, "bytes": len(raw),
                  "untrusted": True, "notice": notice, "content": content},
                 separators=(",", ":")))
PY
)
tb_emit file_peek "$OUT" "$start" "${ARGS[@]}"
