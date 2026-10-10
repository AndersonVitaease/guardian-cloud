#!/usr/bin/env bash
# proc_peek.sh pid - leitura read-only de /proc/<pid>: cmdline, cwd, uptime_s,
# lock. NUNCA mata/sinaliza. Falha tipada NO_SUCH_PID. Exit 0 sempre.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
start=$(date +%s%N)
ARGS=("$@")
pid="${1:-}"
fail(){ tb_fail proc_peek "$1" "$start" "${ARGS[@]}"; }
case "$pid" in ''|*[!0-9]*) fail NO_SUCH_PID;; esac
[ "$pid" -ge 1 ] || fail NO_SUCH_PID
OUT=$(python3 - "$pid" <<'PY'
import json, os, sys
pid = sys.argv[1]
p = "/proc/" + pid

def fail(code):
    print(json.dumps({"ok": False, "tool": "proc_peek", "error": code}, separators=(",", ":")))
    sys.exit(0)

if not os.path.isdir(p):
    fail("NO_SUCH_PID")
try:
    cmdline = open(p + "/cmdline", "rb").read().replace(b"\0", b" ").decode("utf-8", errors="replace").strip()
except OSError:
    fail("NO_SUCH_PID")
try:
    cwd = os.readlink(p + "/cwd")
except OSError:
    cwd = None
uptime_s = None
try:
    with open("/proc/uptime") as fh:
        uptime_s = float(fh.read().split()[0])
except OSError:
    pass
lock = False
try:
    import fcntl
    fd = os.open(p, os.O_RDONLY | os.O_NONBLOCK)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        lock = True
    os.close(fd)
except OSError:
    pass
print(json.dumps({"ok": True, "tool": "proc_peek", "pid": int(pid), "cmdline": cmdline,
                  "cwd": cwd, "uptime_s": uptime_s, "lock": lock}, separators=(",", ":")))
PY
)
tb_emit proc_peek "$OUT" "$start" "${ARGS[@]}"
