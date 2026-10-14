#!/usr/bin/env python3
"""FILA-HIGIENE-01 — inventário e dedup da fila do orchestrator.

Dry-run por padrão: `limpar` só reporta; nunca sobrescreve a fila original.
"""
import argparse
import json
import os
import sys
from collections import Counter


def _ler(fila_path):
    entradas = []
    with open(fila_path, "r", encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            entradas.append(json.loads(linha))
    return entradas


def inventariar(fila_path):
    entradas = _ler(fila_path)
    total = len(entradas)
    por_type = Counter(e.get("type") for e in entradas)
    por_status = Counter(e.get("payload", {}).get("status") for e in entradas)
    contagem_ids = Counter(e.get("id") for e in entradas)
    ids_duplicados = {
        i: c for i, c in contagem_ids.items() if c > 1
    }
    mission_ids = sorted({
        e.get("payload", {}).get("missionId")
        for e in entradas
        if e.get("payload", {}).get("missionId")
    })
    sem_prompt = [
        e.get("id") for e in entradas
        if not e.get("payload", {}).get("promptFile")
        or not os.path.isfile(e.get("payload", {}).get("promptFile", ""))
    ]
    return {
        "total": total,
        "por_type": dict(por_type),
        "por_status": dict(por_status),
        "ids_duplicados": ids_duplicados,
        "linhas_duplicadas": sum(c - 1 for c in ids_duplicados.values()),
        "missoes_unicas": mission_ids,
        "sem_promptFile_valido": sem_prompt,
    }


def plano_limpeza(fila):
    """Linhas REMOVÍVEIS: duplicadas (mantém a 1ª ocorrência de cada id)."""
    vistos = set()
    removiveis = []
    for idx, e in enumerate(fila):
        eid = e.get("id")
        if eid in vistos:
            removiveis.append(idx)
        else:
            vistos.add(eid)
    return removiveis


def limpar(fila_path, dry_run=True):
    fila = _ler(fila_path)
    removiveis = plano_limpeza(fila)
    limpa = [e for i, e in enumerate(fila) if i not in set(removiveis)]
    destino = f"{fila_path}.limpa.jsonl"
    resultado = {
        "fila": os.path.abspath(fila_path),
        "total": len(fila),
        "removiveis": len(removiveis),
        "restantes": len(limpa),
        "dry_run": dry_run,
        "destino": destino,
        "escrito": False,
    }
    if not dry_run:
        with open(destino, "w", encoding="utf-8") as f:
            for e in limpa:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        resultado["escrito"] = True
    return resultado


def main(argv=None):
    ap = argparse.ArgumentParser(description="Inventário/dedup da fila do orchestrator")
    ap.add_argument("--fila", required=True)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--limpar", action="store_true")
    args = ap.parse_args(argv)
    if args.limpar:
        out = limpar(args.fila, dry_run=False)
    else:
        out = inventariar(args.fila)
    print(json.dumps(out, ensure_ascii=False, indent=2 if args.json else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())