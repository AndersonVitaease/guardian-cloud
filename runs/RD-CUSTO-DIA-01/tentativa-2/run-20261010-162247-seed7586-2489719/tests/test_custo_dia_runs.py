import json
import os
import subprocess
import textwrap

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "tools-bash", "custo_dia.sh")


def make_fake_cmd(payload, exit_code=0):
    """Comando fake que substitui runs_historico.sh via CUSTO_RUNS_HISTORICO_CMD."""
    script = textwrap.dedent(
        f"""
        import json, sys
        print(json.dumps({json.dumps(payload)}))
        sys.exit({exit_code})
        """
    )
    return ["python3", "-c", script]


def run_custo_dia(fake_payload, exit_code=0):
    env = dict(os.environ)
    env["CUSTO_RUNS_HISTORICO_CMD"] = json.dumps(make_fake_cmd(fake_payload, exit_code))
    p = subprocess.run(
        ["bash", SCRIPT], env=env, capture_output=True, text=True, timeout=30
    )
    return p


def parse_out(p):
    lines = [l for l in p.stdout.strip().splitlines() if l.strip()]
    assert len(lines) == 1
    return json.loads(lines[0])


FIXTURE_RUNS = {
    "ok": True,
    "tool": "runs_historico",
    "count": 5,
    "runs": [
        {
            "missionId": "M-1",
            "verdict": "PASS",
            "cost_usd": 0.5,
            "turnos": 10,
            "finished_at": "2026-02-10T01:00:00Z",  # 2026-02-09 22h BRT
        },
        {
            "missionId": "M-2",
            "verdict": "FAIL",
            "cost_usd": 0.25,
            "turnos": 5,
            "finished_at": "2026-02-10T02:00:00Z",  # 2026-02-09 23h BRT
        },
        {
            "missionId": "M-3",
            "verdict": "PASS",
            "cost_usd": 0.1,
            "turnos": 3,
            "finished_at": "2026-02-10T03:00:00Z",  # 2026-02-10 00h BRT (dia corrente)
        },
        {
            "missionId": "M-4",
            "verdict": None,  # sem veredito -> outros
            "cost_usd": None,  # sem custo -> 0
            "turnos": 2,
            "finished_at": "2026-02-10T04:00:00Z",
        },
        {
            "missionId": "M-5",
            "verdict": "PASS",
            "cost_usd": 0.9,
            "turnos": 7,
            "finished_at": "2026-02-11T00:30:00Z",  # 2026-02-10 21h BRT (dia corrente)
        },
    ],
}


def test_agrega_dia_brt(tmp_path):
    p = run_custo_dia(FIXTURE_RUNS)
    assert p.returncode == 0
    out = parse_out(p)
    assert out["ok"] is True
    assert out["tool"] == "custo_dia"
    assert out["dia"] == "2026-02-10"
    # dia corrente BRT: M-3, M-4, M-5
    assert out["runs"] == 3
    assert abs(out["custo_usd_total"] - 1.0) < 1e-9
    assert out["turnos_total"] == 12
    assert out["pass"] == 2
    assert out["fail"] == 0
    assert out["outros"] == 1
    ids = [m["missionId"] for m in out["por_missao"]]
    assert set(ids) == {"M-3", "M-4", "M-5"}


def test_por_missao_ordenado_por_custo_desc():
    p = run_custo_dia(FIXTURE_RUNS)
    out = parse_out(p)
    custos = [m["cost_usd"] for m in out["por_missao"]]
    assert custos == sorted(custos, reverse=True)


def test_cost_usd_ausente_nao_quebra():
    payload = {
        "ok": True,
        "tool": "runs_historico",
        "count": 1,
        "runs": [
            {
                "missionId": "M-X",
                "verdict": "PASS",
                "turnos": 4,
                "finished_at": "2026-02-10T12:00:00Z",
            }
        ],
    }
    p = run_custo_dia(payload)
    out = parse_out(p)
    assert out["ok"] is True
    assert out["custo_usd_total"] == 0
    assert out["pass"] == 1


def test_fonte_indisponivel():
    p = run_custo_dia({"ok": False, "error": "X"})
    out = parse_out(p)
    assert out["ok"] is False
    assert out["tool"] == "custo_dia"
    assert out["error"] == "FONTE_INDISPONIVEL"
    assert p.returncode == 0


def test_saida_uma_linha_com_untrusted_notice():
    p = run_custo_dia(FIXTURE_RUNS)
    out = parse_out(p)
    assert out.get("untrusted") is True
    assert out.get("notice")


def test_fuso_utc_vira_dia_brt():
    # 2026-02-10T02:00Z = 2026-02-09 23h BRT -> dia anterior ao corrente
    payload = {
        "ok": True,
        "tool": "runs_historico",
        "count": 1,
        "runs": [
            {
                "missionId": "M-Z",
                "verdict": "FAIL",
                "cost_usd": 0.3,
                "turnos": 6,
                "finished_at": "2026-02-10T02:00:00Z",
            }
        ],
    }
    p = run_custo_dia(payload)
    out = parse_out(p)
    assert out["dia"] == "2026-02-10"
    assert out["runs"] == 0
    assert out["custo_usd_total"] == 0