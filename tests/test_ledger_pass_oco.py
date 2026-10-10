"""RD-PASS-OCO-01: PASS sem entrega na raiz => veredito rebaixado para PASS_OCO."""
import json
import os
import sys

from scripts import ledger_missao as lm


def _mk_ledger(tmp_path, missao_id="M-TEST"):
    state = tmp_path / "state"
    state.mkdir()
    ledger = {"missionId": missao_id, "status": "running", "tabId": None}
    (state / ("%s.json" % missao_id)).write_text(json.dumps(ledger), encoding="utf-8")
    return state


def _mk_resumo(tmp_path, veredito="PASS"):
    p = tmp_path / "resumo.json"
    p.write_text(json.dumps({"veredito": veredito}), encoding="utf-8")
    return str(p)


class FakeResult:
    def __init__(self, rc=0, stdout="", stderr=""):
        self.returncode = rc
        self.stdout = stdout
        self.stderr = stderr


def test_pass_entrega_ok_mantem_closed(tmp_path):
    state = _mk_ledger(tmp_path)
    calls = []

    def runner(cmd, **kw):
        calls.append((cmd, kw))
        if cmd[1].endswith("entrega_verify.sh"):
            return FakeResult(0, json.dumps({"ok": True, "tool": "entrega_verify"}), "")
        return FakeResult(0, "", "")

    r = lm.fechar("M-TEST", _mk_resumo(tmp_path), state_dir=str(state), runner=runner)
    assert r["status"] == "closed"
    ledger = json.loads((state / "M-TEST.json").read_text())
    assert ledger["veredito"] == "PASS"
    assert ledger["entrega"] == {"ok": True}
    assert calls and "entrega_verify" in calls[0][0][1]
    assert calls[0][1]["env"]["ENTREGA_STATE_DIR"] == str(state)


def test_pass_entrega_faltando_rebaixa_pass_oco(tmp_path):
    state = _mk_ledger(tmp_path)

    def runner(cmd, **kw):
        if cmd[1].endswith("entrega_verify.sh"):
            return FakeResult(0, json.dumps({"ok": False, "faltando": ["RELATORIO-M-TEST.md"], "error": None}), "")
        return FakeResult(0, "", "")

    r = lm.fechar("M-TEST", _mk_resumo(tmp_path), state_dir=str(state), runner=runner)
    assert r["status"] == "failed"
    ledger = json.loads((state / "M-TEST.json").read_text())
    assert ledger["veredito"] == "PASS_OCO"
    assert ledger["entrega"]["ok"] is False
    assert ledger["entrega"]["faltando"] == ["RELATORIO-M-TEST.md"]


def test_pass_erro_execucao_fail_open(tmp_path):
    state = _mk_ledger(tmp_path)

    def runner(cmd, **kw):
        if cmd[1].endswith("entrega_verify.sh"):
            raise RuntimeError("boom")
        return FakeResult(0, "", "")

    r = lm.fechar("M-TEST", _mk_resumo(tmp_path), state_dir=str(state), runner=runner)
    assert r["status"] == "closed"
    ledger = json.loads((state / "M-TEST.json").read_text())
    assert ledger["veredito"] == "PASS"
    assert ledger["entrega"]["ok"] is None
    assert "boom" in ledger["entrega"]["aviso"]


def test_fail_nao_chama_entrega_verify(tmp_path):
    state = _mk_ledger(tmp_path)
    calls = []

    def runner(cmd, **kw):
        calls.append(cmd)
        return FakeResult(0, "", "")

    r = lm.fechar("M-TEST", _mk_resumo(tmp_path, veredito="FAIL"), state_dir=str(state), runner=runner)
    assert r["status"] == "failed"
    assert not any(len(c) > 1 and "entrega_verify" in c[1] for c in calls)
    ledger = json.loads((state / "M-TEST.json").read_text())
    assert "entrega" not in ledger


def test_idempotente_nao_reverifica(tmp_path):
    state = _mk_ledger(tmp_path)
    ledger_path = state / "M-TEST.json"
    ledger = json.loads(ledger_path.read_text())
    ledger["status"] = "closed"
    ledger["veredito"] = "PASS"
    ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
    calls = []

    def runner(cmd, **kw):
        calls.append(cmd)
        return FakeResult(0, "", "")

    r = lm.fechar("M-TEST", _mk_resumo(tmp_path), state_dir=str(state), runner=runner)
    assert r.get("idempotente") is True
    assert not calls