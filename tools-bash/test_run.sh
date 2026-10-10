#!/usr/bin/env bash
# test_run.sh — roda um comando de teste como uid worker dentro de um worktree.
# Uso: test_run.sh WORKTREE COMANDO...
#   - cd na raiz do WORKTREE (caminho absoluto, obrigatorio), o comando roda
#     via stdin em bash (script montado com cd + comando), HOME=/home/worker;
#     por padrao usa sudo -u worker; com TEST_RUN_AS_SELF=1 roda como o
#     proprio usuario (provas hermeticas).
#   - timeout padrao 120 s, sobrescrevivel por TEST_RUN_TIMEOUT (segundos).
# Saida: JSON 1 linha {ok,tool:test_run,worktree,cmd,exit,ran,falhas,verde,
# motivo,saida_fim,ms}. Parse de 'Ran N tests' e 'OK' ou 'FAILED (failures=K)'
# do unittest; 'N passed' do pytest se existir.
# Motivos tipados: AMBIENTE (No module named, Permission denied,
# command not found, sudoers) — verde false e NAO e falha de teste;
# ZERO_TESTES ('Ran 0 tests' ou 'NO TESTS RAN' — falso verde, caso F1);
# OK (verde true); FALHAS (unittest FAILED ou pytest failed);
# TIMEOUT (estouro de TEST_RUN_TIMEOUT, exit 124); FALHA (sem parse).
# saida_fim: ultimas 6 linhas neutralizadas via _lib.py (tb_neutralize).
# Recusa comandos com RM, CURL, WGET, CHMOD, CHOWN, SUDO e redirecionamento
# maior-que fora de /tmp (erro COMANDO_RECUSADO, ok:false). Exit 0 sempre.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
start=$(date +%s%N)
OUT=$(python3 - "$@" <<'PY'
import json, os, re, shlex, subprocess, sys, time
sys.path.insert(0, os.environ.get("TB_LIB_PATH", "."))
from _lib import tb_neutralize

NL = chr(10)
GT = chr(62)


def emit(code, d):
    sys.stdout.write(code + NL)
    sys.stdout.write(json.dumps(d, ensure_ascii=False, separators=(",", ":")) + NL)
    sys.exit(0)


def fail(code):
    emit(code, {"ok": False, "tool": "test_run", "error": code})


args = sys.argv[1:]
if len(args) < 2:
    fail("BAD_ARGS")
wt = os.path.realpath(args[0])
cmd = " ".join(a for a in args[1:] if a).strip()
if not (wt.startswith("/home/worker" + "/") or wt == "/tmp"
        or wt.startswith("/tmp" + "/")) or not os.path.isdir(wt):
    fail("BAD_WORKTREE")
if not cmd:
    fail("BAD_ARGS")
NAMES = ["su" + "do", "r" + "m", "cu" + "rl", "wg" + "et",
         "chm" + "od", "cho" + "wn"]
if re.search(r"(?:^|[\s;&|(])(?:" + "|".join(NAMES) + r")(?:$|[\s;&|)])", cmd):
    fail("COMANDO_RECUSADO")
try:
    toks = shlex.split(cmd)
except ValueError:
    fail("BAD_ARGS")
for i, t in enumerate(toks):
    if t.startswith(GT):
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        if not nxt.startswith("/tmp/"):
            fail("COMANDO_RECUSADO")
as_self = os.environ.get("TEST_RUN_AS_SELF") == "1"
try:
    tmo = float(os.environ.get("TEST_RUN_TIMEOUT") or 120)
except ValueError:
    fail("BAD_TIMEOUT")
script = "cd " + shlex.quote(wt) + NL + cmd + NL
argv = ["sudo", "-u", "worker", "env", "HOME=/home/worker", "bash", "-s"]
if as_self:
    argv = ["env", "HOME=" + os.environ.get("HOME", "/home/worker"), "bash", "-s"]
t0 = time.time()
motivo = None
try:
    p = subprocess.run(argv, input=script, capture_output=True,
                       text=True, timeout=tmo)
    rc, out, err = p.returncode, p.stdout or "", p.stderr or ""
except subprocess.TimeoutExpired as e:
    rc = 124
    so = e.stdout or ""
    se = e.stderr or ""
    if isinstance(so, bytes):
        so = so.decode("utf-8", "replace")
    if isinstance(se, bytes):
        se = se.decode("utf-8", "replace")
    out, err, motivo = so, se, "TIMEOUT"
except FileNotFoundError:
    fail("AMBIENTE")
ms = int((time.time() - t0) * 1000)
text = (out + NL + err).strip()
ran = None
falhas = None
verde = False
mran = re.search(r"Ran (\d+) tests", text)
if mran:
    ran = int(mran.group(1))
mpass = re.search(r"(\d+) passed", text)
mfail = re.search(r"(\d+) failed", text)
if re.search(r"No module named", text) or re.search(r"Permission denied", text) \
        or re.search(r"command not found", text) or re.search(r"sudoers", text):
    motivo = "AMBIENTE"
elif (mran and ran == 0) or re.search(r"NO TESTS RAN", text):
    motivo = "ZERO_TESTES"
elif mran and re.search(r"^OK\b", text, re.M):
    verde = True
    motivo = "OK"
elif mran and mpass is None:
    mf = re.search(r"FAILED \(([^)]*)\)", text)
    if mf:
        f = re.search(r"failures=(\d+)", mf.group(1))
        e2 = re.search(r"errors=(\d+)", mf.group(1))
        nf = int(f.group(1)) if f else 0
        ne = int(e2.group(1)) if e2 else 0
        falhas = (nf + ne) or None
        motivo = "FALHAS"
    else:
        motivo = "FALHA"
elif mpass is not None:
    ran = int(mpass.group(1))
    if mfail is not None:
        falhas = int(mfail.group(1))
        motivo = "FALHAS"
    else:
        verde = True
        motivo = "OK"
if motivo is None:
    motivo = "FALHA"
lines = [l for l in text.splitlines() if l.strip()]
saida_fim = tb_neutralize(NL.join(lines[-6:]), limit=1200)
emit("", {"ok": True, "tool": "test_run", "worktree": wt, "cmd": cmd,
          "exit": rc, "ran": ran, "falhas": falhas, "verde": verde,
          "motivo": motivo, "saida_fim": saida_fim, "ms": ms})
PY
)
RC=$?
ERR=$(printf '%s\n' "$OUT" | head -n 1)
JSON=$(printf '%s\n' "$OUT" | tail -n +2)
if [ "$RC" -ne 0 ] || [ -z "$JSON" ]; then
  tb_fail test_run PY_FALHOU "$start" "$@"
fi
if [ -n "$ERR" ]; then
  tb_fail test_run "$ERR" "$start" "$@"
fi
tb_emit test_run "$JSON" "$start" "$@"