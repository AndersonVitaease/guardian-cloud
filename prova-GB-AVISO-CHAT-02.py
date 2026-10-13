#!/usr/bin/env python3
# prova-GB-AVISO-CHAT-02.py — prova hermetica (mktemp) do aviso_chat.sh
# (a) gateway fake 200 -> aviso entregue, exit 0, log em /tmp;
# (b) gateway fake 500 3x -> recusa tipada + evento AVISO_ENTREGA_FALHOU no spool fake;
# (c) sessao ativa resolvida do sessions.json fake.
import http.server, json, os, socket, subprocess, sys, tempfile, threading, time

WT = "/home/worker/wt-GB-AVISO-CHAT-02"
SCRIPT = os.path.join(WT, "scripts", "aviso_chat.sh")
FAILS = {"n": 0}

class OK(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200); self.end_headers(); self.wfile.write(b"{}")
    def log_message(self, *a): pass

class ERR(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(500); self.end_headers(); self.wfile.write(b"err")
    def log_message(self, *a): pass

def serve(cls):
    s = socket.socket(); s.bind(("127.0.0.1", 0)); s.listen(1)
    port = s.getsockname()[1]
    s.close()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, port

def run(env, msg="prova aviso"):
    pr = subprocess.run(["bash", SCRIPT, msg], capture_output=True, text=True, env=env, timeout=180)
    try:
        return pr.returncode, json.loads(pr.stdout.strip().splitlines()[-1])
    except Exception:
        return pr.returncode, {"raw": pr.stdout.strip(), "err": pr.stderr.strip()[-200:]}

def main():
    tmp = tempfile.mkdtemp(prefix="prova-gb-aviso-")
    sess_json = os.path.join(tmp, "sessions.json")
    with open(sess_json, "w") as f:
        json.dump({"sessions": [
            {"session_id": "gh-notifications", "last_activity": 999},
            {"session_id": "sess-ativa-prova", "last_activity": 1234567890},
        ]}, f)
    cred = os.path.join(tmp, "cred")
    open(cred, "w").write("tok-prova")
    spool = os.path.join(tmp, "spool.jsonl")

    base = dict(os.environ, AVISO_SESSIONS_JSON=sess_json, AVISO_CRED=cred,
                AVISO_SPOOL=spool, AVISO_TIMEOUT="5")

    # (c)+(a) gateway 200
    srv_ok, port_ok = serve(OK)
    env = dict(base, AVISO_API="http://127.0.0.1:%d/v1/chat/completions" % port_ok)
    rc, out = run(env)
    assert rc == 0, ("exit", rc, out)
    assert out.get("delivered") is True, out
    assert out.get("sessao") == "sess-ativa-prova", out  # (c) gh-notifications ignorada
    srv_ok.shutdown()

    # (b) gateway 500 3x -> retry esgotado, evento no spool
    srv_err, port_err = serve(ERR)
    env = dict(base, AVISO_API="http://127.0.0.1:%d/v1/chat/completions" % port_err)
    rc, out = run(env)
    assert rc == 0, ("exit fail-open", rc, out)
    assert out.get("delivered") is False and out.get("motivo") == "ROTA_OFFLINE", out
    assert out.get("spool") is True, out
    ev = json.loads(open(spool).read().strip().splitlines()[-1])
    assert ev.get("kind") == "AVISO_ENTREGA_FALHOU", ev
    srv_err.shutdown()

    print("GB-AVISO-CHAT-02-PROVA-OK")

if __name__ == "__main__":
    main()