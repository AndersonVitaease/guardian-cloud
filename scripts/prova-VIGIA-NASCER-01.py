#!/usr/bin/env python3
"""VIGIA-NASCER-01: prova end-to-end com mock local.
Fixture: mock server capturando POSTs, bearer fake em tempdir, eventos jsonl.
Asserta exatamente 2 POSTs (1 nascimento + 1 morte) com textos esperados.
Última linha: VIGIA-NASCER-01-PROVA-OK
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HERE, "..", "tools-bash", "notify_missao.sh")
TOOL = os.path.abspath(TOOL)

capturados = []


class MockHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n).decode("utf-8", "replace")
        capturados.append({"auth": self.headers.get("Authorization"), "body": body})
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *a):
        pass


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/v1/chat/completions"

    with tempfile.TemporaryDirectory() as td:
        bf = os.path.join(td, "bearer.txt")
        with open(bf, "w") as f:
            f.write("fake-bearer-prova\n")
        jsonl = os.path.join(td, "vigia-M-PROVA.jsonl")
        eventos = [
            {"tipo": "inicio", "missao_id": "M-PROVA-01", "seed": 5150, "budget": "US$2.00"},
            {"tipo": "andamento", "missao_id": "M-PROVA-01", "passo": 1},
            {"tipo": "fim", "missao_id": "M-PROVA-01", "veredito": "PASS", "custo": "1.23", "turnos": 9},
        ]
        with open(jsonl, "w") as f:
            for e in eventos:
                f.write(json.dumps(e) + "\n")
        ev_files = []
        for i, e in enumerate(eventos):
            p = os.path.join(td, f"ev{i}.json")
            with open(p, "w") as f:
                json.dump(e, f)
            ev_files.append(p)

        env = dict(os.environ, NOTIFY_URL=url, NOTIFY_BEARER_FILE=bf)
        for p in ev_files:
            r = subprocess.run(["bash", TOOL, p], env=env, capture_output=True, text=True, timeout=15)
            assert r.returncode == 0, (p, r.stdout, r.stderr)

        assert len(capturados) == 2, f"esperava 2 POSTs, vei {len(capturados)}"
        t0 = json.loads(capturados[0]["body"])["messages"][0]["content"]
        t1 = json.loads(capturados[1]["body"])["messages"][0]["content"]
        assert "NASCEU" in t0 and "M-PROVA-01" in t0 and "5150" in t0 and "RUN:M-PROVA-01#s5150" in t0, t0
        assert "MORREU" in t1 and "PASS" in t1 and "1.23" in t1 and "9" in t1, t1
        assert capturados[0]["auth"] == "Bearer fake-bearer-prova"
    srv.shutdown()
    print("VIGIA-NASCER-01-PROVA-OK")


if __name__ == "__main__":
    main()