import json, os, subprocess, time
import pytest

TOOL = os.path.join("tools-bash", "ledger_reap.sh")
TERMINAIS = {"closed", "failed", "cancelled"}


def run_tool(state_dir, units_cmd, extra=()):
    env = dict(os.environ)
    env["MISSION_STATE_DIR"] = str(state_dir)
    env["LEDGER_REAP_UNITS_CMD"] = units_cmd
    env["LEDGER_REAP_LEDGER_SCRIPT"] = str(state_dir / "fake_ledger.py")
    env["FAKE_STATE"] = str(state_dir)
    p = subprocess.run(["bash", TOOL, *extra], capture_output=True, text=True, env=env)
    assert p.returncode == 0
    lines = [l for l in p.stdout.strip().splitlines() if l.strip()]
    assert len(lines) == 1, "JSON deve ser 1 linha"
    return json.loads(lines[0])


def write_ledger(state_dir, mid, status, extra=None):
    data = {"missionId": mid, "status": status, "custo_usd": 1.5}
    if extra:
        data.update(extra)
    f = state_dir / (mid + ".json")
    f.write_text(json.dumps(data))
    return f


@pytest.fixture
def state(tmp_path):
    (tmp_path / "fake_ledger.py").write_text(
        "import sys,os\n"
        "open(os.path.join(os.environ['FAKE_STATE'], sys.argv[2] + '.closed'), 'w').write('ok')\n"
    )
    return tmp_path


def test_dry_run_no_mutation(state):
    f = write_ledger(state, "M-GHOST", "running")
    before = f.read_text()
    out = run_tool(state, "echo 'outra-unit.service loaded active'")
    assert out["ok"] is True and out["dry_run"] is True
    assert any(i["missionId"] == "M-GHOST" for i in out["itens"])
    assert f.read_text() == before


def test_ghost_detected(state):
    write_ledger(state, "M-GHOST", "running")
    out = run_tool(state, "echo 'nada-aqui loaded active'")
    assert [i["missionId"] for i in out["itens"]] == ["M-GHOST"]
    assert out["itens"][0]["status"] == "running"


def test_active_unit_not_candidate(state):
    write_ledger(state, "M-LIVE", "running")
    out = run_tool(state, "echo 'harness-M-LIVE-s42.service loaded active running'")
    assert out["itens"] == []


def test_terminal_not_candidate(state):
    write_ledger(state, "M-DONE", "closed")
    out = run_tool(state, "echo 'nada loaded active'")
    assert out["itens"] == []


def test_systemctl_broken(state):
    f = write_ledger(state, "M-GHOST", "running")
    out = run_tool(state, "exit 1")
    assert out["ok"] is False and out["error"] == "SYSTEMCTL_FAILED"
    assert json.loads(f.read_text())["status"] == "running"


def test_apply_marks_failed_without_resumo(state):
    f = write_ledger(state, "M-GHOST", "running")
    out = run_tool(state, "echo 'nada loaded active'", extra=["--apply"])
    assert out["dry_run"] is False
    led = json.loads(f.read_text())
    assert led["status"] == "failed" and led["motivo"] == "fantasma_sem_unit"
    assert any(r["missionId"] == "M-GHOST" and r["ok"] for r in out["resultados"])


def test_apply_closes_with_resumo(state):
    write_ledger(state, "M-RES", "running")
    resumo = "/tmp/resumo-M-RES.json"
    with open(resumo, "w") as fh:
        json.dump({"resumo": True}, fh)
    try:
        out = run_tool(state, "echo 'nada loaded active'", extra=["--apply"])
    finally:
        os.unlink(resumo)
    assert os.path.exists(str(state / "M-RES.closed"))
    assert any(r["missionId"] == "M-RES" and r["acao"] == "fechar" and r["ok"] for r in out["resultados"])


def test_json_envelope(state):
    write_ledger(state, "M-GHOST", "running")
    out = run_tool(state, "echo 'nada loaded active'")
    assert out["tool"] == "ledger_reap"
    assert out["untrusted"] is True
    assert "notice" in out