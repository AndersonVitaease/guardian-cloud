#!/usr/bin/env bash
# entrega_verify.sh MISSIONID — verifica entrega de uma missao. Uma linha JSON, exit 0 sempre.
set -u
MISSION_ID="${1:-}"
export ENTREGA_MISSION_ID="$MISSION_ID"
python3 - <<'PY'
import json, os, re, subprocess, sys, time

t0 = time.time()
mid = os.environ.get("ENTREGA_MISSION_ID", "")

def out(obj):
    obj.setdefault("tool", "entrega_verify")
    obj.setdefault("missionId", mid)
    obj["ms"] = int((time.time() - t0) * 1000)
    print(json.dumps(obj, ensure_ascii=False))
    sys.exit(0)

def fail(err):
    out({"ok": False, "error": err})

if not mid:
    fail("uso: entrega_verify.sh MISSIONID")

state_dir = os.environ.get("ENTREGA_STATE_DIR") or "/root/.hermes/mission-state"
ledger_path = os.path.join(state_dir, mid + ".json")
if not os.path.isfile(ledger_path):
    fail("ledger nao encontrado: " + ledger_path)
try:
    with open(ledger_path, "r", encoding="utf-8") as f:
        ledger = json.load(f)
except Exception as e:
    fail("ledger invalido: " + str(e))

wt = os.environ.get("ENTREGA_WT_OVERRIDE") or ""
if not wt:
    cwd = ledger.get("cwd") or ""
    d = cwd
    while d and d != os.path.dirname(d):
        if os.path.isdir(os.path.join(d, ".git")) or os.path.isfile(os.path.join(d, ".git")):
            wt = d
            break
        d = os.path.dirname(d)
if not wt:
    wt = "/home/worker/wt-" + mid
if not (os.path.isdir(os.path.join(wt, ".git")) or os.path.isfile(os.path.join(wt, ".git"))):
    fail("worktree sem .git: " + wt)

def git(args, timeout=30):
    return subprocess.run(["git", "-C", wt] + args, capture_output=True,
                          text=True, timeout=timeout)

faltando = []

# (a) git log -1 contem o ID
log1 = git(["log", "-1", "--pretty=%H%n%s%n%b"])
commit_com_id = log1.returncode == 0 and mid in (log1.stdout or "")
if not commit_com_id:
    faltando.append("commit_com_id")

# (b) git status: apenas untracked runs/ e __pycache__
st = git(["status", "--porcelain"])
status_ok = st.returncode == 0
if status_ok:
    for line in (st.stdout or "").splitlines():
        if not line.strip():
            continue
        code, path = line[:2], line[3:].strip()
        if code == "??":
            if not (path == "runs/" or path.startswith("runs/")
                    or path == "__pycache__" or path.startswith("__pycache__")):
                status_ok = False
        else:
            status_ok = False
if not status_ok:
    faltando.append("git_status_limpo_exceto_runs")

# (c) diff do ultimo commit
show = git(["show", "--name-only", "--pretty=format:", "HEAD"])
diff_files = [l.strip() for l in (show.stdout or "").splitlines() if l.strip()]
diff_ok = show.returncode == 0 and len(diff_files) > 0 and any(
    (not f.startswith("runs/")) and (not os.path.basename(f).startswith("missao-"))
    for f in diff_files)

# contrato: missao-ID.md no worktree ou /opt/mission-events
contract = None
for cand in (os.path.join(wt, "missao-" + mid + ".md"),
             os.path.join("/opt/mission-events", "missao-" + mid + ".md")):
    if os.path.isfile(cand):
        try:
            with open(cand, "r", encoding="utf-8") as f:
                contract = f.read()
        except Exception:
            contract = None
        break

mapa_ok = True
if contract and "## MAPA" in contract:
    citados = []
    for line in contract.splitlines():
        m = re.match(r"^\s*-\s+(\S+)\s*\|", line)
        if m:
            citados.append(m.group(1))
    for c in citados:
        base = os.path.basename(c)
        hit = any(f == c or f.endswith("/" + c) or os.path.basename(f) == base
                  for f in diff_files)
        if not hit:
            mapa_ok = False
if not (diff_ok and mapa_ok):
    faltando.append("diff_toca_arquivos")

# (d) re-executar stops do bloco harness-stop como uid worker
stops_total = 0
stops_verdes = 0
if contract:
    lines = contract.splitlines()
    in_block = False
    stops = []
    for line in lines:
        s = line.strip()
        if s.startswith("```harness-stop"):
            in_block = True
            continue
        if in_block and s.startswith("```"):
            in_block = False
            continue
        if in_block and s.startswith("cmd "):
            stops.append(s[4:])
    stops_total = len(stops)
    for cmd in stops:
        rc = None
        try:
            p = subprocess.run(["timeout", "20", "bash"],
                               input=cmd + "\n", cwd=wt, capture_output=True,
                               text=True, timeout=25)
            rc = p.returncode
        except Exception:
            try:
                p = subprocess.run(["timeout", "20", "bash"], input=cmd + "\n",
                                   cwd=wt, capture_output=True, text=True, timeout=25)
                rc = p.returncode
            except Exception:
                rc = None
        if rc == 0:
            stops_verdes += 1

stops_ok = stops_total > 0 and stops_verdes == stops_total
if not stops_ok:
    faltando.append("stops_reexecutados")

entregue = bool(commit_com_id and status_ok and diff_ok and mapa_ok and stops_ok)
out({
    "ok": entregue,
    "entregue": entregue,
    "checks": {
        "commit_com_id": commit_com_id,
        "git_status_limpo_exceto_runs": status_ok,
        "diff_toca_arquivos": diff_ok and mapa_ok,
        "stops_reexecutados": {"total": stops_total, "verdes": stops_verdes},
    },
    "faltando": faltando,
})
PY
