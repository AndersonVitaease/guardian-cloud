"""FORTIFY-01B — header _config no trail (auditabilidade de runs escaladas).

Caso real de origem: sudo env_reset droppa HARNESS_MODEL — runs "escaladas"
rodaram flash em silêncio. O evento _config registra o modelo efetivo, flags
de escada/vagueio, budget e max_turns logo no início da run.
"""
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness  # noqa: E402

PRICES = {"models": {
    "z-ai/glm-5.3-flash": {"in": 0.15, "out": 0.5, "cache_read": 0.03},
    "z-ai/glm-5.3": {"in": 0.075, "out": 4.2, "cache_read": 0.0075},
}}

CONTRACT = """# CONTRATO TESTE seed={{SEED}}
```harness-stop
file alvo.txt
```
"""


def tool_use(i, name, inp):
    return {"type": "tool_use", "id": f"tu{i}", "name": name, "input": inp}


class MockBridge:
    """Bridge mockada: 1º turno escreve alvo.txt (satisfaz stop-condition)."""

    def __init__(self):
        self.models = []
        self.n = 0

    def __call__(self, messages, system, ledger, model=None):
        self.models.append(model)
        self.n += 1
        d = {"model": model,
             "content": [tool_use(self.n, "Write",
                                  {"path": "alvo.txt", "content": "pronto"})],
             "stop_reason": "tool_use",
             "usage": {"input_tokens": 1000, "output_tokens": 200}}
        usd = ledger.add(d["model"], d["usage"])
        return d, usd, 0.01, 0


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.prices = os.path.join(self.dir, "prices.json")
        json.dump(PRICES, open(self.prices, "w"))
        self.contract = os.path.join(self.dir, "contrato.md")
        open(self.contract, "w").write(CONTRACT)
        self.base = os.path.join(self.dir, "cwd")
        os.makedirs(self.base)

    def tearDown(self):
        self.tmp.cleanup()

    def go(self, bridge, max_turns=4, **kw):
        return harness.run_mission(self.contract, self.base, 10.0, max_turns,
                                   seed=7, ledger=harness.Ledger(self.prices),
                                   bridge_fn=bridge, log=io.StringIO(), **kw)

    def trail(self, s):
        return [json.loads(l) for l in open(s["trail"], encoding="utf-8")]


class TestConfigHeader(Base):
    def test_evento_config_no_trail(self):
        fb = MockBridge()
        s = self.go(fb, max_turns=4, escada=True, vagueio=True)
        evs = [e for e in self.trail(s) if e.get("tool") == "_config"]
        self.assertEqual(len(evs), 1)
        ev = evs[0]
        self.assertEqual(ev["turno"], 0)
        self.assertEqual(ev["model"], "z-ai/glm-5.3-flash")
        self.assertEqual(ev["escada"], True)
        self.assertEqual(ev["vagueio"], True)
        self.assertEqual(ev["budget_usd"], 10.0)
        self.assertEqual(ev["max_turns"], 4)

    def test_config_antes_do_primeiro_llm(self):
        fb = MockBridge()
        s = self.go(fb, max_turns=4)
        evs = self.trail(s)
        idx_cfg = next(i for i, e in enumerate(evs) if e.get("tool") == "_config")
        idx_llm = next(i for i, e in enumerate(evs) if e.get("tool") == "llm")
        self.assertLess(idx_cfg, idx_llm)

    def test_config_registra_checkpoint_from(self):
        os.environ["HARNESS_CHECKPOINT_FROM"] = "/tmp/janela-anterior"
        try:
            fb = MockBridge()
            s = self.go(fb, max_turns=4)
            ev = [e for e in self.trail(s) if e.get("tool") == "_config"][0]
            self.assertEqual(ev["checkpoint_from"], "/tmp/janela-anterior")
        finally:
            os.environ.pop("HARNESS_CHECKPOINT_FROM", None)

    def test_pane_primeira_linha_config(self):
        fb = MockBridge()
        s = self.go(fb, max_turns=4, escada=False, vagueio=False)
        pane = open(os.path.join(s["run_dir"], "harness-pane.log"),
                    encoding="utf-8").read().splitlines()
        cfg = [l for l in pane if "config |" in l]
        self.assertTrue(cfg, pane)
        self.assertIn("model=z-ai/glm-5.3-flash escada=False vagueio=False "
                      "budget=$10.0", cfg[0])


if __name__ == "__main__":
    unittest.main()
