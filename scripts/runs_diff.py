#!/usr/bin/env python3
"""CLI: comparação entre 2 harness-trail.jsonl."""
import json, sys


def _metricas(trail_path):
    try:
        with open(trail_path, encoding="utf-8") as f:
            linhas = [l for l in f.read().splitlines() if l.strip()]
    except OSError:
        linhas = []
    eventos = []
    for l in linhas:
        try:
            eventos.append(json.loads(l))
        except json.JSONDecodeError:
            pass
    lat = sorted(e["latencia_ms"] for e in eventos if e.get("tool") == "llm" and "latencia_ms" in e)
    p50 = lat[len(lat) // 2] if lat else 0
    custo = sum(e.get("custo_usd", 0.0) for e in eventos)
    turnos = max((e.get("turno", 0) for e in eventos), default=0)
    return turnos, custo, p50


def diff_runs(trail_a, trail_b):
    ta, ca, pa = _metricas(trail_a)
    tb, cb, pb = _metricas(trail_b)
    dc = cb - ca
    dc_s = f"{dc:.6f}".replace(".", ",")
    return (f"A: {ta} turnos ${ca:.6f} p50={pa}ms | B: {tb} turnos ${cb:.6f} p50={pb}ms | "
            f"Δturnos={tb - ta} Δcusto={dc_s}")


def main(argv):
    if len(argv) < 3:
        print("uso: runs_diff.py <trail_a> <trail_b>", file=sys.stderr)
        return 2
    print(diff_runs(argv[1], argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
