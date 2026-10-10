"""VAGUEIO-01 (§3) — detector de vagueio com abort antecipado (tudo mockado).

Caso real de origem (08/10): 8 runs FAIL por max_turns em que o worker passou
a run inteira só explorando (44–184 Bash, ZERO Write/Edit) — a última foi a
própria missão de construir este detector: 177 Bash / 0 Write, US$ 0,062.
Política §3: N turnos consecutivos sem entregável → FAIL "vagueio" antecipado,
com evidência no trail e recomendacao de re-run no resumo/checkpoint.
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


class VagueioBridge:
    """Roteiro: "bash" (turno só explorando) ou "escreve" (Write que
    satisfaz a stop-condition). Registra chamadas p/ contar turnos."""

    def __init__(self, script):
        self.script = list(script)
        self.n = 0

    def __call__(self, messages, system, ledger, model=None):
        self.n += 1
        spec = self.script.pop(0)
        if spec == "bash":
            d = {"model": model,
                 "content": [tool_use(self.n, "Bash",
                                      {"command": "ls -la /tmp | head"})],
                 "stop_reason": "tool_use",
                 "usage": {"input_tokens": 1000, "output_tokens": 100}}
        elif spec == "read":
            d = {"model": model,
                 "content": [tool_use(self.n, "Read", {"path": "contrato.md"})],
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


class EscreveBridge(VagueioBridge):
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
        # VAGUEIO-01: advisor-midrun default ON consome chamadas do bridge
        # mockado e desalinha o roteiro — patch do ATRIBUTO de módulo (o env
        # é lido no import, que na suite já aconteceu antes deste arquivo).
        self._adv = harness.HARNESS_ADVISOR
        harness.HARNESS_ADVISOR = False
        # FORCA-ESCRITA-01: paridade (item 6) — estes testes verificam o
        # gatilho clássico do vagueio; com a força-escrita ligada o aborto
        # é adiado e o roteiro de 8 bashes não chega ao gatilho antigo.
        self._forca = harness.FORCA_ESCRITA
        harness.FORCA_ESCRITA = 0
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

    def go(self, bridge, max_turns=8, **kw):
        return harness.run_mission(self.contract, self.base, 10.0, max_turns, seed=7,
                                   ledger=harness.Ledger(self.prices), bridge_fn=bridge,
                                   log=io.StringIO(), escada=False, **kw)

    def trail(self, s):
        return [json.loads(l) for l in open(s["trail"], encoding="utf-8")]


class TestVagueio(Base):
    def test_dispara_no_gatilho(self):
        """8 vagueios seguidos → FAIL 'vagueio' antecipado (não max_turns)."""
        fb = VagueioBridge(["bash"] * 8)
        s = self.go(fb, max_turns=20)
        self.assertEqual(s["veredito"], "FAIL")
        self.assertEqual(s["motivo"], "vagueio")
        self.assertTrue(s["vagueio"])
        self.assertEqual(s["turnos_vagueio"], harness.VAGUEIO_TRIGGER)
        # antecipado: pousou no turno do gatilho, não no 20
        self.assertLess(s["turnos"], 20)
        evs = [e for e in self.trail(s) if e.get("tool") == "_vagueio"]
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["streak"], harness.VAGUEIO_TRIGGER)

    def test_write_no_meio_zera_contador(self):
        """Write no meio do streak reseta — nunca dispara."""
        fb = VagueioBridge(["bash"] * 7 + ["escreve"] + ["bash"] * 7 + ["escreve"])
        s = self.go(fb, max_turns=20)
        self.assertNotEqual(s["motivo"], "vagueio")
        self.assertFalse(s["vagueio"])
        self.assertEqual(s["turnos_vagueio"], 0)
        self.assertEqual(s["veredito"], "PASS")  # stop-condition pelo Write

    def test_flag_off_e_paridade(self):
        """--vagueio off: vagueio infinito vira FAIL max_turns (comportamento antigo)."""
        fb = VagueioBridge(["bash"] * 20)
        s = self.go(fb, max_turns=8, vagueio=False)
        self.assertEqual(s["veredito"], "FAIL")
        self.assertEqual(s["motivo"], "max_turns")
        self.assertFalse(s["vagueio"])
        evs = [e for e in self.trail(s) if e.get("tool") == "_vagueio"]
        self.assertEqual(evs, [])

    def test_recomendacao_no_resumo(self):
        """FAIL vagueio carrega recomendacao (comandos/arquivos p/ re-run)."""
        fb = VagueioBridge(["bash"] * 8)
        s = self.go(fb, max_turns=20)
        rec = s["recomendacao"]
        self.assertIsInstance(rec, dict)
        self.assertIn("nota", rec)
        self.assertTrue(any("ls -la" in c for c in rec["ultimos_comandos"]))
        self.assertEqual(rec["turnos_vagueio"], harness.VAGUEIO_TRIGGER)


if __name__ == "__main__":
    unittest.main()
