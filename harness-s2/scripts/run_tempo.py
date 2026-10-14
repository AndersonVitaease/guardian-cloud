#!/usr/bin/env python3
"""CLI: tempo de uma run a partir do harness-trail.jsonl."""
import json, sys
from datetime import datetime


def _parse_ts(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _fmt_wall(seg):
    m, s = divmod(int(seg), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def tempo_da_run(trail_path):
    """Retorna string PTBR com métricas da run; 'SEM TRAIL' se vazio/inexistente."""
    try:
        with open(trail_path, encoding="utf-8") as f:
            linhas = [l for l in f.read().splitlines() if l.strip()]
    except OSError:
        return "SEM TRAIL"
    if not linhas:
        return "SEM TRAIL"
    eventos = []
    for l in linhas:
        try:
            eventos.append(json.loads(l))
        except json.JSONDecodeError:
            pass
    if not eventos:
        return "SEM TRAIL"
    lat = sorted(e["latencia_ms"] for e in eventos if e.get("tool") == "llm" and "latencia_ms" in e)
    p50 = lat[len(lat) // 2] if lat else 0
    mx = max(lat) if lat else 0
    tools = sum(1 for e in eventos if e.get("tool") not in ("llm", "_inicio", "_resumo", "_stop_check"))
    custo = sum(e.get("custo_usd", 0.0) for e in eventos)
    try:
        wall = (_parse_ts(eventos[-1]["ts"]) - _parse_ts(eventos[0]["ts"])).total_seconds()
    except (KeyError, ValueError):
        wall = 0
    turnos = max((e.get("turno", 0) for e in eventos), default=0)
    out = (f"turnos={turnos} | wall={_fmt_wall(wall)} (1º→último evento) | "
           f"llm_p50={p50}ms | llm_max={mx}ms | tools={tools} chamadas | custo=${custo:.6f}")
    if eventos[-1].get("tool") == "_resumo":
        out += f" | veredito={eventos[-1].get('veredito', '?')}"
    return out


def main(argv):
    if len(argv) < 2:
        print("uso: run_tempo.py <trail.jsonl>", file=sys.stderr)
        return 2
    out = tempo_da_run(argv[1])
    print(out)
    return 1 if out == "SEM TRAIL" else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
