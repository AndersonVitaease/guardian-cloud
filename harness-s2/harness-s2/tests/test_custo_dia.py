import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from custo_dia import custo_dia  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _escrever_trail(base, run_rel, resumo):
    run_dir = os.path.join(base, run_rel)
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "harness-trail.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"tool": "x"}) + "\n")
        resumo["tool"] = "_resumo"
        f.write(json.dumps(resumo) + "\n")


def test_dois_dias_duas_linhas(tmp_path):
    _escrever_trail(str(tmp_path), "m/run-1", {
        "ts": "2026-10-07T12:00:00Z", "veredito": "PASS",
        "custo": {"usd": 0.01}})
    _escrever_trail(str(tmp_path), "m/run-2", {
        "ts": "2026-10-06T12:00:00Z", "veredito": "FAIL",
        "custo": {"usd": 0.02}})
    linhas = custo_dia(str(tmp_path))
    assert len(linhas) == 2
    assert linhas[0].startswith("2026-10-07")
    assert linhas[1].startswith("2026-10-06")
    assert "PASS 1 FAIL 0" in linhas[0]
    assert "PASS 0 FAIL 1" in linhas[1]


def test_run_sem_resumo_ignorada(tmp_path):
    _escrever_trail(str(tmp_path), "m/run-1", {
        "ts": "2026-10-07T12:00:00Z", "veredito": "PASS",
        "custo": {"usd": 0.01}})
    run_dir = os.path.join(tmp_path, "m", "run-2")
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "harness-trail.jsonl"), "w") as f:
        f.write(json.dumps({"tool": "Bash"}) + "\n")
    linhas = custo_dia(str(tmp_path))
    assert len(linhas) == 1
    assert "1 runs" in linhas[0]


def test_dir_vazio_exit_1(tmp_path):
    r = subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "custo_dia.py"),
         "--base-dir", str(tmp_path)],
        capture_output=True, text=True)
    assert r.returncode == 1
    assert "SEM RUNS" in r.stdout


def test_moeda_virgula_ptbr(tmp_path):
    _escrever_trail(str(tmp_path), "m/run-1", {
        "ts": "2026-10-07T12:00:00Z", "veredito": "PASS",
        "custo": {"usd": 0.05234}})
    linhas = custo_dia(str(tmp_path))
    assert "$ 0,05234" in linhas[0]


def test_fuso_brt(tmp_path):
    # 01:00 UTC = 22:00 do dia anterior em Brasília
    _escrever_trail(str(tmp_path), "m/run-1", {
        "ts": "2026-10-08T01:00:00Z", "veredito": "PASS",
        "custo": {"usd": 0.01}})
    linhas = custo_dia(str(tmp_path))
    assert linhas[0].startswith("2026-10-07")