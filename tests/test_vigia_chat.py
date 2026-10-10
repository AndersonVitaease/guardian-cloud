# tests/test_vigia_chat.py — VIGIA-CHAT-01
# Prova a tool scripts/vigia_chat.sh: payload 1-linha com 5 chaves, dry-run
# sem rede, rollback VIGIA_CHAT=0, --send com rota fake, ROTA_OFFLINE tipado
# e idempotência do patch 07.
import json
import os
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOL = os.path.join(REPO, "scripts", "vigia_chat.sh")
PATCH = os.path.join(REPO, "patches", "07-vigia-chat-hook.sh")
DESP = os.path.join(REPO, "scripts", "despachar_missao.py")

CAPTURED = []


class FakeHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n).decode("utf-8")
        CAPTURED.append(
            {
                "auth": self.headers.get("Authorization"),
                "session": self.headers.get("X-Hermes-Session-Id"),
                "body": body,
            }
        )
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"ok":true}')

    def log_message(self, *a):
        pass


@pytest.fixture()
def rota_fake(tmp_path, monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), FakeHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    cred = tmp_path / "cred"
    cred.write_text("token-fake\n")
    CAPTURED.clear()
    monkeypatch.setenv("VIGIA_CHAT_API", "http://127.0.0.1:%d/v1/chat/completions" % srv.server_port)
    monkeypatch.setenv("VIGIA_CHAT_CRED", str(cred))
    monkeypatch.setenv("VIGIA_CHAT_SESSION", "gh-notifications")
    yield srv
    srv.shutdown()


def _run_tool(args, extra_env=None):
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", TOOL] + args, capture_output=True, text=True, env=env, timeout=30
    )


def _mk_run(tmp_path, monkeypatch, missao="VIGIA-CHAT-01"):
    """Cria run-dir fake com resumo.json + ledger apontando pra ele."""
    run_dir = tmp_path / "runs" / missao
    run_dir.mkdir(parents=True)
    (run_dir / "resumo.json").write_text(
        json.dumps({"veredito": "PASS", "turnos": 7, "custo_usd": 1.25})
    )
    state = tmp_path / "state"
    state.mkdir()
    (state / (missao + ".json")).write_text(
        json.dumps({"cwd": str(run_dir), "aba": "pane-teste"})
    )
    monkeypatch.setenv("VIGIA_CHAT_STATE_DIR", str(state))
    return run_dir


def test_payload_5_chaves_1_linha(tmp_path, monkeypatch, rota_fake):
    _mk_run(tmp_path, monkeypatch)
    r = _run_tool(["VIGIA-CHAT-01"])
    assert r.returncode == 0
    lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
    assert len(lines) == 1
    p = json.loads(lines[0])
    assert list(p.keys()) == ["missao", "veredito", "custo_usd", "turnos", "aba"]
    assert p["missao"] == "VIGIA-CHAT-01"
    assert p["veredito"] == "PASS"
    assert p["custo_usd"] == 1.25
    assert p["turnos"] == 7
    assert p["aba"] == "pane-teste"


def test_dry_run_nao_faz_post(tmp_path, monkeypatch, rota_fake):
    _mk_run(tmp_path, monkeypatch)
    r = _run_tool(["VIGIA-CHAT-01"])
    assert r.returncode == 0
    assert CAPTURED == []


def test_rollback_vigia_chat_0(tmp_path, monkeypatch, rota_fake):
    _mk_run(tmp_path, monkeypatch)
    r = _run_tool(["VIGIA-CHAT-01", "--send"], {"VIGIA_CHAT": "0"})
    assert r.returncode == 0
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out.get("rollback") is True
    assert CAPTURED == []


def test_send_rota_fake_ok(tmp_path, monkeypatch, rota_fake):
    _mk_run(tmp_path, monkeypatch)
    r = _run_tool(["VIGIA-CHAT-01", "--send"])
    assert r.returncode == 0
    assert len(CAPTURED) == 1
    assert CAPTURED[0]["auth"] == "Bearer token-fake"
    assert CAPTURED[0]["session"] == "gh-notifications"
    body = CAPTURED[0]["body"]
    assert "VIGIA-CHAT-01" in body and "PASS" in body


def test_rota_offline_tipado_exit0(tmp_path, monkeypatch, rota_fake):
    _mk_run(tmp_path, monkeypatch)
    monkeypatch.setenv("VIGIA_CHAT_API", "http://127.0.0.1:1/v1/chat/completions")
    r = _run_tool(["VIGIA-CHAT-01", "--send"])
    assert r.returncode == 0
    assert "ROTA_OFFLINE" in r.stdout + r.stderr


def test_sem_resumo_tipado_exit0(tmp_path, monkeypatch, rota_fake):
    state = tmp_path / "state"
    state.mkdir()
    (state / "SEM-RUN-XYZ.json").write_text(json.dumps({"cwd": str(tmp_path)}))
    monkeypatch.setenv("VIGIA_CHAT_STATE_DIR", str(state))
    r = _run_tool(["SEM-RUN-XYZ"])
    assert r.returncode == 0
    assert "SEM_RESUMO" in r.stdout + r.stderr


def test_patch07_idempotente(tmp_path, monkeypatch):
    copia = tmp_path / "despachar_missao.py"
    shutil.copy(DESP, copia)
    monkeypatch.setenv("DESPACHAR_MISSAO_ALVO", str(copia))
    monkeypatch.setenv("TB_TOOLS", str(tmp_path / "tools"))
    for _ in range(2):
        r = subprocess.run(
            ["bash", PATCH, "--apply"], capture_output=True, text=True, timeout=30
        )
        assert r.returncode == 0, r.stderr
    txt = copia.read_text()
    assert txt.count("vigia_chat.sh") == 1


def test_patch07_dry_run_nao_escreve(tmp_path, monkeypatch):
    copia = tmp_path / "despachar_missao.py"
    shutil.copy(DESP, copia)
    before = copia.read_text()
    monkeypatch.setenv("DESPACHAR_MISSAO_ALVO", str(copia))
    r = subprocess.run(["bash", PATCH], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0
    assert copia.read_text() == before