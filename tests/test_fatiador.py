"""FATIADOR-01 — parser de `## Entregas` + orquestração sequencial (bridge mockada,
padrão test_escada.py: sem LLM real)."""
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness  # noqa: E402
from scripts import fatiador  # noqa: E402

PRICES = {"models": {
    "z-ai/glm-5.3-flash": {"in": 0.15, "out": 0.5, "cache_read": 0.03},
}}

CONTRACT = """# CONTRATO TESTE seed={{SEED}}

Contexto: mapa inteiro do contrato original.

## Entregas

1. Primeira entrega: escrever `a.txt` com "um".
2. Segunda entrega: escrever `b.txt` com "dois".
3. Terceira entrega: escrever `c.txt` com "tres".

## Regras

Worker; paridade total.

```harness-stop
file a.txt
file b.txt
file c.txt
```
"""


def tool_use(i, name, inp):
    return {"type": "tool_use", "id": f"tu{i}", "name": name, "input": inp}


class Bridge:
    """Roteiro fixo: "escreve" satisfaz a stop-condition; "vazia" queima turno."""

    def __init__(self, script):
        self.script = list(script)
        self.n = 0

    def __call__(self, messages, system, ledger, model=None):
        self.n += 1
        spec = self.script.pop(0)
        if spec == "vazia":
            d = {"model": model, "content": [], "stop_reason": "max_tokens",
                 "usage": {"input_tokens": 1000, "output_tokens": 200}}
        else:
            d = {"model": model,
                 "content": [tool_use(self.n * 10 + k, "Write",
                                      {"path": fn, "content": "pronto"})
                             for k, fn in enumerate(("a.txt", "b.txt", "c.txt"))],
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


class TestParser(Base):
    def test_3_entregas_3_subcontratos_com_stops_e_mapa(self):
        fatias = fatiador.fatiar(CONTRACT)
        self.assertEqual(len(fatias), 3)
        for f in fatias:
            self.assertIn("Contexto: mapa inteiro do contrato original.", f)
            self.assertIn("file a.txt", f)
            self.assertIn("file b.txt", f)
            self.assertIn("file c.txt", f)
            self.assertIn("## Regras", f)
        self.assertIn("Primeira entrega", fatias[0])
        self.assertNotIn("Segunda entrega", fatias[0])
        self.assertIn("Segunda entrega", fatias[1])
        self.assertIn("Terceira entrega", fatias[2])


class TestOrquestracao(Base):
    def _run(self, bridge, **kw):
        return fatiador.rodar_fatias(
            self.contract, self.base, budget=0.3, seed=5, max_turns=6,
            bridge_fn=bridge, ledger=harness.Ledger(self.prices),
            log=io.StringIO(), escada=False, vagueio=False, **kw)

    def test_pass_na_1_fail_na_2_3_nao_roda(self):
        # fatia 1: escreve (PASS); fatia 2: vazia, vazia... (FAIL max_turns)
        b = Bridge(["escreve", "vazia", "vazia", "vazia", "vazia", "vazia", "vazia"])
        r = self._run(b)
        self.assertEqual(r["veredito_geral"], "FAIL")
        self.assertEqual([f["fatia"] for f in r["fatias"]], [1, 2])
        self.assertEqual(r["fatias"][0]["veredito"], "PASS")
        self.assertEqual(r["fatias"][1]["veredito"], "FAIL")
        est = json.load(open(os.path.join(self.base, "fatiador", "5",
                                          "estado.json")))
        self.assertEqual(est["fatia"], 2)
        self.assertEqual(est["run_dir"], r["fatias"][1]["run_dir"])
        # custo agregado = soma das fatias rodadas
        self.assertAlmostEqual(r["custo_total_usd"],
                               sum(f["custo_usd"] for f in r["fatias"]), places=8)

    def test_todas_pass(self):
        b = Bridge(["escreve"] * 3)
        r = self._run(b)
        self.assertEqual(r["veredito_geral"], "PASS")
        self.assertEqual([f["veredito"] for f in r["fatias"]], ["PASS"] * 3)
        self.assertEqual(len(r["fatias"]), 3)

    def test_retomar_injeta_checkpoint(self):
        b1 = Bridge(["escreve", "vazia", "vazia", "vazia", "vazia", "vazia", "vazia"])
        r1 = self._run(b1)
        run_dir_f2 = r1["fatias"][1]["run_dir"]
        # grava CHECKPOINT.json fake no run_dir da fatia 2 (o harness lê dele)
        json.dump({"janela": "fatia-2"}, open(os.path.join(run_dir_f2,
                                                          "CHECKPOINT.json"), "w"))
        b2 = Bridge(["escreve", "escreve"])
        r2 = self._run(b2, retomar=5)
        self.assertEqual([f["fatia"] for f in r2["fatias"]], [3])
        trail = [json.loads(l) for l in open(r2["fatias"][0]["trail"],
                                             encoding="utf-8")]
        cfg = [e for e in trail if e.get("tool") == "_config"][0]
        self.assertEqual(cfg["checkpoint_from"], run_dir_f2)
        self.assertEqual(r2["veredito_geral"], "PASS")


if __name__ == "__main__":
    unittest.main()
