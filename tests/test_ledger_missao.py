"""Testes do ledger de missão (DESP-03). Só tmp_path + runner/sleep falsos."""
import json
import os

import pytest

from scripts import ledger_missao as m


class Proc:
    def __init__(self, stdout):
        self.stdout = stdout


def runner_abas(abas):
    def _run(cmd):
        if cmd[:3] == ["herdr", "tab", "list"]:
            return Proc(json.dumps({"tabs": abas}))
        if cmd[:3] == ["herdr", "tab", "close"]:
            return Proc("")
        if cmd[:2] == ["git", "-C"]:
            return Proc("abc1234 msg")
        return Proc("")
    return _run


def runner_nunca():
    def _run(cmd):
        if cmd[:3] == ["herdr", "tab", "list"]:
            return Proc(json.dumps({"tabs": []}))
        return Proc("")
    return _run


def test_registrar_achando_aba(tmp_path):
    sd = tmp_path / "state"
    abas = [{"label": "RUN:M1#s7", "id": "tab-1", "paneId": "pane-9"}]
    out = m.registrar("M1", "/tmp/x", "contrato.md", 7, state_dir=str(sd),
                      runner=runner_abas(abas), espera_s=0.1, sleep=lambda s: None)
    assert out["ok"] and out["tabId"] == "tab-1" and out["paneId"] == "pane-9"
    led = json.loads((sd / "M1.json").read_text())
    assert led["missionId"] == "M1" and led["status"] == "dispatched"
    assert led["engine"] == "harness" and led["spawned_by"] == "despachante"
    assert led["promptFile"] == "contrato.md" and led["cwd"] == "/tmp/x"
    assert led["resumeSessionId"] is None and led["creation"] == "harness"


def test_registrar_aba_ausente_fail_open(tmp_path):
    sd = tmp_path / "state"
    out = m.registrar("M2", "/tmp/x", "c.md", 3, state_dir=str(sd),
                      runner=runner_nunca(), espera_s=0.1, sleep=lambda s: None)
    assert out["ok"] and out["aviso"] == "aba_nao_encontrada"
    led = json.loads((sd / "M2.json").read_text())
    assert led["paneId"] is None and led["tabId"] is None


def test_ledger_terminal_nao_sobrescrito(tmp_path):
    sd = tmp_path / "state"
    sd.mkdir()
    (sd / "M3.json").write_text(json.dumps({"missionId": "M3", "status": "closed"}))
    out = m.registrar("M3", "/tmp/x", "c.md", 1, state_dir=str(sd),
                      runner=runner_abas([]), espera_s=0.1, sleep=lambda s: None)
    assert out["ok"] is False and out["erro"] == "LEDGER_TERMINAL"
    led = json.loads((sd / "M3.json").read_text())
    assert led["status"] == "closed"


def _fechar_base(tmp_path, veredito="PASS"):
    sd = tmp_path / "state"
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    abas = [{"label": "RUN:M4#s2", "id": "tab-4", "paneId": "pane-4"}]
    m.registrar("M4", str(cwd), "c.md", 2, state_dir=str(sd),
                runner=runner_abas(abas), espera_s=0.1, sleep=lambda s: None)
    resumo = tmp_path / "resumo.json"
    resumo.write_text(json.dumps({
        "veredito": veredito, "custo_usd": 0.12, "turnos": 9,
        "stop-conditions": ["cmd a", "cmd b"], "run_dir": str(tmp_path)}))
    return sd, cwd, resumo


def test_fechar_pass(tmp_path):
    sd, cwd, resumo = _fechar_base(tmp_path, "PASS")
    out = m.fechar("M4", str(resumo), state_dir=str(sd), runner=runner_abas([]))
    assert out["ok"] and out["status"] == "closed" and out["aba_fechada"]
    led = json.loads((sd / "M4.json").read_text())
    assert led["status"] == "closed" and led["veredito"] == "PASS"
    assert led["custo_usd"] == 0.12 and led["turnos"] == 9
    assert led["closedAt"] and led["relatorio"]
    rel = (cwd / "RELATORIO-M4.md").read_text()
    assert "PASS" in rel and "0.12" in rel and "abc1234" in rel


def test_fechar_fail(tmp_path):
    sd, cwd, resumo = _fechar_base(tmp_path, "FAIL")
    out = m.fechar("M4", str(resumo), state_dir=str(sd), runner=runner_abas([]))
    assert out["ok"] and out["status"] == "failed"
    led = json.loads((sd / "M4.json").read_text())
    assert led["status"] == "failed"


def test_fechar_sem_tab_id_nao_fecha_aba(tmp_path):
    sd = tmp_path / "state"
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    m.registrar("M5", str(cwd), "c.md", 1, state_dir=str(sd),
                runner=runner_nunca(), espera_s=0.1, sleep=lambda s: None)
    resumo = tmp_path / "resumo.json"
    resumo.write_text(json.dumps({"veredito": "PASS"}))
    out = m.fechar("M5", str(resumo), state_dir=str(sd), runner=runner_abas([]))
    assert out["ok"] and out["aba_fechada"] is False
    assert out.get("aviso") == "sem_tab_id"


def test_fechar_idempotente(tmp_path):
    sd, cwd, resumo = _fechar_base(tmp_path, "PASS")
    primeira = m.fechar("M4", str(resumo), state_dir=str(sd), runner=runner_abas([]))
    segunda = m.fechar("M4", str(resumo), state_dir=str(sd), runner=runner_abas([]))
    assert primeira["ok"] and segunda["ok"]
    assert segunda.get("idempotente") is True
    led = json.loads((sd / "M4.json").read_text())
    assert led["status"] == "closed"


def test_escrita_atomica(tmp_path):
    sd = tmp_path / "state"
    m.registrar("M6", "/tmp/x", "c.md", 1, state_dir=str(sd),
                runner=runner_nunca(), espera_s=0.1, sleep=lambda s: None)
    restos = [p for p in sd.iterdir() if p.name.endswith(".tmp")]
    assert restos == []
    assert (sd / "M6.json").exists()


def test_relatorio_cwd_ilegivel_cai_em_state_dir(tmp_path):
    sd = tmp_path / "state"
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    cwd.chmod(0o500)  # sem permissão de escrita
    try:
        m.registrar("M7", str(cwd), "c.md", 1, state_dir=str(sd),
                    runner=runner_nunca(), espera_s=0.1, sleep=lambda s: None)
        resumo = tmp_path / "resumo.json"
        resumo.write_text(json.dumps({"veredito": "PASS"}))
        out = m.fechar("M7", str(resumo), state_dir=str(sd), runner=runner_abas([]))
        assert out["ok"] and out["relatorio"]
        assert str(out["relatorio"]).startswith(str(sd / "relatorios"))
    finally:
        cwd.chmod(0o700)
