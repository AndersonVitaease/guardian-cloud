#!/usr/bin/env python3
"""RETRY-DECIDE-01 — decisão seletiva: re-tentar ou parar (fail-closed).

decidir(diag) -> {"acao": "retry"|"stop", "mudancas": dict|None, "razao": pt-BR}.
Regras (default = stop; NUNCA gasta retry em parede):
  a) motivo max_turns, não-loop, stop-conditions parciais (>0 ok) -> retry
     (max_turns +15, seed +1).
  b) parou_sem_stop_condition, 0/5 ok, comandos repetidos >=3x -> stop (attractor).
  c) motivo budget -> stop.
  d) erro de PERMISSÃO nas últimas ações -> stop (parede do supervisor).
  e) UNKNOWN -> stop (fail-closed).
CLI: python3 scripts/retry_decide.py <trail.jsonl> -> JSON, exit 0.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PERMISSAO_TOKENS = ("permissionerror", "permission denied", "denied")


def _permissao(diag):
    """True se 'denied'/PermissionError aparece nas últimas ações."""
    for a in diag.get("ultimas_acoes") or []:
        texto = f"{a.get('tool', '')} {a.get('cmd', '')}".lower()
        if any(t in texto for t in PERMISSAO_TOKENS):
            return True
    return False


def _loop(diag):
    return bool(diag.get("comandos_repetidos"))


def decidir(diag):
    """Dict de diagnóstico -> decisão retry/stop (fail-closed)."""
    if not isinstance(diag, dict):
        return {"acao": "stop", "mudancas": None,
                "razao": "diagnóstico insuficiente (entrada inválida) — fail-closed"}
    motivo = diag.get("motivo")
    sc = diag.get("stop_conditions") or {}
    n_ok = len(sc.get("ok") or [])
    n_pend = len(sc.get("pendentes") or [])
    total = n_ok + n_pend

    if _permissao(diag):
        return {"acao": "stop", "mudancas": None,
                "razao": "parede de permissão é do supervisor, não do worker — retry repetiria o erro"}

    if motivo == "budget":
        return {"acao": "stop", "mudancas": None,
                "razao": "orçamento esgotado (retry sem budget é run morta)"}

    if motivo == "max_turns" and not _loop(diag) and n_ok > 0:
        return {"acao": "retry",
                "mudancas": {"max_turns": "+15", "seed": "+1",
                             "nota": "progresso medido, janela maior"},
                "razao": f"max_turns com progresso medido ({n_ok}/{total} stop-conditions ok) e sem loop — janela maior tende a fechar"}

    if motivo == "parou_sem_stop_condition" and n_ok == 0 and _loop(diag):
        cr = diag["comandos_repetidos"][0]
        return {"acao": "stop", "mudancas": None,
                "razao": f"attractor de loop (mesmo comando {cr['vezes']}x+) — retry queimaria o mesmo muro"}

    return {"acao": "stop", "mudancas": None,
            "razao": "diagnóstico insuficiente — fail-closed"}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Decide retry vs stop a partir do trail (JSON)")
    ap.add_argument("trail", help="caminho do harness-trail.jsonl")
    args = ap.parse_args(argv)
    import diagnostico  # noqa: E402 — lazy
    diag = diagnostico.analisar(args.trail)
    print(json.dumps(decidir(diag), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())