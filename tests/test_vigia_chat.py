# tests/test_vigia_chat.py — VIGIA-CHAT-01 + AVISO-CHAT-ATIVO-01
# Prova a tool scripts/vigia_chat.sh: payload 1-linha com 5 chaves, dry-run
# sem rede, rollback VIGIA_CHAT=0, --send com gateway FAKE resolvendo a sessão
# ativa do sessions.json fake, exclusão de gh-notifications, falha tipada
# sessao_ativa_inexistente, dedupe/rate-limit, evento mission_end no spool do
# mission-event-bus (worker-vs-root via permissões, stub) e idempotência do patch 07.
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
def gateway_fake(tmp_path, monkeypatch):
    srv = HTTPServer(("127.0.0.1", 0), FakeHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    cred = tmp_path / "cred"
    cred.write_text("token-fake\n")
    CAPTURED.clear()
    monkeypatch.setenv("VIGIA_CHAT_API", "http://127.0.0.1:%d/v1/chat/completions" % srv.server_port)
    monkeypatch.setenv("VIGIA_CHAT_CRED", str(cred))
    monkeypatch.setenv("VIGIA_CHAT_RATELIMIT", str(tmp_path / "ratelimit.json"))
    monkeypatch.setenv("VIGIA_CHAT_LOGDIR", str(tmp_path / "logs"))
    monkeypatch.setenv("VIGIA_CHAT_SPOOL", str(tmp_path / "spool.jsonl"))
    yield srv
    srv.shutdown()


# alias retrocompat: VIGIA-CHAT-01 usava rota_fake
rota_fake = gateway_fake


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


def _mk_sessions_json(tmp_path, monkeypatch, entries):
    """Escreve sessions.json fake no formato do gateway e aponta o env pra ele."""
    sf = tmp_path / "sessions.json"
    sf.write_text(json.dumps({"sessions": entries}))
    monkeypatch.setenv("VIGIA_CHAT_SESSIONS_JSON", str(sf))
    return sf


# ---------------- payload / dry-run / rollback (VIGIA-CHAT-01) ----------------


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


# ---------------- AVISO-CHAT-ATIVO-01: sessão dinâmica ----------------


def test_send_resolve_sessao_ativa_do_sessions_json(tmp_path, monkeypatch, gateway_fake):
    _mk_run(tmp_path, monkeypatch)
    _mk_sessions_json(
        tmp_path,
        monkeypatch,
        [
            {"session_id": "sess_velha", "last_activity": 100, "surface": "tui"},
            {"session_id": "sess_ativa_20261010_214203_142245", "last_activity": 500, "surface": "tui"},
            {"session_id": "gh-notifications", "last_activity": 999, "surface": "tui"},
        ],
    )
    r = _run_tool(["VIGIA-CHAT-01", "--send"])
    assert r.returncode == 0
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out.get("ok") is True and out.get("delivered") is True
    assert out.get("sessao") == "sess_ativa_20261010_214203_142245"
    assert len(CAPTURED) == 1
    assert CAPTURED[0]["session"] == "sess_ativa_20261010_214203_142245"
    assert CAPTURED[0]["auth"] == "Bearer token-fake"
    assert "VIGIA-CHAT-01" in CAPTURED[0]["body"] and "PASS" in CAPTURED[0]["body"]


def test_gh_notifications_nunca_e_alvo(tmp_path, monkeypatch, gateway_fake):
    _mk_run(tmp_path, monkeypatch)
    _mk_sessions_json(
        tmp_path,
        monkeypatch,
        [
            {"session_id": "gh-notifications", "last_activity": 9999, "surface": "tui"},
        ],
    )
    r = _run_tool(["VIGIA-CHAT-01", "--send"])
    assert r.returncode == 0
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out.get("delivered") is False
    assert out.get("motivo") == "sessao_ativa_inexistente"
    assert CAPTURED == []


def test_sem_sessao_ativa_falha_tipada(tmp_path, monkeypatch, gateway_fake):
    _mk_run(tmp_path, monkeypatch)
    _mk_sessions_json(tmp_path, monkeypatch, [])
    r = _run_tool(["VIGIA-CHAT-01", "--send"])
    assert r.returncode == 0
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out.get("delivered") is False
    assert out.get("motivo") == "sessao_ativa_inexistente"
    assert CAPTURED == []


def test_sessions_json_inexistente_falha_tipada(tmp_path, monkeypatch, gateway_fake):
    _mk_run(tmp_path, monkeypatch)
    monkeypatch.setenv("VIGIA_CHAT_SESSIONS_JSON", str(tmp_path / "nao-existe.json"))
    monkeypatch.delenv("VIGIA_CHAT_SESSION", raising=False)
    r = _run_tool(["VIGIA-CHAT-01", "--send"])
    assert r.returncode == 0
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out.get("delivered") is False
    assert out.get("motivo") == "sessao_ativa_inexistente"
    assert CAPTURED == []


def test_dedupe_60s_max_1_aviso_por_missao(tmp_path, monkeypatch, gateway_fake):
    _mk_run(tmp_path, monkeypatch)
    _mk_sessions_json(
        tmp_path,
        monkeypatch,
        [{"session_id": "sess_ativa", "last_activity": 1, "surface": "tui"}],
    )
    r1 = _run_tool(["VIGIA-CHAT-01", "--send"])
    assert r1.returncode == 0
    out1 = json.loads(r1.stdout.strip().splitlines()[-1])
    assert out1.get("delivered") is True
    r2 = _run_tool(["VIGIA-CHAT-01", "--send"])
    assert r2.returncode == 0
    out2 = json.loads(r2.stdout.strip().splitlines()[-1])
    assert out2.get("delivered") is False
    assert out2.get("motivo") in ("ja_enviado", "dedupe_60s")
    assert len(CAPTURED) == 1


def test_falha_tipada_registra_log(tmp_path, monkeypatch, gateway_fake):
    _mk_run(tmp_path, monkeypatch)
    _mk_sessions_json(
        tmp_path,
        monkeypatch,
        [{"session_id": "sess_ativa", "last_activity": 1, "surface": "tui"}],
    )
    monkeypatch.setenv("VIGIA_CHAT_API", "http://127.0.0.1:1/v1/chat/completions")
    r = _run_tool(["VIGIA-CHAT-01", "--send"])
    assert r.returncode == 0
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out.get("delivered") is False
    assert out.get("motivo") == "ROTA_OFFLINE"
    logfile = tmp_path / "logs" / "vigia-chat-VIGIA-CHAT-01.log"
    assert logfile.exists()
    assert "ROTA_OFFLINE" in logfile.read_text()


def test_override_explicito_sessao_ainda_funciona(tmp_path, monkeypatch, gateway_fake):
    """VIGIA_CHAT_SESSION (override manual) continua respeitado p/ E2E e testes."""
    _mk_run(tmp_path, monkeypatch)
    r = _run_tool(["VIGIA-CHAT-01", "--send"], {"VIGIA_CHAT_SESSION": "sess_manual"})
    assert r.returncode == 0
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out.get("delivered") is True
    assert out.get("sessao") == "sess_manual"
    assert CAPTURED[0]["session"] == "sess_manual"


def test_override_gh_notifications_recusado(tmp_path, monkeypatch, gateway_fake):
    """Guard: override manual para gh-notifications também é recusado."""
    _mk_run(tmp_path, monkeypatch)
    r = _run_tool(["VIGIA-CHAT-01", "--send"], {"VIGIA_CHAT_SESSION": "gh-notifications"})
    assert r.returncode == 0
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out.get("delivered") is False
    assert CAPTURED == []


# ---------------- mission_end no spool do bus (escopo adicional) ----------------


def test_mission_end_append_spool_apos_post(tmp_path, monkeypatch, gateway_fake):
    _mk_run(tmp_path, monkeypatch)
    _mk_sessions_json(
        tmp_path,
        monkeypatch,
        [{"session_id": "sess_ativa", "last_activity": 1, "surface": "tui"}],
    )
    spool = tmp_path / "spool.jsonl"
    r = _run_tool(["VIGIA-CHAT-01", "--send"])
    assert r.returncode == 0
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out.get("delivered") is True
    assert out.get("spool") is True
    assert spool.exists()
    lines = [l for l in spool.read_text().splitlines() if l.strip()]
    assert len(lines) == 1
    ev = json.loads(lines[0])
    assert ev["kind"] == "mission_end"
    assert ev["missionId"] == "VIGIA-CHAT-01"


def test_spool_nao_escrivel_nao_quebra_tool(tmp_path, monkeypatch, gateway_fake):
    """Worker não escreve em /opt (stub root-vs-worker): append falha, tool segue 0."""
    _mk_run(tmp_path, monkeypatch)
    _mk_sessions_json(
        tmp_path,
        monkeypatch,
        [{"session_id": "sess_ativa", "last_activity": 1, "surface": "tui"}],
    )
    spool = tmp_path / "spool.jsonl"
    spool.write_text("")
    os.chmod(spool, 0o444)
    r = _run_tool(["VIGIA-CHAT-01", "--send"])
    assert r.returncode == 0
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out.get("delivered") is True  # aviso no chat foi entregue
    assert out.get("spool") is False  # evento no bus falhou honestamente


def test_spool_nao_escrito_sem_delivery(tmp_path, monkeypatch, gateway_fake):
    """Falha no POST => não appenda mission_end (evita reap sem aviso)."""
    _mk_run(tmp_path, monkeypatch)
    _mk_sessions_json(
        tmp_path,
        monkeypatch,
        [{"session_id": "sess_ativa", "last_activity": 1, "surface": "tui"}],
    )
    monkeypatch.setenv("VIGIA_CHAT_API", "http://127.0.0.1:1/v1/chat/completions")
    spool = tmp_path / "spool.jsonl"
    r = _run_tool(["VIGIA-CHAT-01", "--send"])
    assert r.returncode == 0
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out.get("delivered") is False
    assert not spool.exists()


# ---------------- falha de rota / resumo (retrocompat) ----------------


def test_rota_offline_tipado_exit0(tmp_path, monkeypatch, gateway_fake):
    _mk_run(tmp_path, monkeypatch)
    monkeypatch.setenv("VIGIA_CHAT_SESSION", "sess-offline-teste")
    monkeypatch.setenv("VIGIA_CHAT_API", "http://127.0.0.1:1/v1/chat/completions")
    r = _run_tool(["VIGIA-CHAT-01", "--send"])
    assert r.returncode == 0
    assert "ROTA_OFFLINE" in r.stdout + r.stderr


def test_sem_resumo_tipado_exit0(tmp_path, monkeypatch, gateway_fake):
    state = tmp_path / "state"
    state.mkdir()
    (state / "SEM-RUN-XYZ.json").write_text(json.dumps({"cwd": str(tmp_path)}))
    monkeypatch.setenv("VIGIA_CHAT_STATE_DIR", str(state))
    r = _run_tool(["SEM-RUN-XYZ"])
    assert r.returncode == 0
    assert "SEM_RESUMO" in r.stdout + r.stderr


# ---------------- patch 07 ----------------


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