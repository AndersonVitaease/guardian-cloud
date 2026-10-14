#!/usr/bin/env python3
# GB-SUITE-CFG-01: prova hermetica do patch cura-missao-fechar.patch
import json, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ORIG = os.path.join(HERE, "original-missao_fechar.sh")
PATCH = os.path.join(HERE, "cura-missao-fechar.patch")

def fail(msg):
    print("PROVA-FALHOU:", msg); sys.exit(1)

def setup(tmp):
    dst = os.path.join(tmp, "missao_fechar.sh")
    shutil.copy(ORIG, dst)
    r = subprocess.run(["patch", "-p0", dst, PATCH], capture_output=True, text=True, cwd=tmp)
    if r.returncode != 0:
        fail("patch nao aplicou: " + r.stderr)
    r = subprocess.run(["bash", "-n", dst], capture_output=True, text=True)
    if r.returncode != 0:
        fail("bash -n falhou: " + r.stderr)
    return dst

def extrair_logica(dst):
    src = open(dst).read()
    ini = src.index('SUITE_CMD="${SUITE_CMD:-')
    fim = src.index('if [ "$APPLY" = "1" ] && [ "$SUITE_OK" = "0" ]')
    return src[ini:fim]

def rodar_suite(tmp, bloco, rc, custom=False):
    repo = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(repo, "tests"), exist_ok=True)
    subprocess.run(["git", "init", "-q", repo], check=True)
    stub = os.path.join(tmp, "stub-pytest")
    with open(stub, "w") as f:
        f.write("#!/bin/sh\nexit %d\n" % rc)
    os.chmod(stub, 0o755)
    env_cmd = "/usr/bin/python3 -m pytest tests/ -q" if not custom else "exit 1"
    pydir = os.path.join(tmp, "pybin")
    os.makedirs(pydir, exist_ok=True)
    # stub de sudo (hermetico): ignora "-u worker"; se o comando e a suite
    # pytest default, executa o stub-pytest com o RC desejado (sem rede,
    # sem pytest real); caso contrario executa o comando como esta.
    sudo = os.path.join(pydir, "sudo")
    with open(sudo, "w") as f:
        f.write('#!/bin/sh\n[ "$1" = "-u" ] && shift 2\n'
                'case "$*" in *pytest*) exec "%s" ;; esac\nexec "$@"\n' % stub)
    os.chmod(sudo, 0o755)
    script = ("set -u\nMISSION_ID=PROVA\nBASE_REPO=%s\nAPPLY=1\nSUITE_CMD=\"%s\"\n"
              "PATH=%s:$PATH\n%s\n"
              'echo "SUITE_OK=$SUITE_OK"\necho "RESSALVAS_RAW=$RESSALVAS_RAW"\n'
              % (repo, env_cmd, pydir, bloco))
    r = subprocess.run(["bash", "-c", script], capture_output=True, text=True,
                       env={**os.environ, "PATH": pydir + ":" + os.environ["PATH"]})
    out = {}
    for line in r.stdout.splitlines():
        if line.startswith("SUITE_OK="): out["suite_ok"] = line.split("=",1)[1]
        if line.startswith("RESSALVAS_RAW="): out["ressalvas"] = line.split("=",1)[1]
    out["stderr"] = r.stderr
    return out

def main():
    tmp = tempfile.mkdtemp(prefix="gb-suite-cfg-01-")
    try:
        dst = setup(tmp)
        bloco = extrair_logica(dst)
        r5 = rodar_suite(tmp, bloco, 5)
        if r5.get("suite_ok") != "1": fail("RC5 deveria ser suite_ok=1, got %r" % r5)
        res = json.loads(r5.get("ressalvas", "[]"))
        if not res or res[0].get("tipo") != "SUITE_VAZIA": fail("RC5 sem ressalva SUITE_VAZIA: %r" % r5)
        if "SUITE_VAZIA" not in r5.get("stderr", ""): fail("RC5 sem stderr tipado")
        r1 = rodar_suite(tmp, bloco, 1)
        if r1.get("suite_ok") != "0": fail("RC1 deveria ser suite_ok=0, got %r" % r1)
        r0 = rodar_suite(tmp, bloco, 0)
        if r0.get("suite_ok") != "1": fail("RC0 deveria ser suite_ok=1, got %r" % r0)
        if json.loads(r0.get("ressalvas", "[]")) != []: fail("RC0 nao deveria ter ressalvas")
        r5c = rodar_suite(tmp, bloco, 5, custom=True)
        if r5c.get("suite_ok") != "0": fail("RC5 custom deveria ser suite_ok=0, got %r" % r5c)
        print("GB-SUITE-CFG-01-PROVA-OK")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

if __name__ == "__main__":
    main()