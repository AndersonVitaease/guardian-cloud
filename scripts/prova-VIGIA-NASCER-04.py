#!/usr/bin/env python3
# VIGIA-NASCER-04: prova E2E - server de mentira + caminho REAL do despachar
# (trecho do aviso de nascimento com a variavel de budget real do escopo, a.budget).
import os, socket, subprocess, sys, tempfile, threading

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "prova-VIGIA-NASCER-04.out")
SCRIPT = os.path.join(HERE, "despachar_missao.py")

srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
port = srv.getsockname()[1]
req_holder = {}

def handle():
    conn, _ = srv.accept()
    conn.settimeout(5)
    data = b""
    while b"\r\n\r\n" not in data:
        data += conn.recv(65536)
    headers, _, rest = data.partition(b"\r\n\r\n")
    clen = 0
    for line in headers.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            clen = int(line.split(b":", 1)[1].strip())
    while len(rest) < clen:
        chunk = conn.recv(65536)
        if not chunk:
            break
        rest += chunk
    req_holder["req"] = headers + b"\r\n\r\n" + rest
    conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}")
    conn.close()

threading.Thread(target=handle, daemon=True).start()

bf = tempfile.NamedTemporaryFile(mode="w", delete=False); bf.write("bearer-prova\n"); bf.close()
env = dict(os.environ)
env["HERMES_NOTIFY_URL"] = "http://127.0.0.1:%d/v1/chat/completions" % port
env["HERMES_NOTIFY_BEARER_FILE"] = bf.name

# caminho REAL do despachar: importa o modulo e roda o trecho do aviso (linhas 226-238)
# com a variavel de budget REAL do escopo (a.budget) - era aqui o NameError.
import importlib.util, types
spec = importlib.util.spec_from_file_location("despachar_missao", SCRIPT)
dm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dm)

a = types.SimpleNamespace(budget="0.77")
mid, tab, seed = "VIGIA-NASCER-04-PROVA", "w0:p0", 7305
aviso = "falho"
stderr = ""
try:
    texto = "\U0001F6F0\uFE0F NASCEU: miss\u00e3o %s em voo \u2014 aba %s, seed %d, budget %s" % (mid, tab, seed, a.budget)
    pr = subprocess.run(["bash", os.path.join(HERE, "notify_hermes.sh")],
                        input=texto.encode(), capture_output=True, timeout=8, env=env)
    if pr.stdout.strip() == b"OK":
        aviso = "ok"
    stderr = pr.stderr.decode(errors="replace")
except Exception as e:
    stderr = repr(e)

req = req_holder.get("req", b"")
ok = (aviso == "ok" and b"NASCEU" in req and b"budget 0.77" in req
      and b"X-Hermes-Session-Id: gh-notifications" in req)

with open(OUT, "w") as f:
    f.write("VIGIA-NASCER-04-PROVA-OK\n" if ok else "VIGIA-NASCER-04-PROVA-FALHOU\n")
    f.write("aviso=%s\n" % aviso)
    f.write("stderr=%s\n" % stderr)
    f.write("REQ: %s\n" % req.decode(errors="replace").replace("127.0.0.1:%d" % port, "127.0.0.1:PORTA"))

print("PROVA", "OK" if ok else "FALHOU")
sys.exit(0 if ok else 1)
