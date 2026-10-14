#!/usr/bin/env python3
"""Prova E2E hermetica DESP-STOP-01: lint recusa stop com interpretador incompativel.

Cenario 1 (contrato errado): stop `python3 scripts/prova-x.sh` => lint aponta
STOP_INTERPRETE_ESTRANHO com o nome do arquivo; despachar_missao.py recusaria com
LINT_RECUSADO (lint bloqueante roda ANTES de parsear stops - RD-HARN-LINT-ENFORCE-01).
Cenario 2 (contrato certo): stop `bash scripts/prova-x.sh` / `python3 prova-x.py`
=> lint nao aponta o codigo novo.
Ultima linha: DESP-STOP-01-PROVA-OK
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LINT = os.path.join(HERE, "scripts", "contrato_lint.py")
DESP = os.path.join(HERE, "scripts", "despachar_missao.py")

ERRADO = """# MISSAO DESP-STOP-01-PROVA-ERRADA - x

## Stops
```harness-stop
cmd cd /tmp && python3 scripts/prova-x.sh
```
"""

CERTO = """# MISSAO DESP-STOP-01-PROVA-CERTA - x

## Stops
```harness-stop
cmd cd /tmp && bash scripts/prova-x.sh
cmd cd /tmp && python3 prova-x.py
```
"""


def codigos(texto):
    sys.path.insert(0, os.path.join(HERE, "scripts"))
    import contrato_lint
    return {a["codigo"]: a for a in contrato_lint.lint(texto)}


def main():
    falhas = []

    c = codigos(ERRADO)
    if "STOP_INTERPRETE_ESTRANHO" not in c:
        falhas.append("contrato errado nao gerou STOP_INTERPRETE_ESTRANHO")
    else:
        a = c["STOP_INTERPRETE_ESTRANHO"]
        if a.get("severidade") != "erro":
            falhas.append("STOP_INTERPRETE_ESTRANHO nao e erro")
        if "prova-x.sh" not in a.get("msg", ""):
            falhas.append("msg nao cita o arquivo: %r" % a.get("msg"))

    c2 = codigos(CERTO)
    if "STOP_INTERPRETE_ESTRANHO" in c2:
        falhas.append("contrato certo foi marcado STOP_INTERPRETE_ESTRANHO")

    with tempfile.TemporaryDirectory() as td:
        p_err = os.path.join(td, "errado.md")
        p_ok = os.path.join(td, "certo.md")
        open(p_err, "w", encoding="utf-8").write(ERRADO)
        open(p_ok, "w", encoding="utf-8").write(CERTO)
        r1 = subprocess.run([sys.executable, LINT, p_err], capture_output=True, text=True)
        r0 = subprocess.run([sys.executable, LINT, p_ok], capture_output=True, text=True)
        if r1.returncode != 1:
            falhas.append("lint CLI exit=%d no contrato errado (esperado 1)" % r1.returncode)
        try:
            j = json.loads(r1.stdout)
            if not any(a["codigo"] == "STOP_INTERPRETE_ESTRANHO" for a in j):
                falhas.append("lint CLI JSON sem STOP_INTERPRETE_ESTRANHO")
        except Exception as e:
            falhas.append("lint CLI JSON invalido: %s" % e)
        if r0.returncode != 0:
            falhas.append("lint CLI exit=%d no contrato certo (esperado 0)" % r0.returncode)

    src = open(DESP, encoding="utf-8").read()
    if 'fail("LINT_RECUSADO"' not in src:
        falhas.append("despachar_missao.py sem caminho LINT_RECUSADO")
    lint_pos = src.find("LINT_RECUSADO")
    parse_pos = src.find("parse_stop_conditions")
    if lint_pos == -1 or parse_pos == -1 or lint_pos > parse_pos:
        falhas.append("lint nao roda antes de parsear stops")

    for f in falhas:
        print("FALHA: %s" % f)
    if falhas:
        print("DESP-STOP-01-PROVA-FALHOU")
        sys.exit(1)
    print("cenario errado: STOP_INTERPRETE_ESTRANHO (erro, cita arquivo) OK")
    print("cenario certo: sem STOP_INTERPRETE_ESTRANHO OK")
    print("CLI: exit 1 errado / exit 0 certo OK")
    print("despacho: LINT_RECUSADO antes de parsear stops OK")
    print("DESP-STOP-01-PROVA-OK")


if __name__ == "__main__":
    main()
