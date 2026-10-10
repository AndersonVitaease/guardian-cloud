"""JANELA-LEITURA (RD-H1H2-REPORT-01) — turnos só-leitura-governada dentro da
janela são neutros p/ vagueio; nudge AGIR-OU-PARAR 1x quando o streak de
leitura atinge HARNESS_READ_WINDOW; HARNESS_READ_WINDOW=0 = paridade antiga.
"""
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness  # noqa: E402

PRICES = {"models": {
    "z-ai/glm-5.3-flash": {"in": 0.15, "out": 0.5, "cache_read": 0.03},
}}

CONTRACT = """# CONTRATO TESTE seed={{SEED}}
```harness-stop
file alvo.txt
```
"""


def tool_use(i, name, inp):
    return {"type": "tool_use", "id": f"tu{i}", "name": name, "input": inp}


class RoteiroBridge:
    """Roteiro: "le" (code_find via tool), "bash" (Bash livre) ou "escreve"."""

    def __init__(self, script):
        self.script = list(script)
        self.n = 0

    def __call__(self, messages, system, ledger, model=None):
        self.n += 1
        spec = self.script.pop(0) if self.script else "le"
        if spec == "le":
            d = {"model": model,
                 "content": [tool_use(self.n, "code_find",
                                      {"query": "foo", "glob": "*.py"})],
                 "stop_reason": "tool_use",
                 "usage": {"input_tokens": 1000, "output_tokens": 100}}
        elif spec == "bash":
            d = {"model": model,
                 "content": [tool_use(self.n, "Bash",
                                      {"command": "ls -la /tmp | head"})],
                 "stop_reason": "tool_use",
                 "usage": {"input_tokens": 1000, "output_tokens": 100}}
        else:  # "escreve"
            d = {"model": model,
                 "content": [tool_use(self.n, "Write",
                                      {"path": "alvo.txt", "content": "pronto"})],
                 "stop_reason": "tool_use",
                 "usage": {"input_tokens": 1000, "output_tokens": 100}}
        usd = ledger.add(d["model"], d["usage"])
        return d, usd, 0.01, 0


def _setup():
    tmp = tempfile.TemporaryDirectory()
    d = tmp.name
    prices = os.path.join(d, "prices.json")
    json.dump(PRICES, open(prices, "w"))
    contract = os.path.join(d, "contrato.md")
    open(contract, "w").write(CONTRACT)
    return tmp, contract, prices, os.path.join(d, "runs")


def _go(contract, prices, base, bridge, max_turns=30, **kw):
    return harness.run_mission(contract, base, 10.0, max_turns, seed=7,
                               ledger=harness.Ledger(prices), bridge_fn=bridge,
                               log=io.StringIO(), escada=False, **kw)


def _trail(s):
    return [json.loads(l) for l in open(s["trail"], encoding="utf-8")]


def test_leitura_dentro_da_janela_neutra(monkeypatch):
    """(a) N leituras dentro da janela NÃO disparam vagueio nem nudge."""
    monkeypatch.setattr(harness, "HARNESS_ADVISOR", False)
    monkeypatch.setattr(harness, "FORCA_ESCRITA", 0)
    monkeypatch.setattr(harness, "HARNESS_READ_WINDOW", 12)
    tmp, contract, prices, base = _setup()
    try:
        fb = RoteiroBridge(["le"] * 5 + ["escreve"])
        s = _go(contract, prices, base, fb)
        assert s["veredito"] == "PASS"
        assert not s["vagueio"]
        assert s["turnos_vagueio"] == 0
        evs = [e for e in _trail(s) if e.get("tool") == "_janela_leitura"]
        assert evs == []
    finally:
        tmp.cleanup()


def test_leitura_fora_da_janela_conta_vagueio(monkeypatch):
    """(b) leitura FORA da janela conta pro vagueio (paridade antiga)."""
    monkeypatch.setattr(harness, "HARNESS_ADVISOR", False)
    monkeypatch.setattr(harness, "FORCA_ESCRITA", 0)
    monkeypatch.setattr(harness, "HARNESS_READ_WINDOW", 2)
    tmp, contract, prices, base = _setup()
    try:
        fb = RoteiroBridge(["le"] * (harness.VAGUEIO_TRIGGER + 2))
        s = _go(contract, prices, base, fb)
        assert s["veredito"] == "FAIL"
        assert s["motivo"] == "vagueio"
        assert s["vagueio"]
    finally:
        tmp.cleanup()


def test_nudge_agir_ou_parar_uma_vez(monkeypatch):
    """(c) streak >= janela injeta nudge tipada UMA vez (evento no trail)."""
    monkeypatch.setattr(harness, "HARNESS_ADVISOR", False)
    monkeypatch.setattr(harness, "FORCA_ESCRITA", 0)
    monkeypatch.setattr(harness, "HARNESS_READ_WINDOW", 3)
    tmp, contract, prices, base = _setup()
    try:
        fb = RoteiroBridge(["le"] * 6 + ["escreve"])
        s = _go(contract, prices, base, fb)
        evs = [e for e in _trail(s) if e.get("tool") == "_janela_leitura"]
        assert len(evs) == 1
        assert evs[0]["tipo"] == "AGIR_OU_PARAR"
        assert evs[0]["streak"] == 3
        assert evs[0]["janela"] == 3
    finally:
        tmp.cleanup()


def test_window_zero_paridade_antiga(monkeypatch):
    """(d) HARNESS_READ_WINDOW=0: leitura conta como vagueio desde o turno 1."""
    monkeypatch.setattr(harness, "HARNESS_ADVISOR", False)
    monkeypatch.setattr(harness, "FORCA_ESCRITA", 0)
    monkeypatch.setattr(harness, "HARNESS_READ_WINDOW", 0)
    tmp, contract, prices, base = _setup()
    try:
        fb = RoteiroBridge(["le"] * harness.VAGUEIO_TRIGGER)
        s = _go(contract, prices, base, fb)
        assert s["veredito"] == "FAIL"
        assert s["motivo"] == "vagueio"
        assert s["turnos_vagueio"] == harness.VAGUEIO_TRIGGER
        evs = [e for e in _trail(s) if e.get("tool") == "_janela_leitura"]
        assert evs == []
    finally:
        tmp.cleanup()


def test_write_zera_streaks(monkeypatch):
    """(e) turno com Write é produtivo: zera vagueio e leitura_streak."""
    monkeypatch.setattr(harness, "HARNESS_ADVISOR", False)
    monkeypatch.setattr(harness, "FORCA_ESCRITA", 0)
    monkeypatch.setattr(harness, "HARNESS_READ_WINDOW", 3)
    tmp, contract, prices, base = _setup()
    try:
        fb = RoteiroBridge(["le"] * 2 + ["escreve"] + ["le"] * 2 + ["escreve"])
        s = _go(contract, prices, base, fb)
        assert s["veredito"] == "PASS"
        assert not s["vagueio"]
        assert s["turnos_vagueio"] == 0
        # streak de leitura zerou no Write: nunca atingiu a janela (3)
        evs = [e for e in _trail(s) if e.get("tool") == "_janela_leitura"]
        assert evs == []
    finally:
        tmp.cleanup()