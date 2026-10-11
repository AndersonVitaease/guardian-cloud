#!/usr/bin/env python3
"""DESP-FECHO-ROBUSTO-01: reconcilia resumos /tmp/resumo-*.json com o ledger.
Para cada resumo cuja entrada no ledger ainda esteja dispatched/running,
reexecuta o fecho robusto. Imprime JSON {checked, refechados, erros}."""
import glob, json, os, subprocess, sys

LEDGER = "/home/worker/harness-s2/ledger_missoes.jsonl"
FECHAR = "/home/worker/harness-s2/scripts/fechar_missao.sh"
ABERTOS = {"dispatched", "running"}


def ledger_estado(mid):
    try:
        with open(LEDGER, encoding="utf-8") as f:
            for linha in f:
                try:
                    e = json.loads(linha)
                except json.JSONDecodeError:
                    continue
                if e.get("id") == mid or e.get("mission") == mid:
                    return e.get("status") or e.get("estado")
    except OSError:
        return None
    return None


def main():
    checked = refechados = erros = 0
    for caminho in sorted(glob.glob("/tmp/resumo-*.json")):
        mid = os.path.basename(caminho)[len("resumo-"):-len(".json")]
        if not mid:
            continue
        checked += 1
        estado = ledger_estado(mid)
        if estado in ABERTOS:
            r = subprocess.run(["bash", FECHAR, mid],
                               capture_output=True, text=True)
            if r.returncode == 0:
                refechados += 1
            else:
                erros += 1
                print("ERRO fechar %s rc=%s" % (mid, r.returncode), file=sys.stderr)
    print(json.dumps({"checked": checked, "refechados": refechados, "erros": erros}))


if __name__ == "__main__":
    main()
