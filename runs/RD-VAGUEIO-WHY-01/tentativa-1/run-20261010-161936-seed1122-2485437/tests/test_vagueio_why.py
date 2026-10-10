import json
import subprocess
import os

import pytest

TOOL = os.path.join(os.path.dirname(__file__), "..", "tools-bash", "vagueio_why.sh")


def run(mid, state_dir):
    env = dict(os.environ, MISSION_STATE_DIR=str(state_dir))
    p = subprocess.run(["bash", TOOL, mid], env=env, capture_output=True, text=True)
    assert p.returncode == 0
    line = p.stdout.strip().splitlines()[0]
    data = json.loads(line)
    assert data.get("tool") == "vagueio_why"
    assert data.get("untrusted") is True
    return data


def setup_ledger(state_dir, mid, **extra):
    state_dir.mkdir(parents=True, exist_ok=True)
    ledger = {"missionId": mid, "veredito": "ok", "custo_usd": 0.01}
    ledger.update(extra)
    (state_dir / f"{mid}.json").write_text(json.dumps(ledger))


def setup_trail(state_dir, mid, events):
    (state_dir / f"{mid}.events.tail.jsonl").write_text(
        "\n".join(json.dumps(e) for e in events) + "\n"
    )


def ev(kind, **kw):
    d = {"kind": kind}
    d.update(kw)
    return d


@pytest.fixture
def sd(tmp_path):
    return tmp_path


def test_invalid_mission_id(sd):
    d = run("id inválida!", sd)
    assert d["error"] == "INVALID_MISSION_ID"


def test_ledger_not_found(sd):
    d = run("M-1", sd)
    assert d["error"] == "LEDGER_NOT_FOUND"


def test_sem_trail(sd):
    setup_ledger(sd, "M-1")
    d = run("M-1", sd)
    assert d["causa"] == "sem_trail"
    assert d["evidencias"] == []


def test_ambiente(sd):
    setup_ledger(sd, "M-1")
    setup_trail(sd, "M-1", [
        ev("leitura", resultado="LEITURA_RECUSADA"),
        ev("leitura", resultado="LEITURA_MECANICA_RECUSADA"),
        ev("leitura", resultado="LEITURA_RECUSADA"),
    ])
    d = run("M-1", sd)
    assert d["causa"] == "ambiente"
    assert any("LEITURA_RECUSADA" in json.dumps(e) for e in d["evidencias"])


def test_loop_leitura(sd):
    setup_ledger(sd, "M-2")
    setup_trail(sd, "M-2", [
        ev("leitura", caminho="/a/x.py"),
        ev("leitura", caminho="/a/x.py"),
        ev("leitura", caminho="/a/x.py"),
    ])
    d = run("M-2", sd)
    assert d["causa"] == "loop_leitura"
    assert any("/a/x.py" in json.dumps(e) for e in d["evidencias"])


def test_stop_inviavel(sd):
    setup_ledger(sd, "M-3", stops_parseados=0, stop_vacuo="test -f x")
    setup_trail(sd, "M-3", [ev("stop", conteudo="test -f x")])
    d = run("M-3", sd)
    assert d["causa"] == "stop_inviavel"


def test_cwd(sd):
    setup_ledger(sd, "M-4")
    setup_trail(sd, "M-4", [
        ev("stop", resultado="BAD_ARGS"),
        ev("cwd", caminho="/nao/existe"),
    ])
    d = run("M-4", sd)
    assert d["causa"] == "cwd"


def test_sem_vagueio(sd):
    setup_ledger(sd, "M-5")
    setup_trail(sd, "M-5", [ev("leitura", caminho="/a.py"), ev("stop", resultado="OK")])
    d = run("M-5", sd)
    assert d["causa"] == "sem_vagueio"


def test_verdict_grafia_alternativa(sd):
    setup_ledger(sd, "M-6", verdict="verdict-alt", veredito=None)
    setup_trail(sd, "M-6", [ev("leitura", caminho="/a.py")])
    d = run("M-6", sd)
    assert d["veredito"] == "verdict-alt"


def test_json_uma_linha_untrusted_notice(sd):
    setup_ledger(sd, "M-7")
    setup_trail(sd, "M-7", [ev("leitura", resultado="LEITURA_RECUSADA")])
    env = dict(os.environ, MISSION_STATE_DIR=str(sd))
    p = subprocess.run(["bash", TOOL, "M-7"], env=env, capture_output=True, text=True)
    assert p.returncode == 0
    lines = [l for l in p.stdout.strip().splitlines() if l.strip()]
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data.get("untrusted") is True
    assert "notice" in data