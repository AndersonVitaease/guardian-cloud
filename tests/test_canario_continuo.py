"""Testes do canário contínuo — fixtures no layout REAL:
tmp_path/<mission-id>/run-*/harness-trail.jsonl (dois níveis)."""
import json
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "scripts", "canario_continuo.py")
sys.path.insert(0, REPO)

from scripts.canario_continuo import gerar_relatorio, verificar_run  # noqa: E402

PY = "/usr/bin/python3"


def _escrever_trail(run_dir, eventos, nome="harness-trail.jsonl"):
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, nome), "w", encoding="utf-8") as f:
        for ev in eventos:
            f.write(json.dumps(ev) + "\n")


def _run_real(tmp_path, mission="mission-canario", run="run-1", eventos=None, nome="harness-trail.jsonl"):
    rd = os.path.join(str(tmp_path), mission, run)
    _escrever_trail(rd, eventos if eventos is not None else _trail_pass(), nome)
    return rd


def _trail_pass(custo=0.001):
    return [
        {"ts": "t0", "tool": "_inicio", "owner": "mission-canario"},
        {"ts": "t1", "tool": "llm", "custo_usd": custo},
        {"ts": "t2", "tool": "_resumo", "veredito": "PASS", "motivo": "stop_condition"},
    ]


def _trail_fail():
    return [
        {"ts": "t0", "tool": "_inicio", "owner": "mission-canario"},
        {"ts": "t1", "tool": "llm", "custo_usd": 0.002},
        {"ts": "t2", "tool": "_resumo", "veredito": "FAIL", "motivo": "budget"},
    ]


def test_mission_dir_pass(tmp_path):
    _run_real(tmp_path)
    res = verificar_run(os.path.join(str(tmp_path), "mission-canario"))
    assert res["ok"] is True
    assert res["veredito"] == "PASS"
    assert res["owner"] == "mission-canario"


def test_run_dir_pass(tmp_path):
    rd = _run_real(tmp_path)
    res = verificar_run(rd)
    assert res["ok"] is True
    assert res["veredito"] == "PASS"


def test_mission_dir_fail(tmp_path):
    _run_real(tmp_path, run="run-2", eventos=_trail_fail())
    res = verificar_run(os.path.join(str(tmp_path), "mission-canario"))
    assert res["ok"] is False
    assert res["veredito"] == "FAIL"


def test_mission_dir_sem_run(tmp_path):
    os.makedirs(os.path.join(str(tmp_path), "mission-vazia"))
    res = verificar_run(os.path.join(str(tmp_path), "mission-vazia"))
    assert res["ok"] is False
    assert "trail ausente" in res["motivo"]


def test_run_dir_inexistente(tmp_path):
    res = verificar_run(str(tmp_path / "nao-existe"))
    assert res["ok"] is False and res["motivo"]


def test_linha_corrompida_ignorada(tmp_path):
    rd = _run_real(tmp_path, run="run-3", eventos=_trail_pass()[:1])
    with open(os.path.join(rd, "harness-trail.jsonl"), "a", encoding="utf-8") as f:
        f.write("{isto nao e json\n")
        f.write(json.dumps(_trail_pass()[2]) + "\n")
    res = verificar_run(rd)
    assert res["ok"] is False  # corrompida => divergente, sem crash
    assert "corrompida" in res["motivo"]


def test_base_dir_vazia(tmp_path):
    rel = gerar_relatorio(str(tmp_path))
    assert rel == {"total": 0, "pass": 0, "fail": 0, "custo_total": 0.0, "ultimas": []}


def test_relatorio_layout_real(tmp_path):
    _run_real(tmp_path, mission="m-a", run="run-1", eventos=_trail_pass(0.001))
    _run_real(tmp_path, mission="m-b", run="run-1", eventos=_trail_pass(0.002))
    _run_real(tmp_path, mission="m-c", run="run-1", eventos=_trail_fail())
    rel = gerar_relatorio(str(tmp_path))
    assert rel["total"] == 3
    assert rel["pass"] == 2
    assert rel["fail"] == 1
    assert abs(rel["custo_total"] - 0.005) < 1e-9


def test_relatorio_multiplas_runs_por_mission(tmp_path):
    _run_real(tmp_path, run="run-1", eventos=_trail_pass(0.001))
    _run_real(tmp_path, run="run-2", eventos=_trail_pass(0.003))
    rel = gerar_relatorio(str(tmp_path))
    assert rel["total"] == 2
    assert rel["pass"] == 2
    assert abs(rel["custo_total"] - 0.004) < 1e-9


def test_relatorio_layout_legado_run_direta(tmp_path):
    _escrever_trail(os.path.join(str(tmp_path), "run-legacy"), _trail_pass(0.01))
    rel = gerar_relatorio(str(tmp_path))
    assert rel["total"] == 1 and rel["pass"] == 1


def test_ultimas_cap_5(tmp_path):
    for i in range(8):
        _run_real(tmp_path, mission="m-%02d" % i, run="run-1")
    rel = gerar_relatorio(str(tmp_path))
    assert rel["total"] == 8
    assert len(rel["ultimas"]) == 5


def test_cli_verificar_exit_codes(tmp_path):
    rd_ok = _run_real(tmp_path, run="run-ok")
    rd_bad = _run_real(tmp_path, run="run-bad", eventos=_trail_fail())
    mission = os.path.join(str(tmp_path), "mission-canario")
    # determinístico: --verificar mission-dir escolhe a run mais recente por mtime;
    # sem o touch, run-ok/run-bad nascem a microssegundos de distância (flake de timestamp)
    os.utime(rd_ok, None)
    assert os.path.getmtime(rd_ok) >= os.path.getmtime(rd_bad)
    p_ok = subprocess.run([PY, SCRIPT, "--verificar", rd_ok], capture_output=True)
    p_bad = subprocess.run([PY, SCRIPT, "--verificar", rd_bad], capture_output=True)
    p_miss = subprocess.run([PY, SCRIPT, "--verificar", str(tmp_path / "x")], capture_output=True)
    p_m = subprocess.run([PY, SCRIPT, "--verificar", mission], capture_output=True)
    assert p_ok.returncode == 0
    assert p_bad.returncode == 1
    assert p_miss.returncode == 1
    assert p_m.returncode == 0


def test_cli_usage_error(tmp_path):
    p = subprocess.run([PY, SCRIPT], capture_output=True)
    assert p.returncode == 2


def test_cli_relatorio_json(tmp_path):
    _run_real(tmp_path, run="run-1", eventos=_trail_pass(0.0005))
    p = subprocess.run([PY, SCRIPT, "--relatorio", str(tmp_path), "--json"],
                       capture_output=True, text=True)
    assert p.returncode == 0
    rel = json.loads(p.stdout)
    assert rel["total"] == 1 and rel["pass"] == 1
    assert abs(rel["custo_total"] - 0.0005) < 1e-9


def test_cli_relatorio_base_vazia_exit_1(tmp_path):
    p = subprocess.run([PY, SCRIPT, "--relatorio", str(tmp_path), "--json"],
                       capture_output=True, text=True)
    assert p.returncode == 1
    assert json.loads(p.stdout)["total"] == 0
