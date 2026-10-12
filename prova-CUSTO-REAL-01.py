#!/usr/bin/env python3
"""Prova hermetica MOPS-CUSTO-REAL-01 — custo EXATO por sessao do state.db.

Cobra (RESUMO: 0 falhas -> marcador CUSTO-REAL-01-OK):
 1. custo_sessoes.sh --data sobre db FAKE: total e lista corretos;
 2. custo_sessoes.sh --sessao: custo exato da sessao;
 3. sessao ausente -> CUSTO_SESSAO_AUSENTE tipado (exit 3);
 4. espelho.sh --registrar-custo com log contendo "Session: 20261012_999999_abc"
    -> .espelho.json ganha custo_usd do db fake + session_id;
 5. notifica_pouso.sh --espelho-json ... "-" -> POST /api/notify com custoUsd REAL
    (servidor de captura); json sem custo -> custoUsd null + CUSTO_AUSENTE;
 6. leitura RO garantida: db fake fica com mtime inalterado.
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

HARNESS = "/home/worker/harness-s2"
CUSTO = os.path.join(HARNESS, "scripts", "custo_sessoes.sh")
ESPELHO = os.path.join(HARNESS, "scripts", "espelho.sh")
NOTIFICA = os.path.join(HARNESS, "scripts", "notifica_pouso.sh")

falhas = []


def check(nome, cond, detalhe=""):
    status = "OK" if cond else "FAIL"
    print("%s: %s %s" % (status, nome, detalhe))
    if not cond:
        falhas.append(nome)


def rodar(cmd, env, entrada=None):
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=180)


def main():
    tmp = tempfile.mkdtemp(prefix="custo-real-01-")
    db = os.path.join(tmp, "state.db")
    # db fake: schema minimo da session_model_usage + 2 sessoes
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE session_model_usage ("
        " session_id TEXT NOT NULL, model TEXT NOT NULL,"
        " api_call_count INTEGER NOT NULL DEFAULT 0,"
        " input_tokens INTEGER NOT NULL DEFAULT 0,"
        " output_tokens INTEGER NOT NULL DEFAULT 0,"
        " cache_read_tokens INTEGER NOT NULL DEFAULT 0,"
        " estimated_cost_usd REAL NOT NULL DEFAULT 0,"
        " first_seen REAL, last_seen REAL, task TEXT DEFAULT '',"
        " PRIMARY KEY (session_id, model, task))"
    )
    ep = time.mktime(datetime(2026, 10, 12, 12, 0, 0).timetuple())
    custo_a = 0.00312876 + 0.00004745  # duas linhas da mesma sessao
    conn.executemany(
        "INSERT INTO session_model_usage (session_id, model, api_call_count,"
        " input_tokens, output_tokens, cache_read_tokens, estimated_cost_usd,"
        " first_seen, last_seen, task) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("20261012_999999_abc", "z-ai/glm-5.3-flash", 3, 14870, 153, 27392,
             0.00312876, ep, ep + 10, ''),
            ("20261012_999999_abc", "z-ai/glm-5.3-flash", 1, 263, 16, 0,
             0.00004745, ep, ep + 10, "title_generation"),
            ("20261012_888888_def", "z-ai/glm-5.3-flash", 2, 900, 60, 100,
             0.0205, ep, ep + 10, ''),
        ],
    )
    conn.commit()
    conn.close()
    mtime_antes = os.path.getmtime(db)

    env = dict(os.environ, GUARDIAN_STATE_DB=db)
    # 1. total do dia
    r = rodar([CUSTO, "--data", "2026-10-12"], env)
    check("custo--data-exit0", r.returncode == 0, r.stderr[:200])
    try:
        out = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        out = {}
    esperado_total = round(custo_a + 0.0205, 6)
    check("custo--data-total", out.get("total_usd") == esperado_total,
          "total=%s esperado=%s" % (out.get("total_usd"), esperado_total))
    check("custo--data-2sessoes", len(out.get("sessoes", [])) == 2,
          str(len(out.get("sessoes", []))))
    check("custo--data-json-1linha", len(r.stdout.strip().splitlines()) == 1)

    # 2. custo exato de uma sessao (soma das 2 linhas)
    r = rodar([CUSTO, "--sessao", "20261012_999999_abc"], env)
    try:
        sj = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        sj = {}
    check("custo--sessao-exato", sj.get("custo_usd") == round(custo_a, 6)
          and sj.get("calls") == 4, json.dumps(sj))
    check("custo--sessao-exit0", r.returncode == 0)

    # 3. sessao ausente -> tipado
    r = rodar([CUSTO, "--sessao", "20261012_nada_zzz"], env)
    check("custo--ausente-tipado", "CUSTO_SESSAO_AUSENTE" in r.stdout
          and r.returncode == 3, "rc=%s out=%s" % (r.returncode, r.stdout[:120]))

    # 4. espelho: pouso com log contendo Session -> json ganha custo real
    esp_json = os.path.join(tmp, "MOPS-CUSTO-REAL-01.espelho.json")
    with open(esp_json, "w") as fh:
        json.dump({"id": "MOPS-CUSTO-REAL-01", "status": "running", "ms": 1}, fh)
    log = os.path.join(tmp, "pane.log")
    with open(log, "w") as fh:
        fh.write("ruido antes\nSession: 20261012_999999_abc\nESPELHO-EXIT-1-0\n")
    r = rodar([ESPELHO, "--registrar-custo", "MOPS-CUSTO-REAL-01", log, esp_json], env)
    check("espelho-registrar-exit0", r.returncode == 0, r.stderr[:200])
    try:
        with open(esp_json) as fh:
            ej = json.load(fh)
    except Exception:
        ej = {}
    check("espelho-json-custo", ej.get("custo_usd") == round(custo_a, 6),
          json.dumps(ej))
    check("espelho-json-session", ej.get("session_id") == "20261012_999999_abc",
          str(ej.get("session_id")))
    # log sem Session -> custo_usd null, sem quebrar
    log2 = os.path.join(tmp, "pane2.log")
    with open(log2, "w") as fh:
        fh.write("so ruido\n")
    esp_json2 = os.path.join(tmp, "SEM-SESSAO.espelho.json")
    with open(esp_json2, "w") as fh:
        json.dump({"id": "SEM-SESSAO"}, fh)
    r = rodar([ESPELHO, "--registrar-custo", "SEM-SESSAO", log2, esp_json2], env)
    with open(esp_json2) as fh:
        ej2 = json.load(fh)
    check("espelho-sem-session-null", ej2.get("custo_usd") is None
          and r.returncode == 0, json.dumps(ej2))

    # 5. notifica_pouso com custo real do json (servidor de captura)
    recebidas = []

    class Cap(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            recebidas.append(json.loads(self.rfile.read(n).decode()))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Cap)
    porta = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    envf = os.path.join(tmp, "env.fake")
    with open(envf, "w") as fh:
        fh.write("GUARDIAN_NOTIFY_TOKEN=token-falso-de-prova\n")
    envn = dict(os.environ, GUARDIAN_PORT=str(porta), GUARDIAN_NOTIFY_ENV=envf)
    r = rodar([NOTIFICA, "--espelho-json", esp_json, "MOPS-CUSTO-REAL-01",
               "PASS", "-", "21000"], envn)
    time.sleep(0.3)
    check("notifica-exit0", r.returncode == 0, r.stderr[:200])
    body = recebidas[0] if recebidas else {}
    check("notifica-custo-real", body.get("custoUsd") == round(custo_a, 6),
          json.dumps(body))
    check("notifica-veredito", body.get("veredito") == "PASS"
          and body.get("missionId") == "MOPS-CUSTO-REAL-01")

    # json sem custo -> custoUsd null + CUSTO_AUSENTE no stderr
    recebidas.clear()
    r = rodar([NOTIFICA, "--espelho-json", esp_json2, "SEM-SESSAO",
               "PASS", "-", "500"], envn)
    time.sleep(0.3)
    body2 = recebidas[0] if recebidas else {}
    check("notifica-sem-custo-null", body2.get("custoUsd") is None
          and "CUSTO_AUSENTE" in r.stderr, json.dumps(body2) + " | " + r.stderr[:120])

    # 6. leitura RO: db fake intacto
    check("db-ro-mtime", os.path.getmtime(db) == mtime_antes)

    srv.shutdown()
    print("")
    print("RESUMO: %d falhas" % len(falhas))
    if falhas:
        print("FALHAS: " + ", ".join(falhas))
        print("CUSTO-REAL-01-FAIL")
        return 1
    print("CUSTO-REAL-01-OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
