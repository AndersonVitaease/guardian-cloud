# CLI de missão: missao-*.md do mission-ops → run do harness (HARNESS-SPRINT4-01, item 1)
#
# Uso: /usr/bin/python3 mission_run.py --mission /opt/mission-events/missao-X.md \
#          --cwd /tmp/wt-alvo [--budget 2.0] [--max-turns 60] [--out resumo.json] [--pane]
#
# Adaptador determinístico (adaptador.py) → run_mission do harness v2.
# FAIL honesto no setup: contrato sem prova determinística não roda.
#
# --pane (HARNESS-SPRINT6-01, entrega 3): cria uma tab `RUN:<mission-id>` no
# herdr com espelho `tail -F` da trilha (send-text puro-shell, ZERO CLI
# Claude no caminho), roda a run localmente e faz stream da última linha do
# trail a cada 10s; fim: linha final com veredito + custo + trilha. herdr
# indisponível → falha honesta com motivo ANTES de rodar.
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

from adaptador import AdaptadorSetupError, adaptar_contrato
from harness import run_mission
from mission_report import emitir_run


class PaneUnavailable(RuntimeError):
    """herdr ausente — modo --pane recusa honesto, NADA roda."""


def pane_title(mission_id):
    return f"RUN:{mission_id}"


def pane_mount(mission_id, trail_placeholder="<RUN>"):
    """MONTAGEM determinística dos comandos herdr do modo --pane (pura,
    nunca executa — unit-testada com mock; herdr é inacessível no sandbox).

    - tab create com LABEL RUN:<mission-id> (herdr usa --label, não --title);
    - send-text do comando de espelho `tail -F` na tab ("<TAB>" é o
      placeholder do pane-id, resolvido no runtime: o herdr devolve JSON
      com root_pane.pane_id — extraído lá, nunca aqui; trail_placeholder
      vira o run_dir real no runtime).
    """
    title = pane_title(mission_id)
    # E2E: o trail nasce em <cwd>/run-<ts>-seed*/harness-trail.jsonl DURANTE a
    # run — o espelho espera o glob abrir (puro shell) e então segue com -F.
    glob_ = os.path.join(trail_placeholder, "run-*", "harness-trail.jsonl")
    mirror = (f"until ls {glob_} >/dev/null 2>&1; do sleep 2; done; "
              f"tail -n +1 -F {glob_}\n")
    return {
        "title": title,
        "tab_create": ["herdr", "tab", "create", "--label", title],
        "send_text": ["herdr", "pane", "send-text", "<TAB>", mirror],
    }


def extract_pane_id(tab_create_stdout):
    """pane-id do JSON do `herdr tab create` (result.root_pane.pane_id) —
    ou None (nunca levanta; runtime segue com aviso honesto SEM espelho)."""
    try:
        d = json.loads(tab_create_stdout or "")
        pane = d.get("result", {}).get("root_pane", {})
        return pane.get("pane_id")
    except Exception:  # noqa: BLE001 — JSON quebrado = sem espelho, não bloqueia
        return None


def require_herdr(which=None):
    """herdr no PATH ou falha honesta tipada (nada é executado antes disso)."""
    w = which or shutil.which
    path = w("herdr")
    if not path:
        raise PaneUnavailable(
            "herdr indisponível no PATH — modo --pane exige o herdr "
            "(instale ou rode SEM --pane; o pane é do supervisor)")
    return path


def last_trail_line(run_dir):
    """Última linha JSON do trail da run (ou None — nunca levanta)."""
    trails = sorted(glob.glob(os.path.join(run_dir, "run-*", "harness-trail.jsonl")),
                     key=os.path.getmtime)
    for trail in reversed(trails):
        try:
            with open(trail, encoding="utf-8") as f:
                lines = [ln for ln in f.read().splitlines() if ln.strip()]
            if lines:
                return json.loads(lines[-1])
        except Exception:  # noqa: BLE001 — stream nunca derruba a run
            continue
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="harness v2 — executor de missões mission-ops")
    ap.add_argument("--mission", required=True, help="contrato missao-*.md do mission-ops")
    ap.add_argument("--cwd", required=True, help="cwd-alvo da missão (worktree/repo)")
    ap.add_argument("--budget", type=float, default=None, help="teto USD (default: do contrato ou 1.0)")
    ap.add_argument("--max-turns", type=int, default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None, help="resumo JSON (default: <run_dir>/run-summary.json)")
    ap.add_argument("--pane", action="store_true",
                    help="sprint 6: tab RUN:<id> no herdr com espelho tail -F da trilha "
                         "+ stream da última linha a cada 10s (herdr indisponível → falha honesta)")
    args = ap.parse_args(argv)

    if args.pane:
        return run_with_pane(args, sys.argv[1:])

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
    s["mission"] = cfg["mission"]
    emitir_run(s)  # evento no spool mission-ops (dedupe por assinatura)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    return 0 if s["veredito"] == "PASS" else 1


def run_with_pane(args, cli_argv):
    """Modo --pane: tab espelho no herdr + run local + stream a cada 10s.

    Falha honesta (exit 1, nada executado) se o herdr não estiver no PATH.
    Montagem dos argvs é a de pane_mount (unit-testada); aqui só runtime:
    tab create → send-text do espelho → run local → linha final.
    """
    mission_id = os.path.basename(args.mission).removeprefix("missao-").removesuffix(".md")
    try:
        require_herdr()
    except PaneUnavailable as e:
        print(json.dumps({"veredito": "FAIL", "motivo": "pane_indisponivel",
                          "detalhe": str(e)}, ensure_ascii=False, indent=2))
        return 1

    mount = pane_mount(mission_id)
    tab_id = None
    try:
        r = subprocess.run(mount["tab_create"], capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            tab_id = extract_pane_id(r.stdout) or extract_pane_id(r.stderr)
        if tab_id:
            # espelho: tail -F da trilha da run (send-text puro-shell, zero CLI)
            mirror = (mount["send_text"][4]
                      .replace("<RUN>", os.path.abspath(args.cwd)))
            subprocess.run(["herdr", "pane", "send-text", tab_id, mirror],
                           capture_output=True, text=True, timeout=30)
        else:
            print(f"[pane] aviso: tab criada sem pane-id extraível "
                  f"(stdout: {(r.stdout or '').strip()[:120]!r}); seguindo SEM espelho",
                  file=sys.stderr)
    except Exception as e:  # noqa: BLE001 — pane é visibilidade, não bloqueia a run
        print(f"[pane] aviso: espelho falhou ({type(e).__name__}: {e}); "
              f"seguindo SEM espelho", file=sys.stderr)

    # run local (SEM --pane) + linha final com veredito + custo + trilha
    rc = main([a for a in cli_argv if a != "--pane"])
    line = last_trail_line(os.path.abspath(args.cwd)) or {}
    cost = (line.get("custo") or {}).get("usd") if isinstance(line.get("custo"), dict) else line.get("cum_usd")
    print(f"[pane] fim: veredito={line.get('veredito', '?')} custo_usd={cost} "
          f"trilha={line.get('trail', '?')}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())