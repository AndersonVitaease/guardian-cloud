#!/usr/bin/env python3
"""CLI custo_dia.py — total gasto por dia (hora de Brasília), lido dos trails."""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))


def _ultima_resumo(trail_path):
    try:
        with open(trail_path, encoding="utf-8") as f:
            ultima = None
            for linha in f:
                linha = linha.strip()
                if not linha:
                    continue
                try:
                    d = json.loads(linha)
                except ValueError:
                    continue
                if d.get("tool") == "_resumo":
                    ultima = d
            return ultima
    except OSError:
        return None


def _coletar_trails(base_dir):
    """Escaneia <base_dir>/**/run-*/harness-trail.jsonl (1 nível de missão)."""
    trails = []
    if not os.path.isdir(base_dir):
        return trails
    for nome in sorted(os.listdir(base_dir)):
        caminho = os.path.join(base_dir, nome)
        if not os.path.isdir(caminho):
            continue
        candidatos = []
        if nome.startswith("run-"):
            candidatos.append(caminho)
        else:
            try:
                for sub in sorted(os.listdir(caminho)):
                    if sub.startswith("run-"):
                        candidatos.append(os.path.join(caminho, sub))
            except OSError:
                pass
        for run_dir in candidatos:
            trail = os.path.join(run_dir, "harness-trail.jsonl")
            if os.path.isfile(trail):
                trails.append(trail)
    return trails


def _fmt_usd(valor):
    """Formato pt-BR: vírgula decimal, 5 casas."""
    return f"$ {valor:.5f}".replace(".", ",")


def custo_dia(base_dir):
    """custo_dia(base_dir) -> lista de linhas por dia (mais recente primeiro)."""
    dias = {}
    for trail in _coletar_trails(base_dir):
        resumo = _ultima_resumo(trail)
        if not resumo:
            continue
        ts = resumo.get("ts")
        custo = resumo.get("custo") or {}
        usd = custo.get("usd")
        if not ts or usd is None:
            continue
        try:
            dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue
        dia_brt = dt.astimezone(BRT).strftime("%Y-%m-%d")
        veredito = resumo.get("veredito", "?")
        d = dias.setdefault(dia_brt, {"n": 0, "usd": 0.0, "PASS": 0, "FAIL": 0})
        d["n"] += 1
        d["usd"] += float(usd)
        d[veredito] = d.get(veredito, 0) + 1
    linhas = []
    for dia in sorted(dias, reverse=True):
        d = dias[dia]
        linhas.append(
            f"{dia} | {d['n']} runs | {_fmt_usd(d['usd'])} | "
            f"PASS {d.get('PASS', 0)} FAIL {d.get('FAIL', 0)}"
        )
    return linhas


def main(argv=None):
    ap = argparse.ArgumentParser(description="Total gasto por dia (BRT) dos trails.")
    ap.add_argument("--base-dir", default="runs/")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    linhas = custo_dia(args.base_dir)
    if args.json:
        print(json.dumps(linhas, ensure_ascii=False, indent=2))
    if not linhas:
        print("SEM RUNS")
        return 1
    for linha in linhas:
        print(linha)
    return 0


if __name__ == "__main__":
    sys.exit(main())