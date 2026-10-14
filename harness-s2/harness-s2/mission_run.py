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


def pane_title(mission_id, seed=None):
    return f"RUN:{mission_id}" + (f"#s{seed}" if seed is not None else "")


# pretty-printer do espelho: JSONL cru → 1 linha legível por evento (puro shell,
# zero CLI; falha de parse só pula a linha — o espelho nunca morre)
_MIRROR_PRINT = (
    "python3 -u -c 'import sys,json\n"
    "for l in sys.stdin:\n"
    " try: d=json.loads(l)\n"
    " except Exception: continue\n"
    " ks=[k for k in (\"veredito\",\"motivo\",\"cum_usd\",\"latencia_ms\","
    "\"stop_tick\",\"todas\",\"is_error\",\"stop_reason\") if k in d]\n"
    " print(\"t%s %s %s\" % (d.get(\"turno\",\"-\"), d.get(\"tool\",\"?\"), "
    "\" \".join(\"%s=%s\"%(k,d[k]) for k in ks)))'\n"
)


def pane_mount(mission_id, trail_placeholder="<RUN>", seed=None):
    """MONTAGEM determinística dos comandos herdr do modo --pane (pura,
    nunca executa — unit-testada com mock; herdr é inacessível no sandbox).

    - tab create com LABEL RUN:<mission-id>#s<seed> (único por despacho —
      não empilha tabs duplicadas com o mesmo nome);
    - espelho: espera o trail nascer em <cwd>/run-*/ (glob) e então
      `tail -F | pretty-printer` — 1 linha legível por evento, não JSON cru.
    """
    title = pane_title(mission_id, seed)
    # O pane segue o harness-pane.log — 1 linha legível PTBR por evento (BRT),
    # escrito pelo próprio harness junto do trail. Sem pretty-printer no meio:
    # menos peça para quebrar, zero JSON cru na tela do supervisor.
    glob_ = os.path.join(trail_placeholder, "run-*", "harness-pane.log")
    mirror = (f"until ls {glob_} >/dev/null 2>&1; do sleep 2; done; "
              f"tail -n +1 -F {glob_}")
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



# ---- DEBUGMODE-INFRA-02: presets de modo + memória entre runs -------------

PRESETS = {
    "normal": {"raw_window": 12, "max_summary": 60, "max_tool_chars": 4000},
    # max_tool_chars plumbado até run_mission (harness.MAX_TOOL_CHARS é o default
    # do modo normal: 4000; debug eleva para 12000).
    "debug":  {"raw_window": 40, "max_summary": 120, "max_tool_chars": 12000},
}

_DIAG_HEADER = "## DIAGNÓSTICO PRÉVIO (run anterior)"


def extrair_memoria(trail_path, max_bash=5, max_chars=3000):
    """Lê trail.jsonl de run anterior → bloco de diagnóstico (ou None).

    Extrai: veredito+motivo do _resumo, stop-conditions cumpridas e os
    últimos N tool_result de Bash (texto completo, truncado a max_chars).
    Trail ausente/corrompido → None (nunca levanta).
    """
    if not trail_path or not os.path.isfile(trail_path):
        return None
    try:
        recs = []
        with open(trail_path, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if ln:
                    recs.append(json.loads(ln))
    except Exception:  # noqa: BLE001 — trail corrompido = sem bloco, não bloqueia
        return None
    resumo = next((r for r in reversed(recs) if r.get("tool") == "_resumo"), None)
    if not resumo:
        return None
    bash_results = []
    for r in recs:
        if r.get("tool") == "Bash" and isinstance(r.get("result"), str) and r["result"].strip():
            bash_results.append(r["result"].strip()[:max_chars])
    linhas = [_DIAG_HEADER, ""]
    linhas.append(f"- veredito anterior: {resumo.get('veredito', '?')} "
                  f"(motivo: {resumo.get('motivo', '?')})")
    sc = resumo.get("stop_conditions_cumpridas")
    if sc:
        linhas.append(f"- stop-conditions cumpridas: {sc}")
    if resumo.get("stop_conditions"):
        for c in resumo["stop_conditions"]:
            linhas.append(f"  - [{c.get('kind')}] ok={c.get('ok')} :: "
                          f"{c.get('cmd') or c.get('path') or c.get('marker') or ''}")
    if bash_results:
        linhas.append("- últimos tool_result de Bash (run anterior):")
        for b in bash_results[-max_bash:]:
            linhas.append("  ```")
            linhas.extend("  " + l for l in b.splitlines())
            linhas.append("  ```")
    return "\n".join(linhas)


def bloco_memoria(args):
    """Bloco de diagnóstico do --memoria (ou '' se ausente/corrompido), com aviso."""
    if not getattr(args, "memoria", None):
        return ""
    bloco = extrair_memoria(args.memoria)
    if bloco is None:
        print(f"[memoria] aviso: trail {args.memoria} ausente/corrompido/sem _resumo; "
              f"seguindo SEM bloco de diagnóstico", file=sys.stderr)
        return ""
    return bloco + "\n\n"

def main(argv=None):
    ap = argparse.ArgumentParser(description="harness v2 — executor de missões mission-ops")
    ap.add_argument("--mission", required=True, help="contrato missao-*.md do mission-ops")
    ap.add_argument("--cwd", required=True, help="cwd-alvo da missão (worktree/repo)")
    ap.add_argument("--budget", type=float, default=None, help="teto USD (default: do contrato ou 1.0)")
    ap.add_argument("--max-turns", type=int, default=None)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default=None, help="resumo JSON (default: <run_dir>/run-summary.json)")
    ap.add_argument("--modo", choices=["normal", "debug"], default="normal",
                    help="debug: raw-window 40, sumário 120, max_tool_chars 12000 "
                         "(normal = 12/60/4000, paridade)")
    ap.add_argument("--memoria", default=None,
                    help="path de trail.jsonl de run anterior → bloco "
                         "'DIAGNÓSTICO PRÉVIO' prependado ao kickoff")
    ap.add_argument("--auto-retry", type=int, default=0,
                    help="N re-tentativas automáticas em caso de FAIL "
                         "(herdam --memoria do trail da tentativa anterior)")
    ap.add_argument("--pane", action="store_true",
                    help="sprint 6: tab RUN:<id> no herdr com espelho tail -F da trilha "
                         "+ stream da última linha a cada 10s (herdr indisponível → falha honesta)")
    args = ap.parse_args(argv)

    if args.auto_retry > 0 and args.memoria:
        print("ERRO: --auto-retry e --memoria são mutuamente exclusivos: o retry "
              "gera a própria memória a partir do trail da tentativa anterior "
              "(conflito de fontes). Use apenas --auto-retry.", file=sys.stderr)
        return 2

    if args.pane:
        return run_with_pane(args, sys.argv[1:])

    if args.auto_retry > 0:
        from scripts.autoretry import rodar_com_retry  # lazy: evita circular com autoretry
        agg = rodar_com_retry(mission_path=args.mission, base_cwd=args.cwd,
                              budget_total=args.budget, max_turns=args.max_turns,
                              n_retries=args.auto_retry, seed0=args.seed,
                              modo=args.modo)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(agg, f, ensure_ascii=False, indent=2)
        return 0 if agg.get("veredito") == "PASS" else 1

    try:
        cfg = adaptar_contrato(open(args.mission, encoding="utf-8").read(),
                               cwd=args.cwd, budget_usd=args.budget,
                               max_turns=args.max_turns)
    except AdaptadorSetupError as e:
        print(json.dumps({"veredito": "FAIL", "motivo": "setup_adaptador",
                          "detalhe": str(e)}, ensure_ascii=False, indent=2))
        return 1

    preset = PRESETS[args.modo]
    s = run_mission(args.mission, args.cwd, cfg["budget_usd"], cfg["max_turns"],
                    seed=args.seed, raw_window=preset["raw_window"],
                    max_summary=preset["max_summary"],
                    max_tool_chars=preset["max_tool_chars"],
                    contract_prefix=bloco_memoria(args))
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

    mount = pane_mount(mission_id, seed=args.seed)
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