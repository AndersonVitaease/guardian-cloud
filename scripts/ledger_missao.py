#!/usr/bin/env python3
"""Ledger de missão para runs do harness (DESP-03).

Grava/atualiza <state_dir>/<ID>.json (padrão /root/.hermes/mission-state,
ou MISSION_STATE_DIR) de forma atômica. Fail-open: nunca levanta por
ausência de aba/ledger.

Uso:
  python3 scripts/ledger_missao.py registrar <ID> --contrato C --cwd D --seed N [--label L]
  python3 scripts/ledger_missao.py fechar <ID> --resumo resumo.json
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR_DEFAULT = os.environ.get("MISSION_STATE_DIR") or "/root/.hermes/mission-state"
TERMINAIS = ("closed", "failed", "cancelled", "delivered")


def _agora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _caminho(missao_id, state_dir=None):
    return Path(state_dir or STATE_DIR_DEFAULT) / ("%s.json" % missao_id)


ENTREGA_VERIFY_DEFAULT = "/home/worker/harness-s2/tools-bash/entrega_verify.sh"


def _verificar_entrega(missao_id, state_dir, runner):
    """Roda entrega_verify; retorna {'ok': True/False/None, ...} (None = erro de execucao)."""
    tool = os.environ.get("ENTREGA_VERIFY_PATH") or ENTREGA_VERIFY_DEFAULT
    env = dict(os.environ)
    env["ENTREGA_STATE_DIR"] = str(state_dir or STATE_DIR_DEFAULT)
    try:
        proc = runner(["bash", tool, missao_id], env=env,
                      capture_output=True, text=True)
    except Exception as e:
        return {"ok": None, "aviso": str(e)}
    try:
        out = json.loads((proc.stdout or "").strip().splitlines()[-1])
    except Exception:
        return {"ok": None, "aviso": "saida_invalida_entrega_verify"}
    if out.get("ok") is True:
        return {"ok": True}
    entrega = {"ok": False}
    if out.get("faltando"):
        entrega["faltando"] = out["faltando"]
    if out.get("error"):
        entrega["error"] = out["error"]
    return entrega


def _gravar_atomico(path, dados):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".ledger-", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    os.replace(tmp, str(path))


def _ler_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _procurar_aba(label, runner, espera_s, sleep):
    """Procura aba herdr com label dado; retorna (tab_id, pane_id) ou (None, None)."""
    alvo = "RUN:%s" % label
    prazo = time.monotonic() + espera_s
    while True:
        try:
            proc = runner(["herdr", "tab", "list"])
            saida = proc.stdout if hasattr(proc, "stdout") else proc
            if isinstance(saida, bytes):
                saida = saida.decode("utf-8", "replace")
            dados = json.loads(saida)
            if isinstance(dados, dict):
                resultado = dados.get("result")
                if isinstance(resultado, dict) and isinstance(resultado.get("tabs"), list):
                    abas = resultado["tabs"]
                else:
                    abas = dados.get("tabs", dados)
            else:
                abas = dados
            if isinstance(abas, list):
                for aba in abas:
                    if not isinstance(aba, dict):
                        continue
                    lab = aba.get("label") or aba.get("title") or ""
                    if lab == alvo:
                        tab_id = aba.get("id") or aba.get("tabId") or aba.get("tab_id")
                        pane = aba.get("paneId") or aba.get("pane_id")
                        if pane is None:
                            panes = aba.get("panes") or []
                            if panes and isinstance(panes[0], dict):
                                pane = panes[0].get("id") or panes[0].get("paneId")
                        return tab_id, pane
        except Exception:
            pass
        if time.monotonic() >= prazo:
            return None, None
        sleep(2)


def registrar(missao_id, cwd, contrato, seed, label=None, state_dir=None,
              runner=subprocess.run, espera_s=20, sleep=time.sleep):
    """Registra ledger da missão despachada pelo harness. Fail-open."""
    path = _caminho(missao_id, state_dir)
    existente = _ler_json(path)
    if existente and existente.get("status") in TERMINAIS:
        return {"ok": False, "erro": "LEDGER_TERMINAL", "path": str(path)}
    alvo_label = label or missao_id
    tab_id, pane_id = _procurar_aba("%s#s%s" % (alvo_label, seed),
                                    runner, espera_s, sleep)
    agora = _agora()
    ledger = {
        "missionId": missao_id,
        "paneId": pane_id,
        "tabId": tab_id,
        "creation": "harness",
        "paneTitle": "RUN:%s#s%s" % (alvo_label, seed) if tab_id else None,
        "promptFile": contrato,
        "cwd": cwd,
        "resumeSessionId": None,
        "status": "dispatched",
        "createdAt": (existente or {}).get("createdAt", agora),
        "updatedAt": agora,
        "spawned_by": "despachante",
        "chain_depth": 0,
        "allow_chain_dispatch": False,
        "consequence": False,
        "engine": "harness",
    }
    _gravar_atomico(path, ledger)
    if tab_id is None:
        return {"ok": True, "aviso": "aba_nao_encontrada", "path": str(path),
                "paneId": None, "tabId": None}
    return {"ok": True, "path": str(path), "paneId": pane_id, "tabId": tab_id}


def _gerar_relatorio(ledger, resumo, state_dir, runner):
    cwd = ledger.get("cwd") or ""
    veredito = resumo.get("veredito") or resumo.get("status") or "?"
    custo = resumo.get("custo_usd", resumo.get("custo", resumo.get("cum_usd")))
    turnos = resumo.get("turnos", resumo.get("turns"))
    stops = resumo.get("stop-conditions") or resumo.get("stop_conditions") or []
    run_dir = resumo.get("run_dir") or ledger.get("run_dir") or "-"
    try:
        git = runner(["git", "-C", cwd, "log", "--oneline", "-1"])
        saida = git.stdout if hasattr(git, "stdout") else git
        if isinstance(saida, bytes):
            saida = saida.decode("utf-8", "replace")
        commit = (saida or "").strip() or "(sem commit)"
    except Exception:
        commit = "(git indisponível)"
    linhas = [
        "# Relatório — %s" % ledger.get("missionId"),
        "",
        "| Campo | Valor |",
        "|---|---|",
        "| Veredito | %s |" % veredito,
        "| Stops cumpridas | %s |" % (", ".join(map(str, stops)) if stops else "-"),
        "| Custo (USD) | %s |" % custo,
        "| Turnos | %s |" % turnos,
        "| run_dir | %s |" % run_dir,
        "| Commit | `%s` |" % commit,
        "",
    ]
    texto = "\n".join(linhas)
    destino = None
    if cwd and os.path.isdir(cwd) and os.access(cwd, os.W_OK):
        destino = Path(cwd) / ("RELATORIO-%s.md" % ledger.get("missionId"))
    else:
        base = Path(state_dir or STATE_DIR_DEFAULT) / "relatorios"
        base.mkdir(parents=True, exist_ok=True)
        destino = base / ("RELATORIO-%s.md" % ledger.get("missionId"))
    try:
        destino.write_text(texto, encoding="utf-8")
    except Exception:
        return None
    return str(destino)


def fechar(missao_id, resumo_path, state_dir=None, runner=subprocess.run):
    """Fecha o ledger a partir do resumo.json do harness. Idempotente, fail-open."""
    path = _caminho(missao_id, state_dir)
    ledger = _ler_json(path)
    if not ledger:
        return {"ok": False, "erro": "LEDGER_AUSENTE", "path": str(path)}
    if ledger.get("status") in TERMINAIS and ledger.get("status") != "pass_oco":
        return {"ok": True, "status": ledger.get("status"), "relatorio": None,
                "aba_fechada": False, "idempotente": True}
    # pass_oco NÃO é terminal: permite reconciliação no fecho seguinte.
    resumo = _ler_json(resumo_path) or {}
    veredito = (resumo.get("veredito") or resumo.get("status") or "").upper()
    entrega = None
    if veredito == "PASS":
        # Reconciliação no fecho: re-executa entrega_verify. Se ok => PASS
        # (closed). Se falha => PASS_OCO com status próprio (nunca "failed").
        entrega = _verificar_entrega(missao_id, state_dir, runner)
        if entrega.get("ok") is False:
            veredito = "PASS_OCO"
    if veredito == "PASS":
        status = "closed"
    elif veredito == "PASS_OCO":
        # PASS_OCO honesto: status próprio (nunca "failed"); reconciliável
        # no fecho seguinte (se entrega passar, sobe para closed/PASS).
        status = "pass_oco"
    else:
        status = "failed"
    agora = _agora()
    ledger.update({
        "status": status,
        "updatedAt": agora,
        "closedAt": agora,
        "veredito": veredito or None,
        "custo_usd": resumo.get("custo_usd", resumo.get("custo", resumo.get("cum_usd"))),
        "turnos": resumo.get("turnos", resumo.get("turns")),
        "relatorio": resumo_path,
    })
    if entrega is not None:
        ledger["entrega"] = entrega
    relatorio = _gerar_relatorio(ledger, resumo, state_dir, runner)
    if relatorio:
        ledger["relatorio"] = relatorio
    _gravar_atomico(path, ledger)
    aba_fechada = False
    aviso = None
    tab_id = ledger.get("tabId")
    if tab_id:
        try:
            runner(["herdr", "tab", "close", tab_id])
            aba_fechada = True
        except Exception as e:
            aviso = str(e)
    else:
        aviso = "sem_tab_id"
    out = {"ok": True, "status": status, "relatorio": relatorio,
           "aba_fechada": aba_fechada}
    if aviso:
        out["aviso"] = aviso
    return out


def main(argv):
    p = argparse.ArgumentParser(description="Ledger de missão (harness)")
    sub = p.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("registrar")
    pr.add_argument("missao_id")
    pr.add_argument("--contrato", required=True)
    pr.add_argument("--cwd", required=True)
    pr.add_argument("--seed", required=True)
    pr.add_argument("--label", default=None)
    pr.add_argument("--state-dir", default=None)
    pf = sub.add_parser("fechar")
    pf.add_argument("missao_id")
    pf.add_argument("--resumo", required=True)
    pf.add_argument("--state-dir", default=None)
    args = p.parse_args(argv[1:])
    if args.cmd == "registrar":
        out = registrar(args.missao_id, args.cwd, args.contrato, args.seed,
                        label=args.label, state_dir=args.state_dir)
    else:
        out = fechar(args.missao_id, args.resumo, state_dir=args.state_dir)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
