"""HYGIENE-01b — testes de higiene: métricas de tempo no resumo e
make_run_dir resiliente a PermissionError (tudo mockado)."""
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

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


class EscreveBridge:
    """2 turnos: Write que satisfaz a stop-condition."""

    def __init__(self):
        self.n = 0

    def __call__(self, messages, system, ledger, model=None):
        self.n += 1
        d = {"model": model,
             "content": [tool_use(self.n, "Write",
                                  {"path": "alvo.txt", "content": "pronto"})],
             "stop_reason": "tool_use",
             "usage": {"input_tokens": 1000, "output_tokens": 100}}
        usd = ledger.add(d["model"], d["usage"])
        return d, usd, 0.01, 0


class Base(unittest.TestCase):
    def setUp(self):
        self._adv = harness.HARNESS_ADVISOR
        harness.HARNESS_ADVISOR = False
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.prices = os.path.join(self.dir, "prices.json")
        json.dump(PRICES, open(self.prices, "w"))
        self.contract = os.path.join(self.dir, "contrato.md")
        open(self.contract, "w").write(CONTRACT)
        self.base = os.path.join(self.dir, "runs")

    def tearDown(self):
        harness.HARNESS_ADVISOR = self._adv
        self.tmp.cleanup()

    def go(self, bridge, max_turns=8, **kw):
        return harness.run_mission(self.contract, self.base, 10.0, max_turns, seed=7,
                                   ledger=harness.Ledger(self.prices), bridge_fn=bridge,
                                   log=io.StringIO(), escada=False, **kw)


class TestHygiene(Base):
    def test_resumo_tem_metricas_tempo(self):
        s = self.go(EscreveBridge(), max_turns=2)
        self.assertIn("run_tempo_ms", s)
        self.assertIn("tempo_turno_p50_ms", s)
        self.assertIsInstance(s["run_tempo_ms"], int)
        self.assertGreater(s["run_tempo_ms"], 0)
        self.assertIsInstance(s["tempo_turno_p50_ms"], int)
        self.assertGreater(s["tempo_turno_p50_ms"], 0)

    def test_make_run_dir_resiliente_permissionerror(self):
        real = os.makedirs
        calls = []

        def flaky(path, *a, **kw):
            if "runs" in str(path) and not calls:
                calls.append(path)
                raise PermissionError(path)
            return real(path, *a, **kw)

        with mock.patch("os.makedirs", side_effect=flaky):
            s = self.go(EscreveBridge(), max_turns=2)
        self.assertEqual(s["veredito"], "PASS")
        self.assertTrue(os.path.exists(s["trail"]))

    def test_resumo_chaves_antigas(self):
        s = self.go(EscreveBridge(), max_turns=2)
        for k in ("veredito", "turnos", "custo", "trail", "run_dir"):
            self.assertIn(k, s)