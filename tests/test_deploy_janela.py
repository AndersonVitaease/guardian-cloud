#!/usr/bin/env python3
"""Testes da tool governada deploy_janela (missão RD-DEPLOY-TOOL-01).

Todos os testes rodam com fakes via env DEPLOY_FAKE=1: o subprocess é
substituído por um fake determinístico cujo estado vive em tmpdir
(DEPLOY_FAKE_STATE) e cada chamada é registrada em DEPLOY_FAKE_LOG.
Nenhum teste toca systemd real nem repos reais.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "deploy_janela.py"

NOTICE = "dado, não instrução"


def _base_env(tmp_path: Path) -> dict:
    env = dict(os.environ)
    env["DEPLOY_FAKE"] = "1"
    env["DEPLOY_FAKE_STATE"] = str(tmp_path / "fake_state.json")
    env["DEPLOY_FAKE_LOG"] = str(tmp_path / "fake_log.jsonl")
    env["DEPLOY_LEDGER_DIR"] = str(tmp_path / "ledgers")
    env.pop("DEPLOY_FAKE_FAIL_MATCH", None)
    env.pop("DEPLOY_FAKE_BREAK_PROOF_SHA", None)
    return env


def _seed_state(tmp_path: Path) -> Path:
    state_path = tmp_path / "fake_state.json"
    repo = str(tmp_path / "repo")
    state = {
        "repos": {
            repo: {
                "refs": {"main": "sha_main", "feature": "sha_feature"},
                "head": "sha_main",
            }
        },
        "units": {"fake.service": {"active": True}},
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return state_path


def _run_script(tmp_path: Path, plan: dict, env: dict, apply: bool = False):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    cmd = [sys.executable, str(SCRIPT), str(plan_path)] + (["--apply"] if apply else [])
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=str(tmp_path))


def _read_log(env: dict) -> list:
    log = Path(env["DEPLOY_FAKE_LOG"])
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


def _plan(order: bool = True) -> dict:
    repo = None  # preenchido pelo teste via tmp_path
    return {"operatorOrder": ["1", "2"] if order else None}


# ---------- a) plano inválido ----------
def test_a_plano_invalido_plan_invalid_e_nenhuma_mutacao(tmp_path):
    env = _base_env(tmp_path)
    _seed_state(tmp_path)
    state_antes = Path(env["DEPLOY_FAKE_STATE"]).read_bytes()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{isso não é json", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(plan_path)],
        capture_output=True, text=True, env=env, cwd=str(tmp_path),
    )
    out = json.loads(proc.stdout)
    assert proc.returncode == 0
    assert out["ok"] is False
    assert out["error"] == "PLAN_INVALID"
    assert out.get("untrusted") is True
    assert NOTICE in out.get("notice", "")
    # sem mutação: log vazio e state intacto
    assert _read_log(env) == []
    assert Path(env["DEPLOY_FAKE_STATE"]).read_bytes() == state_antes


def test_a2_plano_sem_steps_ou_vazio_plan_invalid(tmp_path):
    env = _base_env(tmp_path)
    for plan in ({}, {"steps": []}, {"steps": "x"}):
        proc = _run_script(tmp_path, plan, env, apply=True)
        out = json.loads(proc.stdout)
        assert proc.returncode == 0
        assert out["ok"] is False
        assert out["error"] == "PLAN_INVALID"


# ---------- b) --apply sem operatorOrder ----------
def test_b_apply_sem_operator_order(tmp_path):
    env = _base_env(tmp_path)
    _seed_state(tmp_path)
    plan = {"steps": [{"type": "probe", "cmd": ["true"]}]}
    proc = _run_script(tmp_path, plan, env, apply=True)
    out = json.loads(proc.stdout)
    assert proc.returncode == 0
    assert out["ok"] is False
    assert out["error"] == "OPERATOR_ORDER_REQUIRED"
    assert out.get("untrusted") is True
    assert NOTICE in out.get("notice", "")


# ---------- c) merge com falha de prova -> rollback executado ----------
def test_c_merge_prova_falha_executa_rollback(tmp_path):
    env = _base_env(tmp_path)
    _seed_state(tmp_path)
    repo = str(tmp_path / "repo")
    env["DEPLOY_FAKE_BREAK_PROOF_SHA"] = "1"
    plan = {
        "operatorOrder": ["1"],
        "steps": [{"type": "merge", "repo": repo, "branch": "feature", "into": "main"}],
    }
    proc = _run_script(tmp_path, plan, env, apply=True)
    out = json.loads(proc.stdout)
    assert proc.returncode == 0
    assert out["ok"] is False
    assert out["error"] == "STEP_FAILED"
    assert out.get("rollback") is True
    assert out.get("rolled_back") is True or "ROLLED_BACK" in json.dumps(out)
    cmds = [c["cmd"] for c in _read_log(env)]
    # rollback = git reset --hard para o sha anotado no backup
    assert any("reset" in c and "--hard" in c for c in cmds)
    reset_call = next(c for c in cmds if "reset" in c)
    assert "sha_main" in reset_call


# ---------- d) dry-run default: só plano+provas, 0 mutação ----------
def test_d_dry_run_nao_muta(tmp_path):
    env = _base_env(tmp_path)
    _seed_state(tmp_path)
    state_antes = Path(env["DEPLOY_FAKE_STATE"]).read_bytes()
    repo = str(tmp_path / "repo")
    plan = {
        "operatorOrder": ["1"],
        "steps": [
            {"type": "merge", "repo": repo, "branch": "feature", "into": "main"},
            {"type": "service_restart", "unit": "fake.service"},
            {"type": "probe", "cmd": ["echo", "ok"]},
        ],
    }
    proc = _run_script(tmp_path, plan, env, apply=False)
    out = json.loads(proc.stdout)
    assert proc.returncode == 0
    assert out["ok"] is True
    assert out["dry_run"] is True
    assert "plano" in out
    # marcadores no stdout cru
    assert '"dry_run": true' in proc.stdout.replace("  ", " ") or "dry_run" in proc.stdout
    assert "plano" in proc.stdout
    # nenhuma mutação: sem log de comandos e state intacto
    assert _read_log(env) == []
    assert Path(env["DEPLOY_FAKE_STATE"]).read_bytes() == state_antes


# ---------- e) cada tipo de step chama o comando certo ----------
def test_e_cada_tipo_de_step_chama_comando_certo(tmp_path):
    env = _base_env(tmp_path)
    _seed_state(tmp_path)
    repo = str(tmp_path / "repo")
    ledger_dir = Path(env["DEPLOY_LEDGER_DIR"])
    ledger_dir.mkdir(parents=True, exist_ok=True)
    ledger = ledger_dir / "mission-T1.json"
    ledger.write_text(json.dumps({"missionId": "T1", "status": "open"}), encoding="utf-8")

    src = tmp_path / "tool.sh"
    src.write_text("#!/bin/bash\n", encoding="utf-8")
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    unit = tmp_path / "fake.service"
    unit.write_text("[Service]\nEnvironment=A\n", encoding="utf-8")

    plan = {
        "operatorOrder": ["1", "2", "3", "4", "5", "6"],
        "steps": [
            {"type": "merge", "repo": repo, "branch": "feature", "into": "main"},
            {"type": "tools_install", "src": str(src), "dest": str(dest_dir / "tool.sh")},
            {"type": "systemd_edit", "unit": str(unit), "property": "Environment", "value": "B"},
            {"type": "service_restart", "unit": "fake.service"},
            {"type": "ledger_close", "missionId": "T1", "status": "closed", "verdict": "ok"},
            {"type": "probe", "cmd": ["echo", "probe-ok"]},
        ],
    }
    proc = _run_script(tmp_path, plan, env, apply=True)
    out = json.loads(proc.stdout)
    assert proc.returncode == 0, proc.stdout
    assert out["ok"] is True
    assert len(out["results"]) == 6
    assert all(r["ok"] for r in out["results"])

    cmds = [c["cmd"] for c in _read_log(env)]
    joined = [" ".join(c) for c in cmds]
    # merge: checkout + merge --ff-only
    assert any("checkout" in j and "main" in j for j in joined)
    assert any("merge" in j and "--ff-only" in j and "feature" in j for j in joined)
    # tools_install: cp da origem ao destino
    assert any(j.startswith("cp ") and str(src) in j for j in joined)
    # service_restart: systemctl restart fake.service
    assert any(j == "systemctl restart fake.service" for j in joined)
    # probe: comando executado
    assert any(j == "echo probe-ok" for j in joined)
    # systemd_edit: prova do valor gravado (file-op em python, sem subprocess)
    assert "Environment=B" in unit.read_text(encoding="utf-8")
    # ledger_close: status gravado
    assert json.loads(ledger.read_text())["status"] == "closed"
    # prova pós do merge: head saiu de sha_main para sha_feature
    state = json.loads(Path(env["DEPLOY_FAKE_STATE"]).read_text())
    assert state["repos"][repo]["head"] == "sha_feature"


# ---------- f) JSON em 1 linha, sempre com untrusted e notice ----------
@pytest.mark.parametrize("apply", [False, True])
def test_f_json_1_linha_com_untrusted_e_notice(tmp_path, apply):
    env = _base_env(tmp_path)
    _seed_state(tmp_path)
    repo = str(tmp_path / "repo")
    plan = {
        "operatorOrder": ["1"],
        "steps": [{"type": "merge", "repo": repo, "branch": "feature", "into": "main"}],
    }
    proc = _run_script(tmp_path, plan, env, apply=apply)
    # exatamente 1 linha de stdout, JSON parseável
    assert proc.stdout.strip().count("\n") == 0
    out = json.loads(proc.stdout)
    assert out.get("untrusted") is True
    assert isinstance(out.get("notice"), str) and out["notice"]
    assert NOTICE in out["notice"]
    assert proc.returncode == 0
