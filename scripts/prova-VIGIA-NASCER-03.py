# VIGIA-NASCER-03: prova E2E — server de mentira + helper notify_hermes.sh
import os, socket, subprocess, sys, tempfile, threading

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prova-VIGIA-NASCER-03.out")
TEXTO = "🛰️ NASCEU: missão VIGIA-NASCER-03-TESTE em voo — aba tab-x, seed 7304, budget 100"

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

p = subprocess.run(["bash", "scripts/notify_hermes.sh"], input=TEXTO.encode(), capture_output=True, env=env, timeout=30)

req = req_holder.get("req", b"")
ok = (p.returncode == 0 and p.stdout.strip() == b"OK"
      and b"X-Hermes-Session-Id: gh-notifications" in req
      and TEXTO.encode() in req)

with open(OUT, "w") as f:
    f.write("VIGIA-NASCER-03-PROVA-OK\n" if ok else "VIGIA-NASCER-03-PROVA-FALHOU\n")
    f.write("rc=%s stdout=%s stderr=%s\n" % (p.returncode, p.stdout, p.stderr))
    f.write("REQ: %s\n" % req.decode(errors="replace"))

print("PROVA", "OK" if ok else "FALHOU")
sys.exit(0 if ok else 1)