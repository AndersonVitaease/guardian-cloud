"""VAGUEIO-PROMPT-01 (§3) — nudge AGIR-OU-PARAR com prazo de entregável.

Ao 1º registro de vagueio o nudge injetado exige 1 entregável commitado nos
próximos VAGUEIO_PRAZO_1 (5) turnos; ao 2º, o prazo cai para VAGUEIO_PRAZO_2
(3). O FAIL antecipado respeita o prazo declarado (mesmo contador): nunca
dispara antes. VAGUEIO_PROMPT=0 → texto antigo intacto (paridade exata).
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
}}

CONTRACT = """# CONTRATO TESTE seed={{SEED}}
```harness-stop
file alvo.txt
```
"""


def tool_use(i, name, inp):
    return {"type": "tool_use", "id": f"tu{i}", "name": name, "input": inp}


class BashBridge:
    """Turno "bash" = vagueio (só Bash, sem entregável); "escreve" = Write."""

    def __init__(self, script):
        self.script = list(script)
        self.n = 0

    def __call__(self, messages, system, ledger, model=None):
        self.n += 1
        spec = self.script.pop(0) if self.script else "bash"
        if spec == "escreve":
            d = {"model": model,
                 "content": [tool_use(self.n, "Write",
                                      {"path": "alvo.txt", "content": "pronto"})],
                 "stop_reason": "tool_use",
                 "usage": {"input_tokens": 1000, "output_tokens": 100}}
        else:
            d = {"model": model,
                 "content": [tool_use(self.n, "Bash",
                                      {"command": "ls -la /tmp | head"})],
                 "stop_reason": "tool_use",
                 "usage": {"input_tokens": 1000, "output_tokens": 100}}
        usd = ledger.add(d["model"], d["usage"])
        return d, usd, 0.01, 0


class Base(unittest.TestCase):
    def setUp(self):
        self._adv = harness.HARNESS_ADVISOR
        self._forca = harness.FORCA_ESCRITA
        self._vp = harness.VAGUEIO_PROMPT
        harness.HARNESS_ADVISOR = False
        harness.FORCA_ESCRITA = 0
        harness.VAGUEIO_PROMPT = True
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.prices = os.path.join(self.dir, "prices.json")
        json.dump(PRICES, open(self.prices, "w"))
        self.contract = os.path.join(self.dir, "contrato.md")
        open(self.contract, "w").write(CONTRACT)
        self.base = os.path.join(self.dir, "runs")

    def tearDown(self):
        harness.HARNESS_ADVISOR = self._adv
        harness.FORCA_ESCRITA = self._forca
        harness.VAGUEIO_PROMPT = self._vp
        self.tmp.cleanup()

    def go(self, bridge, max_turns=30, **kw):
        return harness.run_mission(self.contract, self.base, 10.0, max_turns,
                                   seed=7, ledger=harness.Ledger(self.prices),
                                   bridge_fn=bridge, log=io.StringIO(),
                                   escada=False, **kw)

    def trail(self, s):
        return [json.loads(l) for l in open(s["trail"], encoding="utf-8")]

    def nudges(self, s):
        return [e for e in self.trail(s) if e.get("tool") == "_vagueio_prompt"]


class TestVagueioPrompt(Base):
    def test_primeiro_vagueio_nudge_5_turnos(self):
        """(a) 1º registro de vagueio → nudge diz '5 turnos' (VAGUEIO_PRAZO_1)."""
        fb = BashBridge(["bash"] * 2)
        s = self.go(fb, max_turns=30)
        evs = self.nudges(s)
        self.assertEqual(len(evs), 2)  # 1º e 2º registros
        self.assertEqual(evs[0]["streak"], 1)
        self.assertEqual(evs[0]["prazo"], 5)
        self.assertIn("5 turnos", evs[0]["nudge"])
        self.assertIn("FAIL vagueio", evs[0]["nudge"])
        self.assertIn("entregável commitado", evs[0]["nudge"])

    def test_segundo_vagueio_nudge_3_turnos(self):
        """(b) 2º registro → prazo cai para '3 turnos' (VAGUEIO_PRAZO_2)."""
        fb = BashBridge(["bash"] * 3)
        s = self.go(fb, max_turns=30)
        evs = self.nudges(s)
        self.assertGreaterEqual(len(evs), 2)
        self.assertEqual(evs[1]["streak"], 2)
        self.assertEqual(evs[1]["prazo"], 3)
        self.assertIn("3 turnos", evs[1]["nudge"])

    def test_fail_respeita_prazo(self):
        """(c) FAIL antecipado só APÓS o prazo declarado no nudge (mesmo contador)."""
        fb = BashBridge(["bash"] * 30)
        s = self.go(fb, max_turns=30)
        self.assertEqual(s["veredito"], "FAIL")
        self.assertEqual(s["motivo"], "vagueio")
        evs = self.nudges(s)
        # prazo declarado no 2º registro: 2 + 3 = FAIL só no turno >= 5
        self.assertEqual(evs[-1]["prazo_ate"], 2 + 3)
        self.assertGreaterEqual(s["turnos"], 5)
        # nunca antes: o gatilho clássico (8) só vale se prazo já venceu
        self.assertGreaterEqual(s["turnos"], evs[-1]["prazo_ate"])

    def test_flag_off_texto_antigo_intacto(self):
        """(d) VAGUEIO_PROMPT=0 → nenhum nudge novo; FAIL antigo no gatilho 8."""
        harness.VAGUEIO_PROMPT = False
        fb = BashBridge(["bash"] * 30)
        s = self.go(fb, max_turns=30)
        self.assertEqual(s["veredito"], "FAIL")
        self.assertEqual(s["motivo"], "vagueio")
        self.assertEqual(self.nudges(s), [])          # sem nudges novos
        self.assertEqual(s["turnos"], harness.VAGUEIO_TRIGGER)  # paridade antiga


if __name__ == "__main__":
    unittest.main()