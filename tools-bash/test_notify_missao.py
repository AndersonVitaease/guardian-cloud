"""VIGIA-NASCER-01: suíte de testes com MOCK local."""
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notify_missao.sh")


class MockHandler(BaseHTTPRequestHandler):
    capturados = []

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n).decode("utf-8", "replace")
        MockHandler.capturados.append(
            {"auth": self.headers.get("Authorization"), "body": body}
        )
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *a):
        pass


@pytest.fixture()
def mock(tmp_path):
    MockHandler.capturados = []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/v1/chat/completions"
    bf = tmp_path / "bearer.txt"
    bf.write_text("fake-bearer-123\n")
    env = dict(os.environ, NOTIFY_URL=url, NOTIFY_BEARER_FILE=str(bf))
    yield env, MockHandler.capturados
    srv.shutdown()


def evento(tipo, **kw):
    e = {"tipo": tipo, "missao_id": "M-TEST-01"}
    e.update(kw)
    return e


def rodar(env, ev, tmp_path):
    f = tmp_path / "ev.json"
    f.write_text(json.dumps(ev))
    return subprocess.run(["bash", TOOL, str(f)], env=env, capture_output=True, text=True, timeout=15)


def test_inicio_formata(mock, tmp_path):
    env, cap = mock
    r = rodar(env, evento("inicio", seed=5150, budget="US$2.00"), tmp_path)
    assert r.returncode == 0
    assert len(cap) == 1
    txt = json.loads(cap[0]["body"])["messages"][0]["content"]
    assert "NASCEU" in txt and "M-TEST-01" in txt and "5150" in txt
    assert "RUN:M-TEST-01#s5150" in txt


def test_fim_formata(mock, tmp_path):
    env, cap = mock
    r = rodar(env, evento("fim", veredito="PASS", custo="1.23", turnos=7), tmp_path)
    assert r.returncode == 0
    assert len(cap) == 1
    txt = json.loads(cap[0]["body"])["messages"][0]["content"]
    assert "MORREU" in txt and "PASS" in txt and "1.23" in txt and "7" in txt


def test_andamento_nao_chama_rede(mock, tmp_path):
    env, cap = mock
    r = rodar(env, evento("andamento", passo=3), tmp_path)
    assert r.returncode == 0
    assert cap == []


def test_sem_bearer(tmp_path):
    f = tmp_path / "ev.json"
    f.write_text(json.dumps(evento("inicio", seed=1)))
    env = dict(os.environ)
    env.pop("NOTIFY_BEARER_FILE", None)
    r = subprocess.run(["bash", TOOL, str(f)], env=env, capture_output=True, text=True, timeout=15)
    assert r.returncode == 0
    assert "SEM_BEARER" in r.stdout


def test_rota_morta(tmp_path):
    f = tmp_path / "ev.json"
    f.write_text(json.dumps(evento("inicio", seed=1)))
    bf = tmp_path / "b.txt"
    bf.write_text("x")
    env = dict(os.environ, NOTIFY_URL="http://127.0.0.1:9/nao", NOTIFY_BEARER_FILE=str(bf))
    r = subprocess.run(["bash", TOOL, str(f)], env=env, capture_output=True, text=True, timeout=15)
    assert r.returncode == 0
    assert "ROTA_OFFLINE" in r.stdout


def test_nunca_exit_nao_zero(mock, tmp_path):
    env, cap = mock
    for ev in (evento("inicio", seed=1), evento("fim", veredito="FAIL"), evento("andamento"), evento("x")):
        assert rodar(env, ev, tmp_path).returncode == 0