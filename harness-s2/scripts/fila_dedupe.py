#!/usr/bin/env python3
"""Dedupe de fila JSONL: mantém a 1ª ocorrência de cada intent id.

Standalone. Nunca toca a fila em modo dry-run (default).
"""
import argparse
import json
import os
import sys
import time


def dedupe(fila_path):
    """Lê a fila jsonl, mantém a 1ª ocorrência de cada id. NÃO muta nada."""
    antes = 0
    corrompidas = 0
    vistos = set()
    linhas = []
    try:
        with open(fila_path, "r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                line = raw.rstrip("\n")
                if not line.strip():
                    corrompidas += 1
                    continue
                antes += 1
                try:
                    obj = json.loads(line)
                    iid = obj.get("id")
                except (ValueError, AttributeError):
                    corrompidas += 1
                    continue
                if iid is None or iid in vistos:
                    continue
                vistos.add(iid)
                linhas.append(line)
    except OSError as e:
        raise FileNotFoundError(f"arquivo nao legivel: {fila_path}: {e}")
    unicos = len(linhas)
    return {
        "antes": antes,
        "unicos": unicos,
        "duplicadas": antes - unicos - corrompidas,
        "corrompidas": corrompidas,
        "linhas": linhas,
    }


def aplicar(fila_path, backup=True):
    """Aplica dedupe atomicamente (tmp no mesmo dir + os.replace)."""
    res = dedupe(fila_path)
    diretorio = os.path.dirname(os.path.abspath(fila_path))
    backup_path = None
    if backup:
        backup_path = f"{fila_path}.bak-{int(time.time())}"
        with open(fila_path, "rb") as src, open(backup_path, "wb") as dst:
            dst.write(src.read())
    tmp = os.path.join(diretorio, f".dedupe-tmp-{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(res["linhas"]))
        if res["linhas"]:
            f.write("\n")
    os.replace(tmp, fila_path)
    res["arquivo"] = fila_path
    res["backup"] = backup_path
    return res


def main(argv=None):
    p = argparse.ArgumentParser(description="Dedupe de fila JSONL por intent id.")
    p.add_argument("--fila", required=True, help="caminho da fila jsonl")
    p.add_argument("--apply", action="store_true", help="aplica (default: dry-run)")
    p.add_argument("--json", action="store_true", help="saida em JSON")
    p.add_argument("--no-backup", action="store_true", help="sem .bak no --apply")
    args = p.parse_args(argv)
    if not os.path.isfile(args.fila):
        print(f"ERRO: arquivo nao encontrado: {args.fila}", file=sys.stderr)
        return 1
    try:
        if args.apply:
            res = aplicar(args.fila, backup=not args.no_backup)
        else:
            res = dedupe(args.fila)
    except (OSError, FileNotFoundError) as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    else:
        print(
            f"antes={res['antes']} unicos={res['unicos']} "
            f"duplicadas={res['duplicadas']} corrompidas={res['corrompidas']}"
        )
        if res.get("arquivo"):
            print(f"arquivo={res['arquivo']} backup={res.get('backup')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())