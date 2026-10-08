#!/usr/bin/env python3
"""CLI: saúde do harness-trail.jsonl (integridade estrutural)."""
import json, sys


def saude_do_trail(trail_path):
    """Retorna 'SAUDÁVEL | N eventos' ou 'DOENTE | <problema>'."""
    try:
        with open(trail_path, encoding="utf-8") as f:
            linhas = [l for l in f.read().splitlines() if l.strip()]
    except OSError:
        return "DOENTE | trail inexistente ou ilegível"
    if not linhas:
        return "DOENTE | trail vazio"
    eventos = []
    for i, l in enumerate(linhas, 1):
        try:
            eventos.append(json.loads(l))
        except json.JSONDecodeError as e:
            return f"DOENTE | linha {i} não é JSON parseável ({e})"
    if not eventos or eventos[0].get("tool") != "_inicio":
        return "DOENTE | _inicio ausente"
    turnos = [e.get("turno", 0) for e in eventos]
    for a, b in zip(turnos, turnos[1:]):
        if b < a:
            return f"DOENTE | sequência de turnos decrescente ({a}→{b})"
    if any(e.get("tool") == "_resumo" for e in eventos[:-1]):
        return "DOENTE | _resumo não é a última linha"
    return f"SAUDÁVEL | {len(eventos)} eventos"


def main(argv):
    if len(argv) < 2:
        print("uso: trail_saude.py <trail.jsonl>", file=sys.stderr)
        return 2
    out = saude_do_trail(argv[1])
    print(out)
    return 1 if out.startswith("DOENTE") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
