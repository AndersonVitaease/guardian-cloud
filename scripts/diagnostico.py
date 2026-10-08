#!/usr/bin/env python3
"""DIAG-AUTORETRY-01 — diagnóstico prévio a partir do trail (pt-BR).

analisar(trail_path) -> dict com veredito, motivo, turnos, custo, stop-conditions,
comandos repetidos, últimas ações de tool e arquivo mais recente escrito.
bloco_diagnostico(trail_path) -> bloco "## DIAGNÓSTICO PRÉVIO (gerado)".
Trail ausente/corrompido -> None (fail-open; retry nunca morre por diagnóstico).
"""
import argparse
import json
import os
import sys

HEADER = "## DIAGNÓSTICO PRÉVIO (gerado)"


def _ler_trail(trail_path):
    """Retorna lista de eventos ou None se trail ausente/corrompido."""
    if not trail_path or not os.path.isfile(trail_path):
        return None
    recs = []
    try:
        with open(trail_path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    recs.append(json.loads(ln))
    except Exception:  # noqa: BLE001 — corrompido = sem diagnóstico
        return None
    return recs or None


def _comandos_repetidos(recs, prefixo=80, minimo=3):
    """Mesmo prefixo de 80 chars de comando Bash >= 3x (padrão detector_loop)."""
    contagem = {}
    for r in recs:
        if r.get("tool") != "Bash":
            continue
        inp = r.get("input") or {}
        cmd = inp.get("command") if isinstance(inp, dict) else None
        if isinstance(cmd, str) and cmd.strip():
            contagem[cmd.strip()[:prefixo]] = contagem.get(cmd.strip()[:prefixo], 0) + 1
    return [{"prefixo": p, "vezes": n} for p, n in contagem.items() if n >= minimo]


def _ultimas_acoes(recs, n=3, max_cmd=100):
    acoes = []
    for r in recs:
        tool = r.get("tool")
        if not tool or tool.startswith("_"):
            continue
        inp = r.get("input") or {}
        cmd = ""
        if isinstance(inp, dict):
            cmd = inp.get("command") or inp.get("file_path") or inp.get("path") or ""
        acoes.append({"tool": tool, "cmd": str(cmd)[:max_cmd]})
    return acoes[-n:]


def _arquivo_mais_recente(recs):
    alvo = None
    for r in recs:
        if r.get("tool") in ("Edit", "Write"):
            inp = r.get("input") or {}
            p = inp.get("file_path") if isinstance(inp, dict) else None
            if p:
                alvo = p
    return alvo


def analisar(trail_path):
    """Trail -> dict de diagnóstico; None se trail ausente/corrompido."""
    recs = _ler_trail(trail_path)
    if recs is None:
        return None
    resumo = next((r for r in reversed(recs) if r.get("tool") == "_resumo"), None)
    stops = [r for r in recs if r.get("tool") == "_stop_check"]
    custo = 0.0
    turnos = 0
    for r in recs:
        if isinstance(r.get("cum_usd"), (int, float)):
            custo = r["cum_usd"]
        elif isinstance(r.get("custo_usd"), (int, float)):
            custo += r["custo_usd"]
        if "turno" in r:
            turnos = max(turnos, int(r["turno"]))
    if resumo:
        turnos = max(turnos, int(resumo.get("turnos", 0) or 0))
        custo = resumo.get("custo", {}).get("usd", custo) \
            if isinstance(resumo.get("custo"), dict) else custo

    stop_conditions = {"ok": [], "pendentes": []}
    if resumo and isinstance(resumo.get("stop_conditions"), list):
        for c in resumo["stop_conditions"]:
            nome = c.get("cmd") or c.get("path") or c.get("marker") or c.get("kind") or "?"
            entrada = {"kind": c.get("kind"), "nome": str(nome)[:120], "ok": bool(c.get("ok"))}
            (stop_conditions["ok"] if c.get("ok") else stop_conditions["pendentes"]).append(entrada)
    elif stops:
        ultimo = stops[-1]
        state = ultimo.get("stop_state") or {}
        stop_conditions["pendentes"] = [
            {"kind": "declarada", "nome": k, "ok": False}
            for k, v in state.items() if not v]
        stop_conditions["ok"] = [
            {"kind": "declarada", "nome": k, "ok": True}
            for k, v in state.items() if v]

    return {
        "veredito": (resumo or {}).get("veredito", "DESCONHECIDO"),
        "motivo": (resumo or {}).get("motivo", ""),
        "turnos": turnos,
        "custo_usd": round(float(custo), 6),
        "stop_conditions": stop_conditions,
        "comandos_repetidos": _comandos_repetidos(recs),
        "ultimas_acoes": _ultimas_acoes(recs),
        "arquivo_mais_recente": _arquivo_mais_recente(recs),
    }


def bloco_diagnostico(trail_path):
    """Dict analisar -> bloco pt-BR para injeção no retry. None se sem trail."""
    d = analisar(trail_path)
    if d is None:
        return None
    linhas = [HEADER, ""]
    linhas.append(f"- veredito anterior: {d['veredito']} (motivo: {d['motivo'] or '?'})")
    linhas.append(f"- turnos: {d['turnos']} | custo: ${d['custo_usd']:.6f}")
    sc = d["stop_conditions"]
    linhas.append(f"- stop-conditions ok: "
                  f"{', '.join(c['nome'] for c in sc['ok']) or 'nenhuma'}")
    for c in sc["pendentes"]:
        linhas.append(f"  - PENDENTE: {c['nome']} (kind={c['kind']})")
    if d["comandos_repetidos"]:
        for cr in d["comandos_repetidos"]:
            linhas.append(f"- comando repetido {cr['vezes']}x: {cr['prefixo']}")
    if d["ultimas_acoes"]:
        linhas.append("- últimas ações:")
        for a in d["ultimas_acoes"]:
            linhas.append(f"  - {a['tool']}: {a['cmd']}")
    if d["arquivo_mais_recente"]:
        linhas.append(f"- último arquivo escrito: {d['arquivo_mais_recente']}")
    return "\n".join(linhas)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Diagnóstico prévio de trail FAIL (pt-BR)")
    ap.add_argument("trail", help="caminho do harness-trail.jsonl")
    ap.add_argument("--json", action="store_true", help="imprime dict JSON")
    args = ap.parse_args(argv)
    if args.json:
        d = analisar(args.trail)
        if d is None:
            return 1
        print(json.dumps(d, ensure_ascii=False, indent=2))
        return 0
    bloco = bloco_diagnostico(args.trail)
    if bloco is None:
        return 1
    print(bloco)
    return 0


if __name__ == "__main__":
    sys.exit(main())