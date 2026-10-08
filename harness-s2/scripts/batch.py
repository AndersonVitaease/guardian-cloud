"""BATCH-PARALELO-01 — N seeds em paralelo com budget agregado compartilhado.

Cada seed k roda run_mission em <base_cwd>/batch-s<k>/ com ledger compartilhado
(thread-safe): todas as threads somam no MESMO Ledger; estourar budget_total
aborta TODAS (stop_flag). Painel/trilha de cada run com prefixo [s<k>].
"""
import argparse
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness  # noqa: E402


def rodar_batch(mission_path, base_cwd, n_seeds, budget_total, max_turns,
                seed0=100, model=harness.MODEL, bridge_fn=harness.call_bridge,
                max_workers=3, stop_flag=None):
    """Roda n_seeds em paralelo; devolve agregado e escreve batch-summary.json.
    stop_flag: Event externo opcional; se None, cria um interno. O MESMO
    objeto (externo ou interno) é plumbed ao run_mission de cada thread."""
    ledger = harness.Ledger()  # compartilhado — lock interno garante atomicidade

    class _Gate:
        """Reserva atômicamente o custo estimado da próxima chamada sob o lock
        do ledger — garante que o teto agregado NUNCA é estourado, mesmo com
        N threads checando/ cobrando concorrentemente."""

        def __init__(self):
            self.pending = 0.0
            self.last_cost = 0.0  # custo observado da última chamada (reserva adaptativa)

        def __call__(self, msgs, system, led, model=None):
            price = led.price(model or harness.MODEL)
            # reserva: teto do output + custo observado da chamada anterior
            # (conservador: se a última chamada custou X, a próxima não deve
            #  custar menos que isso em regime; cobre mocks e modelos reais)
            est = max((4096 * price["out"]) / 1e6, self.last_cost)
            with led._lock:
                if stop_flag.is_set() or led.cost + self.pending + est > budget_total:
                    stop_flag.set()
                    raise harness.BridgeError("budget_excedido")
                self.pending += est
            try:
                d, usd, dt, retries = bridge_fn(msgs, system, led, model=model)
                self.last_cost = max(self.last_cost, usd)
                return d, usd, dt, retries
            finally:
                with led._lock:
                    self.pending -= est

    gate = _Gate()
    if stop_flag is None:
        stop_flag = threading.Event()  # interno (paridade dos usos atuais)
    lock = threading.Lock()
    base_cwd = os.path.abspath(base_cwd)
    os.makedirs(base_cwd, exist_ok=True)

    def uma(seed_k):
        run_dir_base = os.path.join(base_cwd, f"batch-s{seed_k}")
        os.makedirs(run_dir_base, exist_ok=True)
        prefix = f"[s{seed_k}]"
        resumo = harness.run_mission(
            mission_path, run_dir_base, budget_total, max_turns, seed=seed_k,
            model=model, ledger=ledger, bridge_fn=gate,
            stop_flag=stop_flag, pane_prefix=prefix)
        # marca veredito de abort agregado (gate lança BridgeError("budget_excedido"))
        if "budget_excedido" in str(resumo.get("motivo", "")):
            resumo["veredito"] = "FAIL"
            resumo["motivo"] = "budget_excedido"
        with lock:
            if resumo["veredito"] == "FAIL" and resumo["motivo"] == "budget_excedido":
                stop_flag.set()  # aborta as outras threads antes da próxima chamada
        return resumo

    seeds = list(range(seed0, seed0 + n_seeds))
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, n_seeds))) as ex:
        runs = list(ex.map(uma, seeds))

    vereditos = {"PASS": 0, "FAIL": 0}
    for r in runs:
        vereditos[r["veredito"]] = vereditos.get(r["veredito"], 0) + 1
    agregado = {"vereditos": vereditos, "custo_total": round(ledger.cost, 8),
                "runs": runs, "budget_total": budget_total, "seeds": seeds}
    with open(os.path.join(base_cwd, "batch-summary.json"), "w", encoding="utf-8") as f:
        json.dump(agregado, f, ensure_ascii=False, indent=2)
    return agregado


def main(argv=None):
    ap = argparse.ArgumentParser(description="Batch paralelo de seeds (budget agregado)")
    ap.add_argument("--mission", required=True)
    ap.add_argument("--cwd", required=True)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--budget", type=float, default=1.0)
    ap.add_argument("--max-turns", type=int, default=60)
    ap.add_argument("--seed0", type=int, default=100)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args(argv)
    agg = rodar_batch(a.mission, a.cwd, a.seeds, a.budget, a.max_turns,
                      seed0=a.seed0, max_workers=a.workers)
    print("=== RESUMO BATCH ===")
    print(f"seeds: {agg['seeds']}")
    print(f"vereditos: PASS={agg['vereditos']['PASS']} FAIL={agg['vereditos']['FAIL']}")
    print(f"custo total: ${agg['custo_total']:.6f} de ${agg['budget_total']}")
    for r in agg["runs"]:
        print(f"[s{r['seed']}] {r['veredito']} motivo={r['motivo']} "
              f"turnos={r['turnos']} custo=${r['custo']['usd']:.6f} dir={r['run_dir']}")
    print(f"resumo: {os.path.join(a.cwd, 'batch-summary.json')}")
    return 0 if agg["vereditos"]["FAIL"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
