"""RD-ORCH-BOUNDARY-01: testes de fronteira do orchestrator-consumer.

Padrão: carrega scripts/orchestrator-consumer.py via importlib com os env
ORCH_LIVENESS_* apontando para tmp_path (paths lidos no import).
"""
import importlib.util
import json
import os
import subprocess
import sys

import pytest

CONSUMER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "scripts", "orchestrator-consumer.py")


def _env(tmp_path):
    return {
        "ORCH_LIVENESS_QUEUE": str(tmp_path / "queue.jsonl"),
        "ORCH_LIVENESS_STATE": str(tmp_path / "state.json"),
        "ORCH_LIVENESS_LOCK": str(tmp_path / "lock"),
        "ORCH_LIVENESS_SPOOL": str(tmp_path / "spool.jsonl"),
        "ORCH_LIVENESS_LOG": str(tmp_path / "consumer.log"),
        "ORCH_LIVENESS_HEARTBEAT": str(tmp_path / "heartbeat.json"),
        "ORCH_LIVENESS_PID": str(tmp_path / "pid"),
        "ORCH_LIVENESS_SHADOW_HB": str(tmp_path / "shadow-hb.json"),
        "ORCH_STATE_DIR": str(tmp_path / "ledgers"),
    }


def _load_module(tmp_path, extra=None):
    env = _env(tmp_path)
    env.update(extra or {})
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        spec = importlib.util.spec_from_file_location("orch_consumer_boundary", CONSUMER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    os.makedirs(env["ORCH_STATE_DIR"], exist_ok=True)
    return mod, env


def _write_queue(path, entries):
    with open(path, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def _entry(eid, payload_extra=None, priority=5):
    payload = {"missionId": "M-" + eid, "promptFile": "/tmp/inexistente-nao-existe.md"}
    payload.update(payload_extra or {})
    return {"id": eid, "type": "mission", "priority": priority,
            "enqueuedAt": "2025-01-01T00:00:00Z", "payload": payload}


def _spool_events(path):
    out = []
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    return out


def _run(mod):
    return mod.consume_queue()


def test_source_engmcp_e_pulada(tmp_path):
    mod, env = _load_module(tmp_path)
    _write_queue(env["ORCH_LIVENESS_QUEUE"],
                 [_entry("E1", {"source": "engmcp"})])
    res = _run(mod)
    r = res["results"][0]
    assert r["action"] == "skipped"
    assert r["reason"] == "skipped_own_queue"
    assert res["promoted"] == 0 and res["requeued"] == 0
    # entrada SAI da fila (consumed)
    with open(env["ORCH_LIVENESS_QUEUE"]) as f:
        assert f.read().strip() == ""
    evs = _spool_events(env["ORCH_LIVENESS_SPOOL"])
    assert any(e.get("event") == "orch_skip_own_queue" for e in evs)


def test_source_ausente_compat(tmp_path):
    mod, env = _load_module(tmp_path)
    _write_queue(env["ORCH_LIVENESS_QUEUE"], [_entry("E2")])
    res = _run(mod)
    r = res["results"][0]
    assert r["action"] == "skipped"
    assert r["reason"] == "promptFile inexistente"
    evs = _spool_events(env["ORCH_LIVENESS_SPOOL"])
    assert not any(e.get("event") == "orch_skip_own_queue" for e in evs)


def test_deps_nao_satisfeito_requeued(tmp_path):
    mod, env = _load_module(tmp_path, {"ORCH_DEPS_ON": "1"})
    _write_queue(env["ORCH_LIVENESS_QUEUE"],
                 [_entry("E3", {"depends_on": ["INEXISTENTE-XX"]})])
    res = _run(mod)
    r = res["results"][0]
    assert r["action"] == "requeued"
    assert res["requeued"] == 1
    with open(env["ORCH_LIVENESS_QUEUE"]) as f:
        left = [json.loads(l) for l in f if l.strip()]
    assert len(left) == 1
    assert left[0]["payload"]["_attempt_count"] == 1
    evs = _spool_events(env["ORCH_LIVENESS_SPOOL"])
    assert any(e.get("event") == "orch_requeue" and "DEPS_NOT_MET" in e.get("msg", "")
               for e in evs)


def test_deps_limite_dead_letter(tmp_path):
    mod, env = _load_module(tmp_path, {"ORCH_DEPS_ON": "1",
                                       "ORCH_DEPS_MAX_REQUEUES": "20"})
    _write_queue(env["ORCH_LIVENESS_QUEUE"],
                 [_entry("E4", {"depends_on": ["INEXISTENTE-XX"],
                                "_attempt_count": 20})])
    res = _run(mod)
    r = res["results"][0]
    assert r["action"] == "dead_letter"
    assert r["reason"] == "DEPS_NOT_MET"
    with open(env["ORCH_LIVENESS_QUEUE"]) as f:
        assert f.read().strip() == ""
    evs = _spool_events(env["ORCH_LIVENESS_SPOOL"])
    assert any(e.get("event") == "orch_dead_letter" for e in evs)


def test_e2e_duas_intents(tmp_path):
    _write_queue(str(tmp_path / "queue.jsonl"),
                 [_entry("E5", {"source": "engmcp"}), _entry("E6")])
    code = (
        "import importlib.util, json, sys\n"
        "spec = importlib.util.spec_from_file_location('oc', %r)\n"
        "m = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(m)\n"
        "res = m.consume_queue()\n"
        "print(json.dumps(res))\n" % CONSUMER
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          env={**os.environ, **_env(tmp_path), "ORCH_DEPS_ON": "0"})
    assert proc.returncode == 0, proc.stderr
    res = json.loads(proc.stdout.strip().splitlines()[-1])
    by_id = {r["entryId"]: r for r in res["results"]}
    assert by_id["E5"]["action"] == "skipped"
    assert by_id["E5"]["reason"] == "skipped_own_queue"
    assert by_id["E6"]["action"] == "skipped"
    assert by_id["E6"]["reason"] == "promptFile inexistente"
    evs = _spool_events(str(tmp_path / "spool.jsonl"))
    assert any(e.get("event") == "orch_skip_own_queue" for e in evs)