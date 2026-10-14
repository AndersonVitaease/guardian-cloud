"""FORCA-ESCRITA-01 — força Write/Edit quando o worker vagueia sem escrever.

Complemento do VAGUEIO-01: em vez de só abortar, na metade do gatilho o
harness injeta aviso e restringe as tools a Write/Edit por N turnos
(HARNESS_FORCA_ESCRITA, default 3). O aborto é adiado para
VAGUEIO_TRIGGER + N enquanto a força está ativa. Flag 0 = comportamento
idêntico ao anterior.
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


class ForcaBridge:
    """Roteiro por turno: 'bash' (só explora), 'escreve' (Write do alvo).
    Registra as tools recebidas em cada chamada."""

    def __init__(self, script):
        self.script = list(script)
        self.n = 0
        self.tools_por_turno = []

    def __call__(self, messages, system, ledger, model=None, tools=None):
        self.n += 1
        self.tools_por_turno.append(tools)
        spec = self.script.pop(0)
        if spec == "bash":
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


class Base(unittest.TestCase):
    def setUp(self):
        self._adv = harness.HARNESS_ADVISOR
        harness.HARNESS_ADVISOR = False
        self._forca = harness.FORCA_ESCRITA
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
        self.tmp.cleanup()

    def go(self, bridge, max_turns=20, **kw):
        return harness.run_mission(self.contract, self.base, 10.0, max_turns, seed=7,
                                   ledger=harness.Ledger(self.prices), bridge_fn=bridge,
                                   log=io.StringIO(), escada=False, **kw)

    def trail(self, s):
        return [json.loads(l) for l in open(s["trail"], encoding="utf-8")]


class TestForcaEscrita(Base):
    def test_ativa_e_restringe_tools(self):
        """(a) 4 turnos só Bash ⇒ _forca_escrita no trail e o turno seguinte
        recebe só Write/Edit."""
        fb = ForcaBridge(["bash"] * 4 + ["escreve"])
        s = self.go(fb, max_turns=20)
        evs = [e for e in self.trail(s) if e.get("tool") == "_forca_escrita"]
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["streak"], max(2, harness.VAGUEIO_TRIGGER // 2))
        self.assertEqual(evs[0]["turnos"], harness.FORCA_ESCRITA)
        # ativação no turno 4 (streak >= 8//2) ⇒ turno 5 só Write/Edit
        self.assertEqual(len(fb.tools_por_turno), 5)
        tools_depois = fb.tools_por_turno[4]
        self.assertIsNotNone(tools_depois)
        self.assertEqual({t["name"] for t in tools_depois}, {"Write", "Edit"})
        # antes da ativação: lista completa (Bash/Read presentes)
        for i in range(4):
            t = fb.tools_por_turno[i]
            names = {x["name"] for x in t} if t is not None else set()
            self.assertIn("Bash", names)

    def test_escreve_no_turno_forcado_nao_aborta(self):
        """(b) worker escreve no turno forçado ⇒ não aborta por vagueio."""
        fb = ForcaBridge(["bash"] * 4 + ["escreve"])
        s = self.go(fb, max_turns=20)
        self.assertNotEqual(s["motivo"], "vagueio")
        self.assertFalse(s["vagueio"])
        self.assertEqual(s["verdict"] if "verdict" in s else s["veredito"], "PASS")

    def test_nao_escreve_nos_turnos_forcados_aborta(self):
        """(c) não escreve nos turnos forçados ⇒ aborta com 'vagueio' no
        gatilho adiado (VAGUEIO_TRIGGER + FORCA_ESCRITA)."""
        fb = ForcaBridge(["bash"] * 30)
        s = self.go(fb, max_turns=40)
        self.assertEqual(s["veredito"], "FAIL")
        self.assertEqual(s["motivo"], "vagueio")
        self.assertTrue(s["vagueio"])
        self.assertEqual(s["turnos_vagueio"],
                         harness.VAGUEIO_TRIGGER + harness.FORCA_ESCRITA)

    def test_flag_off_comportamento_antigo(self):
        """(d) HARNESS_FORCA_ESCRITA=0 ⇒ sem _forca_escrita e aborto no
        gatilho antigo (VAGUEIO_TRIGGER)."""
        harness.FORCA_ESCRITA = 0
        fb = ForcaBridge(["bash"] * 30)
        s = self.go(fb, max_turns=40)
        evs = [e for e in self.trail(s) if e.get("tool") == "_forca_escrita"]
        self.assertEqual(evs, [])
        self.assertEqual(s["motivo"], "vagueio")
        self.assertEqual(s["turnos_vagueio"], harness.VAGUEIO_TRIGGER)
        # com a flag off, tools nunca são restringidas (lista completa)
        for t in fb.tools_por_turno:
            names = {x["name"] for x in t} if t is not None else set()
            self.assertIn("Bash", names)

    def test_run_que_ja_escreveu_nunca_ativa(self):
        """(e) run que já escreveu antes ⇒ força-escrita nunca ativa."""
        fb = ForcaBridge(["escreve"] + ["bash"] * 12)
        s = self.go(fb, max_turns=20)
        evs = [e for e in self.trail(s) if e.get("tool") == "_forca_escrita"]
        self.assertEqual(evs, [])
        for t in fb.tools_por_turno:
            names = {x["name"] for x in t} if t is not None else set()
            self.assertIn("Bash", names)


if __name__ == "__main__":
    unittest.main()