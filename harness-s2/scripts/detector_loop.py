#!/usr/bin/env python3
"""Detector de loop em runs ao vivo (trail-based). PT-BR."""
import argparse
import json
import os
import sys


def detectar_loop(trail_path, janela=5):
    """Analisa harness-trail.jsonl e retorna dict com diagnóstico de loop."""
    r = {
        "em_loop": False,
        "pendentes": [],
        "ticks_novos": False,
        "turnos_sem_progresso": 0,
        "custo_acumulado": 0.0,
        "turnos": 0,
    }
    if not trail_path or not os.path.exists(trail_path) or os.path.getsize(trail_path) == 0:
        r["erro"] = "SEM TRAIL"
        return r
    stops = []
    resumo = None
    custo = 0.0
    turnos = 0
    with open(trail_path, encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            try:
                ev = json.loads(linha)
            except ValueError:
                continue
            tool = ev.get("tool")
            if tool == "_stop_check":
                stops.append(ev)
            elif tool == "_resumo":
                resumo = ev
            if "cum_usd" in ev:
                custo = ev["cum_usd"]
            if "turno" in ev:
                turnos = max(turnos, int(ev["turno"]))
    r["custo_acumulado"] = custo
    r["turnos"] = turnos
    if resumo is not None:
        r["veredito"] = resumo.get("veredito", "DESCONHECIDO")
        r["motivo"] = resumo.get("motivo", "")
        return r
    if not stops:
        r["erro"] = "SEM TRAIL"
        return r
    ultimo = stops[-1]
    r["pendentes"] = sorted(k for k, v in ultimo.get("stop_state", {}).items() if not v)
    j = max(1, int(janela))
    ult = stops[-j:]
    if len(ult) < j:
        return r
    conjuntos = [
        frozenset(k for k, v in e.get("stop_state", {}).items() if not v) for e in ult
    ]
    ticks = any(e.get("stop_tick") for e in ult)
    r["ticks_novos"] = ticks
    if len(set(conjuntos)) == 1 and not ticks:
        r["turnos_sem_progresso"] = int(ult[-1].get("turno", 0)) - int(ult[0].get("turno", 0)) + 1
        if r["turnos_sem_progresso"] >= j:
            r["em_loop"] = True
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(description="Detector de loop em trails do harness")
    ap.add_argument("trail")
    ap.add_argument("--janela", type=int, default=5)
    a = ap.parse_args(argv)
    d = detectar_loop(a.trail, janela=a.janela)
    if d.get("erro"):
        print("SEM LOOP | erro=%s" % d["erro"])
        return 0
    if d.get("veredito"):
        print("RUN FINALIZADA | veredito=%s motivo=%s" % (d["veredito"], d.get("motivo", "")))
        return 0
    if d["em_loop"]:
        print(
            "LOOP DETECTADO | turnos_sem_progresso=%d | pendentes=%s | cum $%.6f"
            % (d["turnos_sem_progresso"], ",".join(d["pendentes"]) or "-", d["custo_acumulado"])
        )
        return 2
    print(
        "SEM LOOP | turnos=%d ticks_novos=%s pendentes=%s cum $%.6f"
        % (d["turnos"], d["ticks_novos"], ",".join(d["pendentes"]) or "-", d["custo_acumulado"])
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
