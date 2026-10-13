#!/usr/bin/env python3
"""Prova GB-LEDGER-OCO-02 — PASS_OCO honesto + reconciliacao pelo resumo no fecho.

Hermética: ledger/state em tmpdir; entrega_verify simulada via ENTREGA_VERIFY_PATH.
(a) resumo PASS + entrega ok -> closed/PASS
(b) resumo PASS + entrega falha -> pass_oco com campo entrega (NUNCA failed);
    fecho seguinte com entrega ok -> closed/PASS (reconciliacao)
(c) resumo FAIL -> failed (regressao zero)
(d) tests/test_ledger_pass_oco.py passa
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
from scripts import ledger_missao as lm  # noqa: E402

MARKER = "GB-LEDGER-OCO-02-PROVA-OK"


class FakeResult:
    def __init__(self, rc=0, stdout="", stderr=""):
        self.returncode = rc
        self.stdout = stdout
        self.stderr = stderr


def setup(tmp):
    state = tmp / "state"
    state.mkdir(parents=True, exist_ok=True)
    (state / "M.json").write_text(
        json.dumps({"missionId": "M", "status": "running", "tabId": None}),
        encoding="utf-8")
    resumo = tmp / "resumo.json"
    resumo.write_text(json.dumps({"veredito": "PASS"}), encoding="utf-8")
    return state, str(resumo)


def fechar(state, resumo_path, entrega_ok):
    def runner(cmd, **kw):
        if cmd[1].endswith("entrega_verify.sh"):
            if entrega_ok:
                return FakeResult(0, json.dumps({"ok": True}), "")
            return FakeResult(0, json.dumps({"ok": False, "faltando": ["RELATORIO-M.md"]}), "")
        return FakeResult(0, "", "")
    return lm.fechar("M", resumo_path, state_dir=str(state), runner=runner)


def main():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # (a) PASS + entrega ok -> closed/PASS
        state, rp = setup(tmp / "a" if False else tmp)
        r = fechar(state, rp, entrega_ok=True)
        led = json.loads((state / "M.json").read_text())
        assert r["status"] == "closed" and led["veredito"] == "PASS", (r, led)
        print("(a) ok: PASS+entrega ok -> closed/PASS")

        # (b) PASS + entrega falha -> pass_oco (nunca failed); reconcilia depois
        state, rp = setup(tmp / "b")
        r = fechar(state, rp, entrega_ok=False)
        led = json.loads((state / "M.json").read_text())
        assert r["status"] == "pass_oco", r
        assert led["status"] == "pass_oco" and led["status"] != "failed", led
        assert led["veredito"] == "PASS_OCO", led
        assert led["entrega"]["ok"] is False and led["entrega"]["faltando"], led
        print("(b1) ok: PASS+entrega falha -> pass_oco (nunca failed), entrega registrada")
        r2 = fechar(state, rp, entrega_ok=True)
        led = json.loads((state / "M.json").read_text())
        assert r2["status"] == "closed" and led["veredito"] == "PASS", (r2, led)
        print("(b2) ok: reconciliacao pass_oco -> closed/PASS quando entrega ok")

        # (c) FAIL -> failed (regressao zero)
        state, rp = setup(tmp)
        (tmp / "resumo.json").write_text(json.dumps({"veredito": "FAIL"}), encoding="utf-8")
        r = fechar(state, rp, entrega_ok=True)
        led = json.loads((state / "M.json").read_text())
        assert r["status"] == "failed" and led["status"] == "failed", (r, led)
        print("(c) ok: FAIL -> failed")

    # (d) suite existente
    p = subprocess.run([sys.executable, "-m", "pytest", "tests/test_ledger_pass_oco.py", "-q"],
                       cwd=str(REPO), capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
    print("(d) ok: tests/test_ledger_pass_oco.py passa")
    print(MARKER)


if __name__ == "__main__":
    main()