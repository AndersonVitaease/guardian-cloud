#!/usr/bin/env bash
# code_find.sh padrao, diretorio, N=30 — busca de codigo com rg, limite de
# resultados. JSON 1 linha, exit 0 sempre, falha tipada. Raizes via
# ALLOWED_ROOTS (default fixo). Ignora .git, node_modules, *.log, *.jsonl,
# *.bak*, __pycache__. Padrao passado via -e (nunca opcao). Envelope
# anti-injecao em matches (untrusted/notice, neutralizacao).
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
start=$(date +%s%N)
ARGS=("$@")
pat="${1:-}"; dir="${2:-}"; n="${3:-20}"
fail(){ tb_fail code_find "$1" "$start" "${ARGS[@]}"; }
[ -n "$pat" ] || fail INVALID_PATTERN
[ ${#pat} -le 200 ] || fail INVALID_PATTERN
case "$pat" in -*) fail INVALID_PATTERN;; esac
case "$n" in ''|*[!0-9]*) fail INVALID_N:"uso: code_find.sh PADRAO DIR N";; esac
[ "$n" -ge 1 ] && [ "$n" -le 200 ] || fail INVALID_N:"uso: code_find.sh PADRAO DIR N"
[ -n "$dir" ] || dir="${CODE_FIND_DEFAULT_DIR:-/opt/mission-events}"
OUT=$(python3 - "$pat" "$dir" "$n" <<'PY'
import json, os, subprocess, sys
pat, dirn, n = sys.argv[1], sys.argv[2], int(sys.argv[3])

def fail(code):
    print(json.dumps({"ok": False, "tool": "code_find", "error": code}, separators=(",", ":")))
    sys.exit(0)

roots = [os.path.realpath(r) for r in os.environ.get(
    "ALLOWED_ROOTS",
    "/root/.hermes/plugins:/opt/mission-events:/home/worker:/opt/memoryos:/root/.hermes/notes:/root/.hermes/cache/delegation:/root/.hermes/agent-hooks").split(":") if r]
rp = os.path.realpath(dirn)
if not any(rp == r or rp.startswith(r + os.sep) for r in roots):
    fail("INVALID_DIR")
if not os.path.isdir(rp) and not os.path.isfile(rp):
    fail("INVALID_DIR")
RG = "/root/.hermes/tools/ripgrep-15.2.0-linux-x64/rg"
if not os.path.isfile(RG):
    RG = "rg"
excl = []
for g in ("!.git", "!node_modules", "!*.log", "!*.jsonl", "!*.bak*", "!__pycache__"):
    excl += ["-g", g]
try:
    p = subprocess.run([RG, "--no-messages", "--no-heading", "-n", "-H"] + excl + ["-e", pat, "--", rp],
                       capture_output=True, text=True, timeout=10)
except Exception:
    fail("FIND_FAILED")
try:
    sys.path.insert(0, os.environ.get("TB_LIB_PATH", ""))
    from _lib import tb_neutralize as neutral, tb_notice
    notice = tb_notice()
except Exception:
    def neutral(s):
        return "".join(c for c in s if c in "\n\t" or not ord(c) < 32)[:200]
    notice = ""
matches, truncated = [], False
for line in (p.stdout or "").splitlines():
    head, sep, rest = line.partition(":")
    ln, sep2, text = rest.partition(":")
    if not sep or not sep2 or not ln.isdigit():
        continue
    if not (len(matches) < n):
        truncated = True
        break
    matches.append({"file": os.path.basename(rp) if head == rp else os.path.relpath(head, rp), "line": int(ln), "text": neutral(text)})
print(json.dumps({"ok": True, "tool": "code_find", "pattern": pat, "dir": rp,
                  "untrusted": True, "notice": notice,
                  "count": len(matches), "matches": matches, "truncated": truncated},
                 separators=(",", ":")))
PY
)
tb_emit code_find "$OUT" "$start" "${ARGS[@]}"
