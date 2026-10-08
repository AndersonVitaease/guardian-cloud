"""AUTORETRY-SCRIPT-01 — retry sequencial com memória entre tentativas.

Tentativa 1 roda run_mission em <base_cwd>/tentativa-1/ com seed0. Se PASS,
devolve o resumo direto. Se FAIL e sob budget, extrai o bloco
"DIAGNÓSTICO PRÉVIO" do trail da tentativa anterior (mission_run.extrair_memoria)
e re-tenta com memória injetada no kickoff, seed+1, cwd tentativa-<k+1>/ e
budget = budget_total MENOS o já gasto. Hard-cap: 4 tentativas (1 + 3 retries).
Escreve autoretry-summary.json no base_cwd.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import mission_run  # noqa: E402

HARD_CAP = 4  # 1 tentativa + 3 retries no máximo


def rodar_com_retry(mission_path, base_cwd, budget_total, max_turns,
                    n_retries=1, seed0=100, model=harness.MODEL,
                    bridge_fn=harness.call_bridge, modo=None):
    """Retry sequencial: até 1+n_retries tentativas (cap 4). Devolve agregado."""
    base_cwd = os.path.abspath(base_cwd)
    os.makedirs(base_cwd, exist_ok=True)
    kwargs = {}
    if modo:
        preset = mission_run.PRESETS.get(modo, mission_run.PRESETS["normal"])
        kwargs = {"raw_window": preset["raw_window"],
                  "max_summary": preset["max_summary"],
                  "max_tool_chars": preset["max_tool_chars"]}

    tentativas = []
    vereditos = []
    custo_total = 0.0
    memoria = None
    k = 0
    max_tent = min(1 + max(0, n_retries), HARD_CAP)
    while k < max_tent:
        k += 1
        restante = budget_total - custo_total
        if restante <= 0:
            break
        run_dir_base = os.path.join(base_cwd, f"tentativa-{k}")
        os.makedirs(run_dir_base, exist_ok=True)
        resumo = harness.run_mission(
            mission_path, run_dir_base, restante, max_turns,
            seed=seed0 + k - 1, model=model, bridge_fn=bridge_fn,
            contract_prefix=(memoria + "\n\n") if memoria else "", **kwargs)
        tentativas.append(resumo)
        vereditos.append(resumo["veredito"])
        custo_total += resumo.get("custo", {}).get("usd", 0.0)
        if resumo["veredito"] == "PASS":
            break
        memoria = mission_run.extrair_memoria(
            os.path.join(resumo["run_dir"], "harness-trail.jsonl"))

    agregado = {
        "veredito": vereditos[-1] if vereditos else "FAIL",
        "tentativas": len(tentativas),
        "vereditos_por_tentativa": vereditos,
        "custo_total": round(custo_total, 8),
        "budget_total": budget_total,
        "runs": tentativas,
    }
    with open(os.path.join(base_cwd, "autoretry-summary.json"), "w",
              encoding="utf-8") as f:
        json.dump(agregado, f, ensure_ascii=False, indent=2)
    return agregado


def main(argv=None):
    ap = argparse.ArgumentParser(description="Retry sequencial de missões (memória entre tentativas)")
    ap.add_argument("--mission", required=True)
    ap.add_argument("--cwd", required=True)
    ap.add_argument("--budget", type=float, default=1.0)
    ap.add_argument("--max-turns", type=int, default=30)
    ap.add_argument("--retries", type=int, default=1)
    ap.add_argument("--seed0", type=int, default=100)
    ap.add_argument("--modo", choices=["normal", "debug"], default=None)
    a = ap.parse_args(argv)
    agg = rodar_com_retry(a.mission, a.cwd, a.budget, a.max_turns,
                          n_retries=a.retries, seed0=a.seed0, modo=a.modo)
    print("=== RESUMO AUTORETRY ===")
    print(f"veredito final: {agg['veredito']}")
    print(f"tentativas: {agg['tentativas']} ({' -> '.join(agg['vereditos_por_tentativa'])})")
    print(f"custo total: ${agg['custo_total']:.6f} de ${agg['budget_total']}")
    print(f"resumo: {os.path.join(os.path.abspath(a.cwd), 'autoretry-summary.json')}")
    return 0 if agg["veredito"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
