#!/usr/bin/env bash
# runs_status.sh — estado das runs vivas (units systemd harness-*).
# Para cada unit: active/result/execStatus (systemctl show), cwd (do --cwd do
# ExecStart), verdict/reason/stops/turn/cost_usd (harness-pane.log mais recente
# sob o cwd, profundidade max 3), commit (git do repo), tab (herdr tab list).
# Ordenado por ultima atividade. Leitura SO sob /home/worker.
# Uso: runs_status.sh [--only-active] [N=20]
# JSON 1 linha; exit 0 sempre; falha tipada {ok:false,error:SYSTEMCTL_FAILED|BAD_ARGS}.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
start=$(date +%s%N)
OUT=$(python3 - "$@" <<'PY'
import json, os, re, subprocess, sys

def fail(err):
    print(json.dumps({"ok": False, "tool": "runs_status", "error": err},
                     separators=(",", ":")))
    sys.exit(0)

args = sys.argv[1:]
only_active = False
limit = 20
nargs = 0
for a in args:
    if a == "--only-active":
        only_active = True
    elif a.isdigit() and int(a) >= 1:
        limit = int(a)
        nargs += 1
    else:
        fail("BAD_ARGS")
if nargs > 1:
    fail("BAD_ARGS")

def run(cmd, timeout=5):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout or "", p.stderr or ""
    except Exception:
        return 127, "", ""

rc, out, _ = run(["systemctl", "list-units", "--all", "--no-legend", "harness-*"])
if rc != 0:
    fail("SYSTEMCTL_FAILED")
units = []
for line in out.splitlines():
    parts = line.split()
    if parts and (parts[0].startswith("harness-") or parts[0].endswith(".service")):
        u = parts[0]
        if not u.endswith(".service") and u.startswith("harness-"):
            u = u + ".service"
        units.append(u)
units = sorted(set(units))

def parse_props(text):
    props = {}
    for line in text.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            props[k.strip()] = v.strip()
    return props

def find_pane_log(cwd):
    best = None
    best_mt = 0
    base = cwd.rstrip("/")
    try:
        for root, dirs, files in os.walk(base):
            rel = os.path.relpath(root, base)
            depth = 0 if rel == "." else rel.count(os.sep) + 1
            if depth > 3:
                dirs[:] = []
                continue
            if "harness-pane.log" in files:
                p = os.path.join(root, "harness-pane.log")
                try:
                    mt = os.stat(p).st_mtime
                except OSError:
                    continue
                if mt > best_mt:
                    best_mt = mt
                    best = p
    except Exception:
        return None, 0
    return best, best_mt

def parse_pane(path):
    verdict = reason = stops = None
    turn = cost = None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return verdict, reason, stops, turn, cost
    for line in text.splitlines():
        m = re.search(r"VEREDITO (PASS|FAIL)", line)
        if m:
            verdict = m.group(1)
        m = re.search(r"motivo=([^\s|]+)", line)
        if m:
            reason = m.group(1)
        m = re.search(r"stop-conditions (\d+/\d+)", line)
        if m:
            stops = m.group(1)
        m = re.search(r"\bturno (\d+)\b", line)
        if m:
            turn = int(m.group(1))
        m = re.search(r"cum \$([0-9.]+)", line)
        if m:
            cost = float(m.group(1))
        m = re.search(r"VEREDITO (?:PASS|FAIL) \|.*?\| \$([0-9.]+) de", line)
        if m:
            cost = float(m.group(1))
    return verdict, reason, stops, turn, cost

def get_commit(repo):
    if not repo:
        return None
    rc, out, _ = run(["git", "-C", repo, "log", "--oneline", "-1"])
    if rc != 0 or not out.strip():
        return None
    return out.strip()[:80]

def get_tab(mission_id):
    rc, out, _ = run(["herdr", "tab", "list"])
    if rc != 0:
        return None
    try:
        d = json.loads(out)
        tabs = d.get("result", {}).get("tabs", [])
    except Exception:
        return None
    needle = "RUN:%s#" % mission_id
    for t in tabs:
        lbl = t.get("label") or ""
        if needle in lbl:
            return lbl
    return None

runs = []
for unit in units:
    rc, out, _ = run(["systemctl", "show", unit,
                      "-p", "ActiveState,Result,ExecMainStatus,ExecStart"])
    if rc != 0:
        continue
    props = parse_props(out)
    active_state = props.get("ActiveState") or "unknown"
    cwd = None
    m = re.search(r"--cwd (\S+)", props.get("ExecStart", ""))
    if m:
        cwd = m.group(1)
    mission_id = os.path.basename(cwd.rstrip("/")) if cwd else None
    if not mission_id:
        m = re.match(r"harness-(.+?)(?:-s\d+)?(?:\.service)?$", unit)
        mission_id = m.group(1) if m else unit
    verdict = reason = stops = None
    turn = cost = None
    commit = tab = None
    last_mt = 0
    roots = [r for r in os.environ.get("RUNS_STATUS_ROOTS", "/home/worker:/opt/memoryos").split(":") if r]
    if cwd and any(cwd == r or cwd.startswith(r.rstrip("/") + "/") for r in roots):
        pane, last_mt = find_pane_log(cwd)
        if pane:
            verdict, reason, stops, turn, cost = parse_pane(pane)
        repo = None
        if "/runs/" in cwd:
            repo = cwd.split("/runs/")[0]
        commit = get_commit(repo)
    tab = get_tab(mission_id)
    is_active = active_state == "active"
    if only_active and not is_active:
        continue
    runs.append({
        "missionId": mission_id, "unit": unit, "active": is_active,
        "activeState": active_state,
        "result": props.get("Result"),
        "execStatus": props.get("ExecMainStatus"),
        "cwd": cwd, "verdict": verdict, "reason": reason,
        "stops": stops, "turn": turn, "cost_usd": cost,
        "commit": commit, "tab": tab, "_mt": last_mt,
    })

runs.sort(key=lambda r: r["_mt"], reverse=True)
for r in runs:
    r.pop("_mt", None)
runs = runs[:limit]
print(json.dumps({"ok": True, "tool": "runs_status", "count": len(runs),
                  "runs": runs}, separators=(",", ":")))
PY
)
tb_emit runs_status "$OUT" "$start"
