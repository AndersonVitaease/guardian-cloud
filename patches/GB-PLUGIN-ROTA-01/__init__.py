# -*- coding: utf-8 -*-
# GB-PLUGIN-ROTA-01 — arquivo de estudo (deploy no fecho)
# Cópia funcional do plugin mission-ops com handle_mission_dispatch MODIFICADO:
# após os gates (preflight, cap 24h, chain_gate), NÃO spawna claude no pane;
# delega ao despachante nativo via subprocess.
import os, sys, json, random, subprocess

PLUGIN_NAME = "mission-ops"

def _gate_preflight(payload):
    """Gate de preflight: payload mínimo válido."""
    if not isinstance(payload, dict):
        return False, "payload não é dict"
    if not payload.get("missionId"):
        return False, "missionId ausente"
    if not payload.get("promptFile"):
        return False, "promptFile ausente"
    return True, "ok"

def _gate_cap_24h(payload):
    """Gate de cap de custo 24h (stub de estudo)."""
    return True, "ok"

def _gate_chain(payload):
    """Gate chain_gate (stub de estudo)."""
    return True, "ok"

def _resolver_cwd(args, payload):
    """cwd_resolvido = <worktree>/runs/<missionId>.
    payload.cwd só vale se começar com <worktree>/runs/."""
    wt = getattr(args, "worktree", None)
    mid = payload.get("missionId")
    correto = os.path.join(wt, "runs", mid)
    pcwd = payload.get("cwd") or ""
    if wt and pcwd.startswith(os.path.join(wt, "runs") + os.sep):
        return pcwd
    return correto

def _resolver_seed(args):
    s = getattr(args, "seed", None)
    if s:
        return str(s)
    return str(random.randint(1, 999999))

def _resolver_budget(args):
    b = getattr(args, "budget", None)
    if b:
        return str(b)
    return "0.30"

def handle_mission_dispatch(mc, args, payload):
    """Rota CORRETA: delega ao despachar_missao.py --executar.
    NUNCA spawna claude no pane (run_command)."""
    ok, msg = _gate_preflight(payload)
    if not ok:
        return {"ok": False, "error": "preflight: " + msg}
    ok, msg = _gate_cap_24h(payload)
    if not ok:
        return {"ok": False, "error": "cap24h: " + msg}
    ok, msg = _gate_chain(payload)
    if not ok:
        return {"ok": False, "error": "chain_gate: " + msg}

    cwd_resolvido = _resolver_cwd(args, payload)
    seed = _resolver_seed(args)
    budget = _resolver_budget(args)
    prompt_file = payload["promptFile"]

    cmd = [
        "python3",
        "/opt/mission-events/scripts/despachar_missao.py",
        prompt_file,
        cwd_resolvido,
        "--executar",
        "--seed", seed,
        "--budget", budget,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    try:
        resultado = json.loads(proc.stdout or "{}")
    except Exception:
        resultado = {"ok": proc.returncode == 0, "raw": proc.stdout, "stderr": proc.stderr}
    return resultado

def register(mc):
    mc.register_handler("mission_dispatch", handle_mission_dispatch)