# RD-ORQD-SENTINEL-01 — sentinel/liveness do orqd-live.service e do orchestrator-consumer.
# Fakes de systemctl: caminho do binário systemctl vem de env; NUNCA default vazio.
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import orqd_sentinel  # noqa: E402


class FakeCtl:
    """Fake de `systemctl is-active` — mapa serviço->estado."""

    def __init__(self, states=None):
        self.states = states or {}

    def __call__(self, service, **kw):
        st = self.states.get(service, "active")
        r = subprocess.CompletedProcess([], 0 if st == "active" else 3)
        r.stdout = st + "\n"
        r.stderr = ""
        return r


def run_sentinel(tmp_path, ctl, state=None, queue_lines=0):
    state_path = tmp_path / "state.json"
    queue_path = tmp_path / "queue.jsonl"
    if state is None:
        state = {"status": "alive", "lastPromotion": "2026-10-10T12:00:00Z"}
    state_path.write_text(json.dumps(state))
    queue_path.write_text("".join('{"id":"e%d"}\n' % i for i in range(queue_lines)))
    return orqd_sentinel.coletar(
        state_path=str(state_path), queue_path=str(queue_path),
        queue_lines=queue_lines, systemctl=ctl, now=1800000000.0,
        stale_seconds=1800,
    )


def test_tudo_ok_verde(tmp_path):
    out = run_sentinel(tmp_path, FakeCtl())
    assert out["semaforo"] == "verde", out


def test_orqd_live_inativo_vermelho(tmp_path):
    out = run_sentinel(tmp_path, FakeCtl({"orqd-live.service": "inactive"}))
    assert out["semaforo"] == "vermelho"
    assert out["culpado"] == "orqd-live.service"


def test_consumer_inativo_vermelho(tmp_path):
    out = run_sentinel(tmp_path, FakeCtl({"orchestrator-consumer.service": "inactive"}))
    assert out["semaforo"] == "vermelho"
    assert out["culpado"] == "orchestrator-consumer.service"


def test_last_promotion_velho_com_fila_amarelo(tmp_path):
    st = {"status": "alive", "lastPromotion": "2026-10-09T00:00:00Z"}
    out = run_sentinel(tmp_path, FakeCtl(), state=st, queue_lines=3)
    assert out["semaforo"] == "amarelo"
    assert out["culpado"] == "orqd-live.service"


def test_last_promotion_velho_fila_vazia_verde(tmp_path):
    st = {"status": "alive", "lastPromotion": "2026-10-09T00:00:00Z"}
    out = run_sentinel(tmp_path, FakeCtl(), state=st, queue_lines=0)
    assert out["semaforo"] == "verde"


def test_env_default_tools_nunca_vazio():
    # default do caminho de tools NUNCA vazio: /opt/mission-events/tools-bash
    env = {"PATH": "/usr/bin"}
    v = orqd_sentinel.env_ou_default(env, "ORQD_SENTINEL_TOOLS_DIR", "")
    assert v == "/opt/mission-events/tools-bash"
    assert orqd_sentinel.env_ou_default({}, "ORQD_SENTINEL_TOOLS_DIR", "") != ""
