#!/usr/bin/env python3
"""Verificador da CANÁRIA MÉDIA (HARNESS-SPRINT2-01) — roda no cwd da run.

uso: check_canary.py --seed N [dir]     exit 0 = PASS; exit 1 = FAIL (motivos no stderr)

Tema escolhido por seed % 3 (mesma tabela do contrato). Checa:
  1. utilitário CLI do tema com os 3 subcomandos (--help exit 0 + sondas de I/O exatas
     + subcomando inválido sai != 0);
  2. ≥10 testes unitários coletados, todos verdes (pytest);
  3. README.md citando cada subcomando;
  4. verify.json de si mesmo (schema cmd+file, campo mission) — cada cmd com o exit
     esperado e cada file existente.
"""
import argparse
import json
import os
import re
import subprocess
import sys

THEMES = {
    0: {"tool": "textkit.py", "probes": [
        (["conta", "a b  c"], "3"), (["inverte", "abc"], "cba"), (["maiusculas", "abc"], "ABC")]},
    1: {"tool": "numkit.py", "probes": [
        (["soma", "1", "2", "3.5"], "6.5"), (["media", "2", "4"], "3"), (["maximo", "3", "9", "2"], "9")]},
    2: {"tool": "listkit.py", "probes": [
        (["ordena", "c", "a", "b"], "a b c"), (["unicos", "a", "b", "a", "c"], "a b c"),
        (["inverte", "c", "a", "b"], "b a c")]},
}


def sh(cmd, cwd, timeout=120):
    return subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), capture_output=True,
                          text=True, timeout=timeout)


def check(seed, d):
    errs = []
    theme = THEMES[seed % 3]
    tool = theme["tool"]
    subs = [p[0][0] for p in theme["probes"]]

    # 1. CLI
    if not os.path.isfile(os.path.join(d, tool)):
        return [f"{tool} ausente"]
    for sub in subs:
        r = sh([sys.executable, tool, sub, "--help"], d)
        if r.returncode != 0:
            errs.append(f"{tool} {sub} --help exit={r.returncode}")
    for args, want in theme["probes"]:
        r = sh([sys.executable, tool, *args], d)
        got = r.stdout.strip()
        if r.returncode != 0 or got != want:
            errs.append(f"sonda {args}: exit={r.returncode} stdout={got!r} esperado={want!r}")
    r = sh([sys.executable, tool, "naoexiste"], d)
    if r.returncode == 0:
        errs.append("subcomando inválido deveria sair != 0")

    # 2. testes
    r = sh([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], d, timeout=300)
    tail = (r.stdout.strip().splitlines() or [""])[-1]
    m = re.search(r"(\d+) passed", tail)
    passed = int(m.group(1)) if m else 0
    if r.returncode != 0 or re.search(r"failed|error", tail) or passed < 10:
        errs.append(f"pytest: exit={r.returncode} passed={passed} (mín 10) tail={tail!r}")

    # 3. README
    readme = os.path.join(d, "README.md")
    if not os.path.isfile(readme):
        errs.append("README.md ausente")
    else:
        txt = open(readme, encoding="utf-8", errors="replace").read()
        miss = [s for s in subs if s not in txt]
        if miss:
            errs.append(f"README.md não cita: {miss}")

    # 4. verify.json
    try:
        v = json.load(open(os.path.join(d, "verify.json"), encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return errs + [f"verify.json inválido: {e}"]
    if not isinstance(v.get("mission"), str) or not v["mission"]:
        errs.append("verify.json sem campo mission")
    cmds, files = v.get("cmd"), v.get("file")
    if not isinstance(cmds, list) or not cmds or not isinstance(files, list) or not files:
        errs.append("verify.json precisa de listas não vazias cmd e file")
        return errs
    for c in cmds:
        if not isinstance(c, dict) or "run" not in c:
            errs.append(f"cmd sem run: {c}")
            continue
        r = sh(c["run"], d, timeout=int(c.get("timeout", 120)))
        if r.returncode != int(c.get("expect_exit", 0)):
            errs.append(f"verify cmd {c['run']!r}: exit={r.returncode} esperado={c.get('expect_exit', 0)}")
    for f in files:
        p = f.get("path") if isinstance(f, dict) else None
        if not p or not os.path.isfile(os.path.join(d, p)):
            errs.append(f"verify file ausente: {f}")
    return errs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("dir", nargs="?", default=".")
    a = ap.parse_args(argv)
    errs = check(a.seed, os.path.abspath(a.dir))
    for e in errs:
        print("FAIL:", e, file=sys.stderr)
    print("CANARIA PASS" if not errs else f"CANARIA FAIL ({len(errs)})")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
