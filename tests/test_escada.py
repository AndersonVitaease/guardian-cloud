"""ESCADA-01 (§4) — escada de camada automática (sem LLM real, tudo mockado).

Caso real de origem: GUARDIAN-SITE-V4-02 (08/10) — 4 turnos de resposta vazia
(stop=max_tokens, sem texto e sem tool_use) queimando budget sem saída.
Política aprovada pelo operator: 2 degenerações consecutivas → o harness sobe
sozinho para o modelo mais forte até o fim da run, com custo separado.
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
    "nex-agi/nex-n2.5-pro": {"in": 0.075, "out": 0.25, "cache_read": 0.015},
}}

CONTRACT = """# CONTRATO TESTE seed={{SEED}}
```harness-stop
file alvo.txt
```
"""


def tool_use(i, name, inp):
    return {"type": "tool_use", "id": f"tu{i}", "name": name, "input": inp}


class EscadaBridge:
    """Bridge mockada com roteiro fixo de respostas.

    Especificação por turno: "vazia" (sem texto, sem tool_use, stop=max_tokens)
    ou "escreve" (tool_use Write que cria alvo.txt e satisfaz a stop-condition).
    Registra o `model` pedido a cada chamada (é aí que a escada aparece).
    """

    def __init__(self, script):
        self.script = list(script)
        self.models = []
        self.n = 0

    def __call__(self, messages, system, ledger, model=None):
        self.models.append(model)
        self.n += 1
        spec = self.script.pop(0)
        if spec == "vazia":
            d = {"model": model, "content": [], "stop_reason": "max_tokens",
                 "usage": {"input_tokens": 1000, "output_tokens": 200}}
        else:
            d = {"model": model,
                 "content": [tool_use(self.n, "Write",
                                      {"path": "alvo.txt", "content": "pronto"})],
                 "stop_reason": "tool_use",
                 "usage": {"input_tokens": 2000, "output_tokens": 400}}
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
        self.base = os.path.join(self.dir, "runs")

    def tearDown(self):
        self.tmp.cleanup()

    def go(self, bridge, max_turns=8, **kw):
        return harness.run_mission(self.contract, self.base, 10.0, max_turns, seed=7,
                                   ledger=harness.Ledger(self.prices), bridge_fn=bridge,
                                   log=io.StringIO(), **kw)

    def trail(self, s):
        return [json.loads(l) for l in open(s["trail"], encoding="utf-8")]


class TestEscada(Base):
    def test_gatilho_2_vazias_sobe_modelo(self):
        """2 respostas vazias seguidas → 3º turno sai com o modelo da escada."""
        fb = EscadaBridge(["vazia", "vazia", "escreve"])
        s = self.go(fb, max_turns=6)
        self.assertEqual(s["veredito"], "PASS")
        self.assertEqual(fb.models[:2], ["z-ai/glm-5.3-flash"] * 2)
        self.assertEqual(fb.models[2], harness.ESCADA_MODEL)
        self.assertTrue(s["escalada"])
        self.assertEqual(s["model_escalada"], harness.ESCADA_MODEL)

    def test_evento_escada_no_trail_e_custo_separado(self):
        fb = EscadaBridge(["vazia", "vazia", "escreve"])
        s = self.go(fb, max_turns=6)
        evs = [e for e in self.trail(s) if e.get("tool") == "_escada"]
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["para"], harness.ESCADA_MODEL)
        self.assertEqual(evs[0]["de"], "z-ai/glm-5.3-flash")
        # contabilidade separada: fase escalada = 2000in/400out do pro
        self.assertAlmostEqual(s["custo"]["escalada_usd"],
                               (2000 * 0.075 + 400 * 0.25) / 1e6, places=8)
        # custo total = 2 turnos flash + 1 turno pro
        self.assertAlmostEqual(
            s["custo"]["usd"],
            2 * (1000 * 0.15 + 200 * 0.5) / 1e6 + (2000 * 0.075 + 400 * 0.25) / 1e6,
            places=8)

    def test_1_vazia_isolada_nao_sobe(self):
        """Vazia isolada (turno produtivo no meio) reseta o contador."""
        fb = EscadaBridge(["vazia", "escreve"])
        s = self.go(fb, max_turns=6)
        self.assertEqual(s["veredito"], "PASS")
        self.assertFalse(s["escalada"])
        self.assertEqual(s["model_escalada"], None)
        self.assertEqual(s["custo"]["escalada_usd"], 0.0)
        self.assertEqual(fb.models, ["z-ai/glm-5.3-flash"] * 2)

    def test_flag_off_nunca_sobe(self):
        """escada=False (CLI --escada off): paridade exata do comportamento antigo."""
        fb = EscadaBridge(["vazia", "vazia", "escreve"])
        s = self.go(fb, max_turns=6, escada=False)
        self.assertEqual(fb.models, ["z-ai/glm-5.3-flash"] * 3)
        self.assertFalse(s["escalada"])
        self.assertEqual(s["custo"]["escalada_usd"], 0.0)

    def test_turno_escalada_marcado_no_trail(self):
        fb = EscadaBridge(["vazia", "vazia", "escreve"])
        s = self.go(fb, max_turns=6)
        llms = [e for e in self.trail(s) if e.get("tool") == "llm"]
        self.assertEqual([e.get("escalada") for e in llms], [False, True, True])


if __name__ == "__main__":
    unittest.main()
