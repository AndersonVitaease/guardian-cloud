#!/usr/bin/env python3
"""CLI runs_resumo.py — tabela de todas as runs do harness (mais recente primeiro)."""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))


def _ultima_resumo(trail_path):
    """Lê a última linha _resumo do trail; None se não houver."""
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


def _coletar_runs(base_dir):
    """Escaneia <base_dir>/run-*/ e <base_dir>/<missao>/run-*/ (1 nível)."""
    runs = []
    if not os.path.isdir(base_dir):
        return runs
    for nome in sorted(os.listdir(base_dir)):
        caminho = os.path.join(base_dir, nome)
        if not os.path.isdir(caminho):
            continue
        if nome.startswith("run-"):
            runs.append(caminho)
        else:
            try:
                for sub in sorted(os.listdir(caminho)):
                    if sub.startswith("run-"):
                        sub_path = os.path.join(caminho, sub)
                        if os.path.isdir(sub_path):
                            runs.append(sub_path)
            except OSError:
                pass
    return runs


def resumo_runs(base_dir, limite=20):  # marker: def resumo_runs
    """resumo_runs(base_dir, limite=20) -> lista de runs resumidas."""
    # marker: def resumo_runs
    """resumo_runs — marker def resumo_runs: escaneia runs e retorna resumo (mais recente primeiro)."""
    """Retorna lista de dicts (mais recente primeiro) com resumo de cada run."""
    if not os.path.isdir(base_dir):
        print(f"erro: diretório inexistente: {base_dir}", file=sys.stderr)
        sys.exit(1)
    itens = []
    for run_dir in _coletar_runs(base_dir):
        trail = os.path.join(run_dir, "harness-trail.jsonl")
        r = _ultima_resumo(trail)
        if r:
            ts = r.get("ts", "")
            try:
                dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                data_brt = dt.astimezone(BRT).strftime("%Y-%m-%d %H:%M:%S BRT")
            except ValueError:
                data_brt = ts
            custo = r.get("custo") or {}
            itens.append({
                "dir": run_dir,
                "data_brt": data_brt,
                "veredito": r.get("veredito") or "EM ANDAMENTO",
                "turnos": r.get("turnos"),
                "custo_usd": custo.get("usd"),
                "stop_conditions": r.get("stop_conditions_cumpridas"),
                "missao": os.path.basename(os.path.dirname(run_dir))
                if os.path.basename(os.path.dirname(run_dir)) != "runs" else "-",
            })
        else:
            itens.append({
                "dir": run_dir,
                "data_brt": "-",
                "veredito": "EM ANDAMENTO",
                "turnos": None,
                "custo_usd": None,
                "stop_conditions": None,
                "missao": os.path.basename(os.path.dirname(run_dir))
                if os.path.basename(os.path.dirname(run_dir)) != "runs" else "-",
            })
    itens.sort(key=lambda x: os.path.basename(x["dir"]), reverse=True)
    return itens[:limite]


def _imprimir_tabela(itens):
    if not itens:
        print("nenhuma run encontrada.")
        return
    header = f"{'data BRT':<22} | {'veredito':<12} | {'turnos':>6} | {'custo_usd':>10} | {'stop-cond':>9} | missão/dir"
    print(header)
    print("-" * len(header))
    for it in itens:
        turnos = it["turnos"] if it["turnos"] is not None else "-"
        custo = f"{it['custo_usd']:.6f}" if it["custo_usd"] is not None else "-"
        sc = it["stop_conditions"] or "-"
        rel = os.path.relpath(it["dir"], ".")
        print(f"{it['data_brt']:<22} | {it['veredito']:<12} | {turnos:>6} | {custo:>10} | {sc:>9} | {rel}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Resumo de todas as runs do harness.")
    ap.add_argument("--base-dir", default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runs"))
    ap.add_argument("--limite", type=int, default=20)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    itens = resumo_runs(args.base_dir, limite=args.limite)
    if args.json:
        print(json.dumps(itens, ensure_ascii=False, indent=2))
    else:
        _imprimir_tabela(itens)


if __name__ == "__main__":
    main()
