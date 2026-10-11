"""Testes de tools-bash/ledger_reap.sh (RD-ROUTER-BRIEFING-01)."""
import json
import os
import stat
import subprocess
import textwrap

import pytest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "tools-bash", "ledger_reap.sh")


def _run(env, *args):
    e = dict(os.environ)
    e.update(env)
    return subprocess.run(
        ["bash", SCRIPT, *args], env=e, capture_output=True, text=True
    )


def _mk_ledger(d, mid, status="running", custo=0.42):
    p = d / ("%s.json" % mid)
    p.write_text(json.dumps({
        "missionId": mid, "status": status, "custo_usd": custo,
        "veredito": None, "verdict": None,
        "ts_inicio": "2025-10-09T17:00:00Z",
    }), encoding="utf-8")
    return p


def _fake_units(units):
    return "#!/bin/sh\ncat <<'EOF'\n%s\nEOF\n" % "\n".join(
        "%s active running" % u for u in units)


@pytest.fixture
def env(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    units = tmp_path / "units.sh"
    units.write_text(_fake_units([]), encoding="utf-8")
    units.chmod(units.stat().st_mode | stat.S_IEXEC)
    return {
        "MISSION_STATE_DIR": str(state),
        "LEDGER_REAP_UNITS_CMD": str(units),
        "LEDGER_REAP_LEDGER_SCRIPT": str(tmp_path / "ledger_fake.py"),
        "PATH": os.environ["PATH"],
    }, state, units


def test_dry_run_nao_muta(env):
    e, state, _ = env
    p = _mk_ledger(state, "M-1")
    antes = p.read_text(encoding="utf-8")
    r = _run(e)
    assert r.returncode == 0
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["tool"] == "ledger_reap"
    assert out["dry_run"] is True
    assert out["untrusted"] is True
    assert out["notice"]
    assert [i["missionId"] for i in out["itens"]] == ["M-1"]
    assert p.read_text(encoding="utf-8") == antes


def test_fantasma_detectado_unit_inativa(env):
    e, state, _ = env
    _mk_ledger(state, "M-ghost", status="running")
    _mk_ledger(state, "M-done", status="closed")
    r = _run(e)
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert [i["missionId"] for i in out["itens"]] == ["M-ghost"]
    assert out["itens"][0]["status"] == "running"
    assert "custo_usd" in out["itens"][0]
    assert "idade" in out["itens"][0]


def test_unit_ativa_nao_e_candidato(env):
    e, state, units = env
    units.write_text(_fake_units(["harness-M-live-s1"]), encoding="utf-8")
    _mk_ledger(state, "M-live", status="running")
    r = _run(e)
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["itens"] == []


def test_systemctl_quebrado(env):
    e, state, units = env
    units.write_text("#!/bin/sh\nexit 3\n", encoding="utf-8")
    units.chmod(units.stat().st_mode | stat.S_IEXEC)
    _mk_ledger(state, "M-1")
    r = _run(e, "--apply")
    assert r.returncode == 0
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["ok"] is False
    assert out["error"] == "SYSTEMCTL_FAILED"
    assert json.loads((state / "M-1.json").read_text(encoding="utf-8"))["status"] == "running"


def test_apply_fecha_via_script_e_motivo(env, tmp_path):
    e, state, _ = env
    _mk_ledger(state, "M-a", status="running")
    _mk_ledger(state, "M-b", status="running")
    (state / "resumo-M-a.json").write_text("{}", encoding="utf-8")
    calls = tmp_path / "calls.log"
    ledger_fake = tmp_path / "ledger_fake.py"
    ledger_fake.write_text(textwrap.dedent("""
        import json, sys
        with open(%r, "a") as f:
            f.write(json.dumps(sys.argv[1:]) + "\\n")
    """ % str(calls)), encoding="utf-8")
    r = _run(e, "--apply")
    assert r.returncode == 0
    out = json.loads(r.stdout.strip().splitlines()[-1])
    ids = {x["missionId"] for x in out["resultados"]}
    assert ids == {"M-a", "M-b"}
    chamadas = [json.loads(l) for l in calls.read_text().splitlines()]
    assert any(c[:2] == ["fechar", "M-a"] for c in chamadas)
    lb = json.loads((state / "M-b.json").read_text(encoding="utf-8"))
    assert lb["status"] == "failed"
    assert lb["motivo"] == "fantasma_sem_unit"


def test_saida_uma_linha_json(env):
    e, state, _ = env
    _mk_ledger(state, "M-1")
    r = _run(e)
    linhas = [l for l in r.stdout.strip().splitlines() if l.strip()]
    assert len(linhas) == 1
    json.loads(linhas[0])