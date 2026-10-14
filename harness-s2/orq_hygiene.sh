#!/usr/bin/env bash
# orq_hygiene.sh — varredura de higiene do orquestrador (0 LLM, só leitura).
# WATCHERS_ZUMBI | ORQD_DUPLICADO | FECHO_FORA_WORKTREE
# Uso: orq_hygiene.sh [--only watchers|orqd|worktree] [--fix] [--proc-dump <arquivo>]
# JSON 1 linha; exit 0 sempre; falha tipada {ok:false,error:BAD_ARGS}.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
start=$(date +%s%N)
OUT=$(python3 - "$@" <<'PY'
import json, os, re, subprocess, sys

def fail(err):
    print(json.dumps({"ok": False, "tool": "orq_hygiene", "error": err},
                     separators=(",", ":")))
    sys.exit(0)

args = sys.argv[1:]
only = None
fix = False
proc_dump = None
i = 0
while i < len(args):
    a = args[i]
    if a == "--fix":
        fix = True
    elif a == "--only":
        i += 1
        if i >= len(args) or args[i] not in ("watchers", "orqd", "worktree"):
            fail("BAD_ARGS")
        if only is not None:
            fail("BAD_ARGS")
        only = args[i]
    elif a in ("watchers", "orqd", "worktree"):
        if only is not None:
            fail("BAD_ARGS")
        only = a
    elif a == "--proc-dump":
        i += 1
        if i >= len(args):
            fail("BAD_ARGS")
        proc_dump = args[i]
    else:
        fail("BAD_ARGS")
    i += 1

def run(cmd, timeout=10):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout or "", p.stderr or ""
    except Exception:
        return 127, "", ""

procs = []
if proc_dump:
    try:
        with open(proc_dump, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line.strip():
                    continue
                parts = line.split(" ", 2)
                if len(parts) == 3:
                    procs.append((parts[0], parts[1], parts[2]))
    except Exception:
        fail("PROC_DUMP_UNREADABLE")
else:
    rc, out, _ = run(["ps", "-eo", "pid,user,args", "--no-headers"])
    if rc != 0:
        fail("PS_FAILED")
    for line in out.splitlines():
        parts = line.strip().split(" ", 2)
        if len(parts) == 3:
            procs.append((parts[0], parts[1], parts[2]))

watchers = []
orqd = []
worktree = []

if only in (None, "watchers"):
    for pid, user, cmd in procs:
        if "bash" not in cmd or "-lic" not in cmd:
            continue
        m = re.search(r"pgrep\s+-f\s+(?:'([^']*)'|\"([^\"]*)\"|(\S+))", cmd)
        if not m:
            continue
        pat = m.group(1) or m.group(2) or m.group(3) or ""
        if not pat:
            continue
        try:
            hit = bool(re.search(pat, cmd))
        except re.error:
            hit = pat in cmd
        if hit:
            watchers.append({"pid": pid, "user": user,
                             "padrao": pat[:200], "cmdline": cmd[:300]})

if only in (None, "orqd"):
    by_ws = {}
    for pid, user, cmd in procs:
        if "orqd.daemon" not in cmd:
            continue
        mws = re.search(r"--workspace\s+(\S+)", cmd)
        ws = mws.group(1) if mws else "(default)"
        mdb = re.search(r"--db\s+(\S+)", cmd)
        mq = re.search(r"--queue\s+(\S+)", cmd)
        by_ws.setdefault(ws, []).append({
            "pid": pid, "user": user,
            "db": mdb.group(1) if mdb else None,
            "queue": mq.group(1) if mq else None,
            "cmdline": cmd[:300]})
    for ws, lst in by_ws.items():
        if len(lst) > 1:
            orqd.append({"workspace": ws, "processos": lst,
                         "alerta": "ORQD_DUPLICADO"})

if only in (None, "worktree"):
    bad_re = re.compile(r"^(\.orqd-.*|\.wt-rd-.*|RELATORIO-RD-ORQD-.*)$")
    if os.path.isdir("/home/worker"):
        for name in sorted(os.listdir("/home/worker")):
            path = os.path.join("/home/worker", name)
            if not os.path.isdir(path):
                continue
            rc, out, _ = run(["git", "-C", path, "rev-parse",
                              "--is-inside-work-tree"], timeout=5)
            if rc != 0 or out.strip() != "true":
                continue
            rc, out, _ = run(["git", "-C", path, "ls-files", "--others",
                              "--exclude-standard"], timeout=10)
            if rc != 0:
                continue
            hits = [l for l in out.splitlines()
                     if bad_re.match(os.path.basename(l))][:10]
            if hits:
                worktree.append({"repo": path, "arquivos": hits,
                                 "sugestao": "mover p/ worktree próprio"})

fix_aplicado = []
if fix:
    me = os.getuid()
    for w in watchers:
        try:
            import pwd
            pw = pwd.getpwnam(w["user"])
            if pw.pw_uid == me:
                rcs, _, _ = run(["kill", w["pid"]], timeout=5)
                if rcs == 0:
                    fix_aplicado.append({"tipo": "watcher", "pid": w["pid"]})
            else:
                w["dica"] = ("processo de outro usuário (%s); apenas relatado"
                             % w["user"])
        except Exception:
            pass

print(json.dumps({"ok": True, "tool": "orq_hygiene", "watchers": watchers,
                  "orqd": orqd, "worktree": worktree,
                  "fix_aplicado": fix_aplicado,
                  "modo": "fix" if fix else "scan"},
                 separators=(",", ":")))
PY
)
ok=1; error=""
case "$OUT" in *'"ok":false'*)
  ok=0
  error=$(printf '%s' "$OUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("error",""))' 2>/dev/null || printf 'EMIT_INVALIDO')
  ;; esac
tb_audit orq_hygiene "$(tb_join "$@")" "$ok" "$error" "$start" || :
printf '%s\n' "$OUT"
exit 0
# ORQ-HYGIENE-01
