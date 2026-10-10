import json
import inspect

import pytest

from scripts import ledger_missao as m


class Proc:
    def __init__(self, rc=0, stdout=""):
        self.rc = rc
        self.stdout = stdout

    def wait(self):
        return self.rc


def _runner(saida):
    def run(cmd):
        return Proc(stdout=saida)
    return run


def _saida(abas, aninhada):
    if aninhada:
        return json.dumps({"id": "cli:tab:list", "result": {"tabs": abas}, "type": "tab_list"})
    return json.dumps({"tabs": abas})


def _registrar(tmp_path, abas, aninhada):
    runner = _runner(_saida(abas, aninhada))
    return m.registrar(
        "M1", "/tmp/x", "contrato.md", 7,
        state_dir=str(tmp_path / "state"),
        runner=runner, espera_s=0.1, sleep=lambda s: None,
    )


def test_achar_aba_result_tabs(tmp_path):
    abas = [{"label": "RUN:M1#s7", "id": "tab-1", "paneId": "pane-9"}]
    out = _registrar(tmp_path, abas, aninhada=True)
    assert out["ok"]
    assert out["tabId"] == "tab-1"
    assert out["paneId"] == "pane-9"
    ledger = json.loads((tmp_path / "state" / "M1.json").read_text())
    assert ledger["status"] == "dispatched"


def test_compat_tabs_no_topo(tmp_path):
    abas = [{"label": "RUN:M1#s7", "id": "tab-1", "paneId": "pane-9"}]
    out = _registrar(tmp_path, abas, aninhada=False)
    assert out["ok"]
    assert out["tabId"] == "tab-1"
    assert out["paneId"] == "pane-9"


def test_espera_default_menor_que_timeout_chamador():
    assert inspect.signature(m.registrar).parameters["espera_s"].default == 20