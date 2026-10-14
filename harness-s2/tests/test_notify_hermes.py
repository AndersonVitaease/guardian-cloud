# VIGIA-NASCER-03: testes hermeticos do notify_hermes.sh
import json, os, socket, subprocess, sys, tempfile, threading, time

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "notify_hermes.sh")


def _server(handler, timeout=8.0):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    srv.settimeout(timeout)
    port = srv.getsockname()[1]
    t = threading.Thread(target=handler, args=(srv,), daemon=True)
    t.start()
    return port, t


def _recv(srv):
    try:
        conn, _ = srv.accept()
        data = b""
        conn.settimeout(5)
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
        data = headers + b"\r\n\r\n" + rest
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}")
        conn.close()
        return data
    except Exception:
        return b""


def run_helper(env_extra, text="texto de teste"):
    env = dict(os.environ)
    env.pop("HERMES_NOTIFY_BEARER_FILE", None)
    env.update(env_extra)
    p = subprocess.run(["bash", SCRIPT], input=text.encode(), capture_output=True, env=env, timeout=30)
    return p


def test_payload_ok():
    got = {}
    def handler(srv):
        data = _recv(srv)
        got["data"] = data
    port, t = _server(handler)
    bf = tempfile.NamedTemporaryFile(mode="w", suffix=".key", delete=False)
    bf.write("segredo-teste\n")
    bf.close()
    p = run_helper({"HERMES_NOTIFY_URL": "http://127.0.0.1:%d/v1/chat/completions" % port,
                    "HERMES_NOTIFY_BEARER_FILE": bf.name}, "🛰️ NASCEU: missão X em voo — aba w0:p0, seed 7, budget 0.30")
    t.join(10)
    assert p.returncode == 0
    assert p.stdout.strip() == b"OK"
    body = got["data"].decode("utf-8", "replace")
    assert "NASCEU" in body and "seed 7" in body and "budget 0.30" in body
    assert "Authorization: Bearer segredo-teste" in body
    assert "X-Hermes-Session-Id: gh-notifications" in body
    os.unlink(bf.name)


def test_sem_bearer():
    p = run_helper({"HERMES_NOTIFY_URL": "http://127.0.0.1:1/v1/chat/completions",
                    "HERMES_NOTIFY_BEARER_FILE": "/tmp/nao-existe-%d" % time.time_ns()},
                   "texto")
    assert p.returncode == 0
    assert b"SEM_BEARER" in p.stdout


def test_rota_offline():
    bf = tempfile.NamedTemporaryFile(mode="w", suffix=".key", delete=False)
    bf.write("k\n")
    bf.close()
    p = run_helper({"HERMES_NOTIFY_URL": "http://127.0.0.1:1/v1/chat/completions",
                    "HERMES_NOTIFY_BEARER_FILE": bf.name}, "texto")
    assert p.returncode == 0
    assert b"ROTA_OFFLINE" in p.stdout
    os.unlink(bf.name)


def test_timeout():
    def handler(srv):
        try:
            conn, _ = srv.accept()
            time.sleep(30)  # nunca responde
        except Exception:
            pass
    port, t = _server(handler, timeout=8.0)
    bf = tempfile.NamedTemporaryFile(mode="w", suffix=".key", delete=False)
    bf.write("k\n")
    bf.close()
    t0 = time.time()
    p = run_helper({"HERMES_NOTIFY_URL": "http://127.0.0.1:%d/v1/chat/completions" % port,
                    "HERMES_NOTIFY_BEARER_FILE": bf.name}, "texto")
    dt = time.time() - t0
    assert p.returncode == 0
    assert b"ROTA_OFFLINE" in p.stdout
    assert dt < 20
    os.unlink(bf.name)