#!/usr/bin/env python3
"""Prova hermética GB-STREAM-CRU-01 — espelho transmite transcript cru.

Sem rede, sem tokens. Tempdir com run dir fake:
  <tmp>/BASE/tentativa-1/run-FAKE/harness-pane.log   (trail estruturado fake)
  <tmp>/BASE/tentativa-1/run-FAKE/harness-trail.jsonl (transcript cru fake)

Prova:
 (a) o tail exposto ao streamer (saída de _trail_cru.py sobre o trail jsonl)
     vem do transcript cru — contém "preparing <tool>..." e fala do agente;
 (b) o pane log continua inteiro (bytes preservados após rodar o conversor);
 (c) transcript ausente não derruba nada — espelho-segue.sh roda e segue vivo,
     e o conversor sobre stdin vazio sai 0 sem saída.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

OK = True


def check(nome, cond, det=""):
    global OK
    print(("PASS" if cond else "FAIL") + " " + nome + (" | " + det if det else ""))
    if not cond:
        OK = False


def rodar(args, stdin=None, timeout=20):
    return subprocess.run(args, input=stdin, capture_output=True, text=True, timeout=timeout)


def main():
    tmp = tempfile.mkdtemp(prefix="streamcru-")
    rundir = os.path.join(tmp, "BASE", "tentativa-1", "run-FAKE")
    os.makedirs(rundir)
    pane = os.path.join(rundir, "harness-pane.log")
    trail = os.path.join(rundir, "harness-trail.jsonl")

    pane_txt = "turno 5 | Write | 0ms | $0.00 | ok | path\n"
    with open(pane, "w") as f:
        f.write(pane_txt)
    evs = [
        {"ts": "T1", "turno": 1, "tool": "llm", "stop_reason": "tool_use", "bytes": 720},
        {"ts": "T2", "turno": 1, "tool": "Bash", "input": '{"command": "ls scripts"}', "custo_usd": 0.0},
        {"ts": "T3", "turno": 2, "tool": "Write", "input": {"path": "a.md"}, "custo_usd": 0.001},
    ]
    with open(trail, "w") as f:
        for e in evs:
            f.write(json.dumps(e) + "\n")

    aqui = os.path.dirname(os.path.abspath(__file__))
    conv = os.path.join(aqui, "_trail_cru.py")

    # (a) tail exposto ao streamer vem do transcript cru
    r = rodar(["python3", conv], stdin=open(trail).read())
    check("cru-saida-tem-preparing", "preparing Bash" in r.stdout and "preparing Write" in r.stdout, r.stdout.strip())
    check("cru-saida-tem-fala-agente", "agente turno 1" in r.stdout)
    check("cru-uma-acao-por-linha", all(l.strip() for l in r.stdout.strip().splitlines()) and len(r.stdout.strip().splitlines()) == 3)
    check("cru-exit0", r.returncode == 0)

    # (b) pane log continua inteiro
    with open(pane) as f:
        check("pane-inteiro", f.read() == pane_txt)

    # (c) transcript ausente não derruba nada
    os.remove(trail)
    r2 = rodar(["python3", conv], stdin="")
    check("sem-trail-exit0-sem-saida", r2.returncode == 0 and r2.stdout == "")
    # espelho-segue.sh segue vivo sem trail (loop roda, mata após 4s)
    segue = os.path.join(aqui, "espelho-segue.sh")
    p = subprocess.Popen(["bash", segue, os.path.join(tmp, "BASE")],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         start_new_session=True)
    time.sleep(4)
    vivo = p.poll() is None
    os.killpg(os.getpgid(p.pid), 9)  # mata o grupo: bash + tails
    p.wait()
    check("segue-vivo-sem-trail", vivo)
    # e com trail presente também emite a linha de acompanhamento
    with open(trail, "w") as f:
        for e in evs:
            f.write(json.dumps(e) + "\n")
    p = subprocess.Popen(["bash", segue, os.path.join(tmp, "BASE")],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                         start_new_session=True)
    time.sleep(4)
    vivo2 = p.poll() is None
    os.killpg(os.getpgid(p.pid), 9)
    out, _ = p.communicate()
    check("segue-acompanha", "acompanhando" in out and vivo2)

    print("RESUMO: " + ("0 falhas" if OK else "FALHAS"))
    sys.exit(0 if OK else 1)


if __name__ == "__main__":
    main()