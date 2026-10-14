#!/usr/bin/env bash
# queue_eye.sh — quem consome a fila do orquestrador (read-only, 0 LLM).
# Lista daemons orqd.daemon / orchestrator-consumer (pid, user, --db, --queue,
# --sock via /proc/*/cmdline); para cada fila em /opt/mission-events
# (orchestrator-queue.jsonl e variantes .js*): bytes, mtime BRT, profundidade
# (linhas JSON válidas de missão), dispatched sem veredito, consumidores (fds).
# Uso: queue_eye.sh [--only daemons|filas]
# JSON 1 linha; exit 0 sempre; falha tipada {ok:false,error:BAD_ARGS}.
# Env de teste: QUEUE_EYE_DIR (dir de filas), QUEUE_EYE_PROC (dump de cmdlines,
# formato: "PID<TAB>arg1<US>arg2<US>..." por linha, US=\x1f).
# NUNCA escreve em /opt; NUNCA mata processo.
set -u
source /opt/mission-events/tools-bash/_lib.sh
start=$(date +%s%N)
OUT=$(python3 - "$@" <<'PY'
import json, os, sys, time

def fail(err):
    print(json.dumps({"ok": False, "tool": "queue_eye", "error": err},
                     separators=(",", ":")))
    sys.exit(0)

only = None
args = sys.argv[1:]
if len(args) == 2 and args[0] == "--only" and args[1] in ("daemons", "filas"):
    only = args[1]
elif args:
    fail("BAD_ARGS")

US = "\x1f"
proc_dump = os.environ.get("QUEUE_EYE_PROC")
queue_dir = os.environ.get("QUEUE_EYE_DIR") or "/opt/mission-events"

# ---- 1. processos ----
procs = []  # {pid,user,cmd:[...]}
if proc_dump:
    try:
        with open(proc_dump, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue
                pid, _, rest = line.partition("\t")
                procs.append({"pid": pid, "user": "?", "cmd": rest.split(US)})
    except OSError:
        pass
else:
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open("/proc/%s/cmdline" % entry, "rb") as f:
                raw = f.read()
            cmd = [a.decode("utf-8", "replace") for a in raw.split(b"\0") if a]
            if not cmd:
                continue
            user = "?"
            uid = None
            try:
                with open("/proc/%s/status" % entry, encoding="utf-8", errors="replace") as f:
                    for ln in f:
                        if ln.startswith("Uid:"):
                            uid = ln.split()[1]
                            break
            except OSError:
                pass
            if uid is not None:
                try:
                    import pwd
                    user = pwd.getpwuid(int(uid)).pw_name
                except Exception:
                    user = uid
            procs.append({"pid": entry, "user": user, "cmd": cmd})
        except OSError:
            continue

def flag_val(cmd, flag):
    for i, a in enumerate(cmd):
        if a == flag and i + 1 < len(cmd):
            return cmd[i + 1]
        if a.startswith(flag + "="):
            return a[len(flag) + 1:]
    return None

daemons = []
consumers = []
for p in procs:
    cmd = p["cmd"]
    joined = " ".join(cmd)
    base = os.path.basename(cmd[0]) if cmd else ""
    if "orqd.daemon" in joined or base == "orqd.daemon":
        daemons.append({"pid": p["pid"], "user": p["user"],
                        "db": flag_val(cmd, "--db"),
                        "queue": flag_val(cmd, "--queue"),
                        "sock": flag_val(cmd, "--sock")})
    elif "orchestrator-consumer" in joined:
        consumers.append({"pid": p["pid"], "user": p["user"],
                          "queue": flag_val(cmd, "--queue")})

# ---- 2. filas ----
filas = []
try:
    names = sorted(os.listdir(queue_dir))
except OSError:
    names = []
for name in names:
    if name != "orchestrator-queue.jsonl" and not name.startswith("orchestrator-queue.js"):
        continue
    path = os.path.join(queue_dir, name)
    if not os.path.isfile(path):
        continue
    try:
        st = os.stat(path)
    except OSError:
        continue
    profundidade = 0
    dispatched_sem_veredito = 0
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if not isinstance(obj, dict) or "missionId" not in obj:
                    continue
                profundidade += 1
                if obj.get("status") == "dispatched" and not obj.get("verdict"):
                    dispatched_sem_veredito += 1
    except OSError:
        pass
    # ---- 3. consumidores via /proc/*/fd ----
    fds = set()
    if not proc_dump:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                fd_dir = "/proc/%s/fd" % entry
                for fd in os.listdir(fd_dir):
                    try:
                        target = os.readlink(os.path.join(fd_dir, fd))
                    except OSError:
                        continue
                    if target == path:
                        fds.add(int(entry))
            except OSError:
                continue
    else:
        for p in procs:
            if path in p["cmd"]:
                try:
                    fds.add(int(p["pid"]))
                except ValueError:
                    pass
    for c in consumers:
        if c.get("queue") == path:
            try:
                fds.add(int(c["pid"]))
            except ValueError:
                pass
    mtime_brt = time.strftime("%Y-%m-%dT%H:%M:%S-03:00", time.gmtime(st.st_mtime - 3 * 3600))
    filas.append({"arquivo": path, "bytes": st.st_size, "mtime_brt": mtime_brt,
                  "profundidade": profundidade,
                  "dispatched_sem_veredito": dispatched_sem_veredito,
                  "consumidores": sorted(fds)})

queue_counts = {}
for d in daemons:
    if d["queue"]:
        queue_counts[d["queue"]] = queue_counts.get(d["queue"], 0) + 1
duplicado = any(v >= 2 for v in queue_counts.values())

out = {"ok": True, "tool": "queue_eye", "daemons": daemons, "filas": filas,
       "duplicado": duplicado, "modo": "scan"}
if only == "daemons":
    out.pop("filas")
elif only == "filas":
    out.pop("daemons")
print(json.dumps(out, separators=(",", ":")))
PY
)
tb_emit queue_eye "$OUT" "$start"