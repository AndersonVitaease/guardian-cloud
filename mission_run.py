# CLI de missão: missao-*.md do mission-ops → run do harness (HARNESS-SPRINT4-01, item 1)
#
# Uso: /usr/bin/python3 mission_run.py --mission /opt/mission-events/missao-X.md \
#          --cwd /tmp/wt-alvo [--budget 2.0] [--max-turns 60] [--out resumo.json]
#
# Adaptador determinístico (adaptador.py) → run_mission do harness v2.
# FAIL honesto no setup: contrato sem prova determinística não roda.
import argparse
import json
import sys

from adaptador import AdaptadorSetupError, adaptar_contrato
from harness import run_mission


def main(argv=None):
    ap = argparse.ArgumentParser(description="harness v2 — executor de missões mission-ops")
    ap.add_argument("--mission", required=True, help="contrato missao-*.md do mission-ops")
    ap.add_argument("--cwd", required=True, help="cwd-alvo da missão (worktree/repo)")
    ap.add_argument("--budget", type=float, default=None, help="teto USD (default: do contrato ou 1.0)")
    ap.add_argument("--max-turns", type=int, default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None, help="resumo JSON (default: <run_dir>/run-summary.json)")
    args = ap.parse_args(argv)

    try:
        cfg = adaptar_contrato(open(args.mission, encoding="utf-8").read(),
                               cwd=args.cwd, budget_usd=args.budget,
                               max_turns=args.max_turns)
    except AdaptadorSetupError as e:
        print(json.dumps({"veredito": "FAIL", "motivo": "setup_adaptador",
                          "detalhe": str(e)}, ensure_ascii=False, indent=2))
        return 1

    s = run_mission(args.mission, args.cwd, cfg["budget_usd"], cfg["max_turns"],
                    seed=args.seed)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    return 0 if s["veredito"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())