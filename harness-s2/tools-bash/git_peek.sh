#!/usr/bin/env bash
# git_peek.sh repo, subcomando (status/log/diff-stat/show-stat rev) — leitura SOMENTE
# de repo git dentro das raizes. Nunca checkout/commit/reset. Envelope
# anti-injecao em short/commits/stat (untrusted/notice, neutralizacao).
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
start=$(date +%s%N)
ARGS=("$@")
repo="${1:-}"; sub="${2:-status}"; rev="${3:-}"
fail(){ tb_fail git_peek "$1" "$start" "${ARGS[@]}"; }
[ -n "$repo" ] || fail INVALID_REPO
[ -d "$repo" ] || fail INVALID_REPO
case "$sub" in status|log|diff-stat|show-stat) ;; *) fail INVALID_SUBCOMMAND;; esac
case "$rev" in -*|*[!A-Za-z0-9._~-]*) [ -z "$rev" ] || fail INVALID_REV;; esac
OUT=$(python3 - "$repo" "$sub" "$rev" <<'PY'
import json, os, subprocess, sys
repo, sub, rev = sys.argv[1], sys.argv[2], sys.argv[3]

def fail(code):
    print(json.dumps({"ok": False, "tool": "git_peek", "error": code}, separators=(",", ":")))
    sys.exit(0)

roots = [os.path.realpath(r) for r in os.environ.get(
    "ALLOWED_ROOTS",
    "/root/.hermes/plugins:/opt/mission-events:/home/worker:/opt/memoryos").split(":") if r]
rp = os.path.realpath(repo)
if not any(rp == r or rp.startswith(r + os.sep) for r in roots):
    fail("REPO_OUTSIDE_ROOTS")
if not (os.path.isdir(os.path.join(rp, ".git"))
        or os.path.isfile(os.path.join(rp, ".git"))):
    fail("NOT_A_GIT_REPO")
try:
    sys.path.insert(0, os.environ.get("TB_LIB_PATH", ""))
    from _lib import tb_neutralize as neutral, tb_notice
    notice = tb_notice()
except Exception:
    def neutral(s):
        return "".join(c for c in s if c in "\n\t" or not ord(c) < 32)
    notice = ""

def run(*g):
    return subprocess.run(["git", "-C", rp, "-c", "core.quotepath=false", *g],
                          capture_output=True, text=True, timeout=10)

short, commits, stat = None, None, None
if sub == "status":
    p = run("status", "--short")
    if p.returncode != 0:
        fail("GIT_FAILED")
    short = [neutral(l) for l in (p.stdout or "").splitlines()[:100]]
elif sub == "log":
    p = run("log", "-10", "--oneline")
    if p.returncode != 0:
        fail("GIT_FAILED")
    commits = []
    for l in (p.stdout or "").splitlines()[:10]:
        h, _, s = l.partition(" ")
        if h:
            commits.append({"hash": h, "subject": neutral(s)})
elif sub == "diff-stat":
    p = run("diff", "--stat")
    if p.returncode != 0:
        fail("GIT_FAILED")
    stat = neutral(p.stdout or "")
else:
    p = run("show", "--stat", rev)
    if p.returncode != 0:
        fail("INVALID_REV")
    stat = neutral(p.stdout or "")
print(json.dumps({"ok": True, "tool": "git_peek", "repo": rp, "sub": sub,
                  "untrusted": True, "notice": notice,
                  "short": short, "commits": commits, "stat": stat},
                 separators=(",", ":")))
PY
)
tb_emit git_peek "$OUT" "$start" "${ARGS[@]}"
