#!/usr/bin/env bash
# runs_historico.sh — histórico de runs no DISCO (units systemd somem por
# --collect; a fonte do histórico é <repo>/runs/<MISSION_ID>/.../harness-pane.log).
# Raiz default /home/worker (override por env RUNS_ROOTS, ':' separado).
# Estruturas: <repo>/runs/<ID>/tentativa-<N>/run-*/harness-pane.log e
# <repo>/runs/<ID>/run-*/harness-pane.log (sem tentativa-N).
# Extrai SOMENTE com regex (nunca executa nada do log):
#  - "[..] VEREDITO PASS | motivo=stop_condition | 9 turno(s) | $0.017476 de $0.3 | ... stop-conditions 4/4"
#  - "... turno 4 | llm | 1433ms | $0.000396 | cum $0.001541 | ..."
# Saída: {"ok":true,"tool":"runs_historico","count":N,"runs":[{missionId,
# tentativas,verdict,motivo,turnos,cost_usd,stops,finished_at,commit,repo}]}
# ordenado por finished_at desc. Leitura só sob as raizes; commit via
# subprocess com timeout. JSON 1 linha; exit 0 sempre;
# falha tipada {ok:false,error:BAD_ARGS}.
# Uso: runs_historico.sh [--since-hours H] [N=20 (max 100)]
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
start=$(date +%s%N)
OUT=$(python3 - "$@" <<'PY'
import json, os, re, subprocess, sys, time

def fail(err):
    print(json.dumps({"ok": False, "tool": "runs_historico", "error": err},
                     separators=(",", ":")))
    sys.exit(0)

args = sys.argv[1:]
since_hours = 24.0
limit = 20
i = 0
while i < len(args):
    a = args[i]
    if a == "--since-hours":
        if i + 1 >= len(args):
            fail("BAD_ARGS")
        try:
            since_hours = float(args[i + 1])
        except ValueError:
            fail("BAD_ARGS")
        i += 2
    elif a.isdigit() and int(a) >= 1:
        limit = int(a)
        i += 1
    else:
        fail("BAD_ARGS")
if limit > 100:
    limit = 100

roots = [r for r in os.environ.get("RUNS_ROOTS", "/home/worker").split(":") if r]
try:
    expanded = []
    for r in roots:
        if os.path.isdir(os.path.join(r, "runs")):
            expanded.append(r)
        else:
            for x in sorted(os.listdir(r)):
                pth = os.path.join(r, x)
                if os.path.islink(pth) or not os.path.isdir(pth):
                    continue
                if os.path.isdir(os.path.join(pth, "runs")):
                    expanded.append(pth)
    roots = expanded
except OSError:
    pass
try:
    expanded = []
    for r in roots:
        if os.path.isdir(os.path.join(r, "runs")):
            expanded.append(r)
        else:
            for x in sorted(os.listdir(r)):
                p = os.path.join(r, x)
                if os.path.islink(p) or not os.path.isdir(p):
                    continue
                if os.path.isdir(os.path.join(p, "runs")):
                    expanded.append(p)
    roots = expanded
except OSError:
    pass

def run(cmd, timeout=5):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout or "", p.stderr or ""
    except Exception:
        return 127, "", ""

def get_commit(repo):
    if not repo:
        return None
    rc, out, _ = run(["git", "-C", repo, "log", "--oneline", "-1"])
    if rc != 0 or not out.strip():
        return None
    return out.strip()[:80]

def parse_pane(path):
    verdict = reason = stops = None
    turnos = 0
    cost = None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception:
        return None, None, None, 0, None
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
            turnos = max(turnos, int(m.group(1)))
        m = re.search(r"\b(\d+) turno\(s\)", line)
        if m:
            turnos = max(turnos, int(m.group(1)))
        m = re.search(r"VEREDITO (?:PASS|FAIL) \|.*?\| \$([0-9.]+) de", line)
        if m:
            cost = float(m.group(1))
        m = re.search(r"cum \$([0-9.]+)", line)
        if m:
            if cost is None:
                cost = float(m.group(1))
            else:
                cost = max(cost, float(m.group(1)))
    return verdict, reason, stops, turnos, cost

now = time.time()
cutoff = now - since_hours * 3600.0
missions = {}  # (base, mission_id) -> {"tentativas": n, "logs": [(mt, path)]}
for root in roots:
    base = os.path.realpath(root)
    if os.environ.get("RUNS_ROOTS") is None:
        if not (base == "/home/worker" or base.startswith("/home/worker/")):
            continue
    runs_dir = os.path.join(base, "runs")
    if not os.path.isdir(runs_dir):
        continue
    try:
        missions_ids = sorted(os.listdir(runs_dir))
    except OSError:
        continue
    for mid in missions_ids:
        mdir = os.path.join(runs_dir, mid)
        if not os.path.isdir(mdir) or os.path.islink(mdir):
            continue
        try:
            level1 = sorted(os.listdir(mdir))
        except OSError:
            continue
        for e1 in level1:
            p1 = os.path.join(mdir, e1)
            if os.path.islink(p1):
                continue
            if e1.startswith("tentativa-") and os.path.isdir(p1):
                d = missions.setdefault((base, mid), {"tentativas": 0, "logs": []})
                d["tentativas"] += 1
                try:
                    level2 = sorted(os.listdir(p1))
                except OSError:
                    continue
                for e2 in level2:
                    p2 = os.path.join(p1, e2)
                    if e2.startswith("run-") and os.path.isdir(p2) and not os.path.islink(p2):
                        pane = os.path.join(p2, "harness-pane.log")
                        if os.path.isfile(pane):
                            try:
                                mt = os.stat(pane).st_mtime
                            except OSError:
                                continue
                            d["logs"].append((mt, pane))
            elif e1.startswith("run-") and os.path.isdir(p1) and not os.path.islink(p1):
                pane = os.path.join(p1, "harness-pane.log")
                if os.path.isfile(pane):
                    d = missions.setdefault((base, mid), {"tentativas": 0, "logs": []})
                    if d["tentativas"] == 0:
                        d["tentativas"] = 1
                    try:
                        mt = os.stat(pane).st_mtime
                    except OSError:
                        continue
                    d["logs"].append((mt, pane))

runs = []
for (base, mid), d in missions.items():
    if not d["logs"]:
        continue
    d["logs"].sort(key=lambda t: t[0])
    last_mt, last_pane = d["logs"][-1]
    if last_mt < cutoff:
        continue
    verdict, reason, stops, turnos, cost = parse_pane(last_pane)
    turnos_total = 0
    cost_total = 0.0
    have_cost = False
    for mt, pane in d["logs"]:
        v, r, s, t, c = parse_pane(pane)
        turnos_total += t
        if c is not None:
            cost_total += c
            have_cost = True
    commit = get_commit(base)
    finished = time.strftime("%d/%m %H:%M", time.localtime(last_mt))
    runs.append({
        "missionId": mid,
        "tentativas": d["tentativas"],
        "verdict": verdict,
        "motivo": reason,
        "turnos": turnos_total,
        "cost_usd": round(cost_total, 6) if have_cost else None,
        "stops": stops,
        "finished_at": finished,
        "commit": commit,
        "repo": os.path.basename(base),
        "_mt": last_mt,
    })

runs.sort(key=lambda r: r["_mt"], reverse=True)
for r in runs:
    r.pop("_mt", None)
runs = runs[:limit]
print(json.dumps({"ok": True, "tool": "runs_historico", "count": len(runs),
                  "runs": runs}, separators=(",", ":")))
PY
)
tb_emit runs_historico "$OUT" "$start"