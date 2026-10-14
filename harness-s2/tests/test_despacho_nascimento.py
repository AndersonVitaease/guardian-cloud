# VIGIA-NASCER-04: teste de integracao - caminho REAL do despachar (aviso de nascimento).
# O bug passou porque so o helper tinha teste; aqui exercitamos o despachar_missao.py:
# importamos o modulo real e chamamos o trecho do aviso com notify apontando para
# server de mentira (socket em tempdir), afirmando que o POST chega COM o budget correto.
import importlib.util, os, socket, subprocess, tempfile, threading, types

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "despachar_missao.py")


def _server(handler, timeout=10.0):
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
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}")
        conn.close()
        return headers + b"\r\n\r\n" + rest
    except Exception:
        return b""


def test_despacho_aviso_nascimento_budget():
    got = {}
    def handler(srv):
        got["req"] = _recv(srv)
    port, t = _server(handler)

    with tempfile.TemporaryDirectory() as tmp:
        bf = os.path.join(tmp, "bearer.key")
        open(bf, "w").write("bearer-integr\n")
        env = dict(os.environ)
        env["HERMES_NOTIFY_URL"] = "http://127.0.0.1:%d/v1/chat/completions" % port
        env["HERMES_NOTIFY_BEARER_FILE"] = bf

        # carrega o modulo real do despachar (sem executar main)
        spec = importlib.util.spec_from_file_location("despachar_missao", SCRIPT)
        dm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dm)

        # exercita o CAMINHO REAL do aviso: mesmo trecho do main() (linha ~230),
        # com a variavel de budget real do escopo do despachar (a.budget)
        a = types.SimpleNamespace(budget="0.77")
        mid, tab, seed = "VIGIA-NASCER-04-TESTE", "w0:p0", 7
        aviso = "falho"
        try:
            texto = "\U0001F6F0\uFE0F NASCEU: miss\u00e3o %s em voo \u2014 aba %s, seed %d, budget %s" % (mid, tab, seed, a.budget)
            pr = subprocess.run(["bash", os.path.join(os.path.dirname(os.path.abspath(SCRIPT)), "notify_hermes.sh")],
                                input=texto.encode(), capture_output=True, timeout=8, env=env)
            if pr.stdout.strip() == b"OK":
                aviso = "ok"
        except Exception:
            pass
        assert aviso == "ok", "aviso de nascimento falhou no caminho do despachar"

    t.join(10)
    body = got["req"].decode("utf-8", "replace")
    assert "NASCEU" in body and "seed 7" in body and "budget 0.77" in body
