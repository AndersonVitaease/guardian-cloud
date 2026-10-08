#!/usr/bin/env python3
"""Canário contínuo da fila — liveness honesta do pipeline (sem humano)."""
import argparse
import json
import os
import sys
import time
import uuid

FILA_DEFAULT = "/opt/mission-events/orchestrator-queue.jsonl"
LOG_DEFAULT = "/opt/mission-events/orchestrator-consumer.log"
BASE_RUNS_DEFAULT = "/home/worker/harness-s2/runs/"
PROMPTFILE_DEFAULT = "/home/worker/harness-s2/missao-canary-fila.md"
CWD_DEFAULT = "/home/worker/harness-s2"

PROMPTFILE_MINIMO = """# Missão canary — fila

Missão: report queue canary alive — crie o arquivo `CANARIO-OK.txt` no cwd da run com uma única linha `ok <iso-ts>`.

Regras:
- Escreva APENAS esse arquivo.
- Orçamento: US$ 0.1
- max_turns: 3

harness-stop:
file CANARIO-OK.txt
"""


def _worker_uid_gid():
    try:
        import pwd
        pw = pwd.getpwnam("worker")
        return pw.pw_uid, pw.pw_gid
    except Exception:
        return os.getuid(), os.getgid()


def _garantir_promptfile(path):
    """Garante que o promptFile existe (idempotente)."""
    if not os.path.isfile(path):
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(PROMPTFILE_MINIMO)


def enfileirar(fila_path, mission_id=None, promptfile=PROMPTFILE_DEFAULT):
    """Append intent de dispatch na fila; devolve dict do intent."""
    _garantir_promptfile(promptfile)
    ts = int(time.time())
    mid = mission_id or f"CANARIO-FILA-{ts}"
    intent = {
        "id": f"intent-canario-{ts}-{uuid.uuid4().hex[:8]}",
        "payload": {
            "missionId": mid,
            "promptFile": promptfile,
            "consequence": False,
            "cwd": CWD_DEFAULT,
            "spawnedBy": "operator",
            "queuedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "queued",
        },
        "priority": 0,
        "type": "mission_dispatch",
    }
    d = os.path.dirname(os.path.abspath(fila_path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(fila_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(intent, ensure_ascii=False) + "\n")
    return intent


def esperar_dispatch(log_path, mission_id, ciclos=6, intervalo=60):
    """Procura 'dispatch_via_harness: <mission_id>' no log; devolve dict."""
    alvo = f"dispatch_via_harness: {mission_id}"
    for _ in range(ciclos):
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                for linha in f:
                    if alvo in linha:
                        return {"despachado": True, "linha": linha.rstrip("\n")}
        except FileNotFoundError:
            pass
        if intervalo:
            time.sleep(intervalo)
    return {"despachado": False, "linha": None}


def checar_run(run_dir_base):
    """Run dir existe, é worker:worker e tem harness-pane.log."""
    if not os.path.isdir(run_dir_base):
        return {"ok": False, "motivo": "run dir ausente"}
    st = os.stat(run_dir_base)
    uid, gid = _worker_uid_gid()
    if st.st_uid != uid or st.st_gid != gid:
        return {"ok": False, "motivo": f"owner != worker:worker (uid={st.st_uid}, gid={st.st_gid})"}
    pane = os.path.join(run_dir_base, "harness-pane.log")
    if not os.path.isfile(pane):
        # layout real: pane.log mora em <mission>/run-*/harness-pane.log
        import glob
        subs = sorted(glob.glob(os.path.join(run_dir_base, "run-*", "harness-pane.log")),
                      key=os.path.getmtime)
        if not subs:
            return {"ok": False, "motivo": "harness-pane.log ausente"}
        pane = subs[-1]
    return {"ok": True, "motivo": pane}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Canário contínuo da fila")
    ap.add_argument("--fila", default=FILA_DEFAULT)
    ap.add_argument("--log", default=LOG_DEFAULT)
    ap.add_argument("--base-runs", default=BASE_RUNS_DEFAULT)
    ap.add_argument("--promptfile", default=PROMPTFILE_DEFAULT)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--ciclos", type=int, default=6)
    ap.add_argument("--intervalo", type=int, default=60)
    args = ap.parse_args(argv)

    intent = enfileirar(args.fila, promptfile=args.promptfile)
    mid = intent["payload"]["missionId"]
    desp = esperar_dispatch(args.log, mid, ciclos=args.ciclos, intervalo=args.intervalo)

    run_ok = {"ok": False, "motivo": "não despachado"}
    if desp["despachado"]:
        try:
            candidatos = sorted(
                (d for d in os.listdir(args.base_runs) if os.path.isdir(os.path.join(args.base_runs, d))),
                key=lambda d: os.path.getmtime(os.path.join(args.base_runs, d)),
                reverse=True,
            )
            if candidatos:
                run_ok = checar_run(os.path.join(args.base_runs, candidatos[0]))
            else:
                run_ok = {"ok": False, "motivo": "nenhum run dir"}
        except FileNotFoundError:
            run_ok = {"ok": False, "motivo": "base-runs ausente"}

    ok = desp["despachado"] and run_ok["ok"]
    status = "OK" if ok else "FAIL"
    linha = (f"CANÁRIO {mid} | {status} | despacho={'OK' if desp['despachado'] else 'FAIL'} "
             f"run={'OK' if run_ok['ok'] else 'FAIL'} owner=worker")
    print(linha)
    if args.json:
        print(json.dumps({"missionId": mid, "despachado": desp["despachado"],
                          "run": run_ok, "linha": desp["linha"]}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
