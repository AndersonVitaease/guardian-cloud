"""RETRY-DECIDE-01 — testes de scripts/retry_decide.py + wiring no autoretry."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import retry_decide  # noqa: E402
import scripts.autoretry as autoretry  # noqa: E402


def _diag(**kw):
    base = {"veredito": "FAIL", "motivo": "max_turns", "turnos": 30,
            "custo_usd": 0.5,
            "stop_conditions": {"ok": [{"nome": "a", "kind": "file"}],
                                "pendentes": [{"nome": "b", "kind": "cmd"}]},
            "comandos_repetidos": [], "ultimas_acoes": [],
            "arquivo_mais_recente": "x.txt"}
    base.update(kw)
    return base


# ---- regra a) retry ----
def test_a_max_turns_progresso_retry():
    d = retry_decide.decidir(_diag())
    assert d["acao"] == "retry"
    assert d["mudancas"]["max_turns"] == "+15" and d["mudancas"]["seed"] == "+1"
    assert "progresso" in d["razao"]


def test_a_max_turns_com_loop_stop():
    d = retry_decide.decidir(_diag(comandos_repetidos=[{"prefixo": "x", "vezes": 3}]))
    assert d["acao"] == "stop"


def test_a_max_turns_sem_progresso_stop():
    d = retry_decide.decidir(_diag(stop_conditions={"ok": [], "pendentes": [{"nome": "b"}]}))
    assert d["acao"] == "stop"


# ---- regra b) attractor de loop ----
def test_b_loop_attractor_stop():
    d = retry_decide.decidir(_diag(
        motivo="parou_sem_stop_condition",
        stop_conditions={"ok": [], "pendentes": [{"nome": f"c{i}"} for i in range(5)]},
        comandos_repetidos=[{"prefixo": "cd /x", "vezes": 3}]))
    assert d["acao"] == "stop"
    assert "attractor" in d["razao"]


# ---- regra c) budget ----
def test_c_budget_stop():
    d = retry_decide.decidir(_diag(motivo="budget"))
    assert d["acao"] == "stop" and "orçamento" in d["razao"]


# ---- regra d) permissão ----
def test_d_permissao_stop():
    d = retry_decide.decidir(_diag(ultimas_acoes=[{"tool": "Bash", "cmd": "cat /etc/shadow"}]))
    assert d["acao"] == "retry"  # sem token de permissão -> segue outras regras
    d2 = retry_decide.decidir(_diag(ultimas_acoes=[
        {"tool": "Bash", "cmd": "PermissionError: denied"}]))
    assert d2["acao"] == "stop" and "permissão" in d2["razao"]


# ---- regra e) fail-closed ----
def test_e_unknown_fail_closed():
    assert retry_decide.decidir(None)["acao"] == "stop"
    assert retry_decide.decidir({})["acao"] == "stop"
    assert retry_decide.decidir(_diag(motivo="desconhecido"))["acao"] == "stop"


# ---- CLI ----
def _trail(tmp_path, eventos):
    p = tmp_path / "harness-trail.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for e in eventos:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return str(p)


def test_cli_exit0(tmp_path, capsys):
    trail = _trail(tmp_path, [
        {"turno": 1, "tool": "Write", "input": {"file_path": "a.txt", "content": "x"}},
        {"turno": 2, "tool": "_resumo", "veredito": "FAIL", "motivo": "max_turns",
         "turnos": 2, "custo": {"usd": 0.01},
         "stop_conditions": [{"kind": "file", "path": "a.txt", "ok": True},
                             {"kind": "cmd", "cmd": "pytest", "ok": False}]},
    ])
    rc = retry_decide.main([trail])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["acao"] == "retry"


# ---- wiring no autoretry ----
class _FakeHarness:
    pass


def _rodar(monkeypatch, tmp_path, decisao, n_calls_box):
    def fake_run(mission_path, run_dir, restante, max_turns, seed=0, model=None,
                 bridge_fn=None, contract_prefix="", **kw):
        n_calls_box[0] += 1
        os.makedirs(run_dir, exist_ok=True)
        return {"veredito": "FAIL", "run_dir": run_dir,
                "custo": {"usd": 0.01}}
    monkeypatch.setattr(autoretry.harness, "run_mission", fake_run)
    monkeypatch.setattr(autoretry.mission_run, "extrair_memoria", lambda p: None)
    import diagnostico
    monkeypatch.setattr(diagnostico, "bloco_diagnostico", lambda p: "bloco")
    import retry_decide as rd
    monkeypatch.setattr(rd, "decidir",
                        lambda diag: {"acao": decisao, "mudancas": None,
                                      "razao": "razao-teste"})
    agg = autoretry.rodar_com_retry("m.md", str(tmp_path / "base"), 1.0, 30,
                                    n_retries=1, seed0=100)
    return agg


def test_wiring_stop_quebra_loop(tmp_path, monkeypatch):
    box = [0]
    agg = _rodar(monkeypatch, tmp_path, "stop", box)
    assert box[0] == 1  # sem segunda tentativa
    assert agg["decisao"] == "stop" and agg["razao"] == "razao-teste"
    rep = os.path.join(str(tmp_path / "base"), "STOP_REPORT.md")
    assert os.path.isfile(rep)
    with open(rep, encoding="utf-8") as f:
        txt = f.read()
    assert "razao-teste" in txt and "DIAGNÓSTICO" in txt


def test_wiring_retry_segunda_tentativa(tmp_path, monkeypatch):
    box = [0]
    agg = _rodar(monkeypatch, tmp_path, "retry", box)
    assert box[0] == 2
    assert agg["decisao"] == "retry"
    assert agg["runs"][0].get("decisao") == "retry"


def test_wiring_falha_diagnostico_fallback_retry(tmp_path, monkeypatch):
    box = [0]

    def fake_run(mission_path, run_dir, restante, max_turns, seed=0, model=None,
                 bridge_fn=None, contract_prefix="", **kw):
        box[0] += 1
        os.makedirs(run_dir, exist_ok=True)
        return {"veredito": "FAIL", "run_dir": run_dir, "custo": {"usd": 0.01}}
    monkeypatch.setattr(autoretry.harness, "run_mission", fake_run)
    monkeypatch.setattr(autoretry.mission_run, "extrair_memoria", lambda p: None)
    import diagnostico
    monkeypatch.setattr(diagnostico, "bloco_diagnostico",
                        lambda p: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(retry_decide, "decidir",
                        lambda d: (_ for _ in ()).throw(RuntimeError("boom")))
    agg = autoretry.rodar_com_retry("m.md", str(tmp_path / "base"), 1.0, 30,
                                    n_retries=1, seed0=100)
    assert box[0] == 2  # fallback: retry como hoje