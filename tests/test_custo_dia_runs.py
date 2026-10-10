"""Testes da tool custo_dia.sh (fonte: runs_historico.sh)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools-bash" / "custo_dia.sh"


def make_fake(payload, exit_code=0):
    """Comando fake que imprime payload JSON (1 linha)."""
    if exit_code != 0:
        return "exit 1"
    return f"printf '%s\\n' '{json.dumps(payload, ensure_ascii=False)}'"


def run_tool(fake_cmd):
    env = dict(os.environ)
    env["CUSTO_RUNS_HISTORICO_CMD"] = fake_cmd
    p = subprocess.run(
        ["bash", str(TOOL)], env=env, capture_output=True, text=True, timeout=30
    )
    return p


def parse_out(p):
    lines = [l for l in p.stdout.strip().splitlines() if l.strip()]
    assert len(lines) == 1, f"esperado 1 linha, veio {len(lines)}: {p.stdout!r}"
    return json.loads(lines[0])


FIXTURE_RUNS = {
    "ok": True,
    "tool": "runs_historico",
    "count": 5,
    "runs": [
        # 2026-02-10 22:00 UTC = 2026-02-10 19:00 BRT (mesmo dia)
        {"missionId": "M-A", "verdict": "PASS", "cost_usd": 1.5, "turnos": 10,
         "finished_at": "2026-02-10T22:00:00Z"},
        # 2026-02-11 01:00 UTC = 2026-02-10 22:00 BRT (dia anterior em BRT!)
        {"missionId": "M-B", "verdict": "FAIL", "cost_usd": 2.0, "turnos": 5,
         "finished_at": "2026-02-11T01:00:00Z"},
        {"missionId": "M-C", "verdict": "WEIRD", "cost_usd": 0.25, "turnos": 3,
         "finished_at": "2026-02-10T15:00:00Z"},
        # cost_usd ausente não quebra
        {"missionId": "M-D", "verdict": "PASS", "turnos": 2,
         "finished_at": "2026-02-10T18:00:00Z"},
        # outro dia BRT (2026-02-09 20:00 UTC = 17:00 BRT do dia 09)
        {"missionId": "M-E", "verdict": "PASS", "cost_usd": 9.0, "turnos": 7,
         "finished_at": "2026-02-09T20:00:00Z"},
    ],
}


def test_agregacao_dia_brt():
    p = run_tool(make_fake(FIXTURE_RUNS))
    assert p.returncode == 0
    out = parse_out(p)
    assert out["ok"] is True
    assert out["tool"] == "custo_dia"
    # dia corrente do fixture: 2026-02-10 em BRT
    assert out["dia"] == "2026-02-10"
    assert out["runs"] == 4
    assert abs(out["custo_usd_total"] - (1.5 + 2.0 + 0.25)) < 1e-9
    assert out["turnos_total"] == 10 + 5 + 3 + 2
    assert out["pass"] == 2
    assert out["fail"] == 1
    assert out["outros"] == 1
    ids = [m["missionId"] for m in out["por_missao"]]
    assert set(ids) == {"M-A", "M-B", "M-C", "M-D"}
    assert len(out["por_missao"]) <= 20


def test_por_missao_mais_caros_primeiro():
    runs = {
        "ok": True, "tool": "runs_historico", "count": 3,
        "runs": [
            {"missionId": "BARATO", "verdict": "PASS", "cost_usd": 0.1, "turnos": 1,
             "finished_at": "2026-02-10T12:00:00Z"},
            {"missionId": "CARO", "verdict": "PASS", "cost_usd": 5.0, "turnos": 1,
             "finished_at": "2026-02-10T13:00:00Z"},
            {"missionId": "MEIO", "verdict": "PASS", "cost_usd": 1.0, "turnos": 1,
             "finished_at": "2026-02-10T14:00:00Z"},
        ],
    }
    out = parse_out(run_tool(make_fake(runs)))
    ids = [m["missionId"] for m in out["por_missao"]]
    assert ids == ["CARO", "MEIO", "BARATO"]


def test_cost_usd_ausente_nao_quebra():
    runs = {
        "ok": True, "tool": "runs_historico", "count": 1,
        "runs": [{"missionId": "M-X", "verdict": "PASS", "turnos": 4,
                  "finished_at": "2026-02-10T12:00:00Z"}],
    }
    out = parse_out(run_tool(make_fake(runs)))
    assert out["custo_usd_total"] == 0
    assert out["turnos_total"] == 4


def test_fonte_indisponivel():
    p = run_tool(make_fake({"ok": False, "tool": "runs_historico", "error": "X"}))
    assert p.returncode == 0
    out = parse_out(p)
    assert out["ok"] is False
    assert out["tool"] == "custo_dia"
    assert out["error"] == "FONTE_INDISPONIVEL"
    assert "detalhe" in out


def test_saida_untrusted_notice_e_exit0():
    p = run_tool(make_fake(FIXTURE_RUNS))
    assert p.returncode == 0
    assert "untrusted:true" in p.stdout
    assert "notice" in p.stdout


def test_fuso_utc_vira_dia_brt():
    # 2026-02-11 02:30 UTC = 2026-02-10 23:30 BRT -> dia 10
    runs = {
        "ok": True, "tool": "runs_historico", "count": 1,
        "runs": [{"missionId": "M-F", "verdict": "FAIL", "cost_usd": 3.0, "turnos": 9,
                  "finished_at": "2026-02-11T02:30:00Z"}],
    }
    out = parse_out(run_tool(make_fake(runs)))
    assert out["dia"] == "2026-02-10"
    assert out["runs"] == 1
    assert out["fail"] == 1


def test_sem_runs_no_dia():
    runs = {
        "ok": True, "tool": "runs_historico", "count": 1,
        "runs": [{"missionId": "M-Z", "verdict": "PASS", "cost_usd": 1.0, "turnos": 1,
                  "finished_at": "2026-02-09T20:00:00Z"}],
    }
    out = parse_out(run_tool(make_fake(runs)))
    assert out["runs"] == 0
    assert out["custo_usd_total"] == 0