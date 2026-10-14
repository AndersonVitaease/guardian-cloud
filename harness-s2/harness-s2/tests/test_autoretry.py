"""Suíte AUTORETRY-SCRIPT-01 — retry sequencial, sem rede (bridge falso injetado)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import autoretry  # noqa: E402

PRICES = {"models": {"z-ai/glm-5.3-flash": {"in": 0.15, "out": 0.5, "cache_read": 0.03}}}

CONTRACT = """# CONTRATO TESTE seed={{SEED}}
```harness-stop
file ok.txt
cmd test "$(cat ok.txt)" = ok
```
"""


def tool_use(i, name, inp):
    return {"type": "tool_use", "id": f"tu{i}", "name": name, "input": inp}


def resp(content, stop="tool_use", inp=1000, out=200):
    return {"model": "z-ai/glm-5.3-flash", "content": content, "stop_reason": stop,
            "usage": {"input_tokens": inp, "output_tokens": out}}


class FakeBridge:
    """Roteiriza respostas por (seed, n-ésima chamada); cobra via ledger."""

    def __init__(self, script_fn=None):
        self.script_fn = script_fn or (lambda seed, call: [])
        self.calls = []      # (seed, n_da_run, advisor?)
        self.systems = []    # system do kickoff de cada tentativa

    def __call__(self, messages, system, ledger, model=None):
        import re as _re
        m = _re.search(r"seed desta run: (\d+)", system or "")
        seed = int(m.group(1)) if m else None
        # kickoff = 1ª chamada da run (janela só com a mensagem user inicial)
        is_kickoff = len(messages) == 1 and "Execute o contrato abaixo EXATAMENTE" in (system or "")
        if is_kickoff:
            self.systems.append(system or "")
        if is_kickoff:
            self._run_n = 0
        self._run_n = getattr(self, "_run_n", 0) + 1
        n = self._run_n
        self.calls.append((seed, n, is_kickoff))
        d = self.script_fn(seed, n) or resp([{"type": "text", "text": "fim"}], "end_turn")
        usd = ledger.add(d["model"], d["usage"])
        return d, usd, 0.01 * n, 0


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.prices = os.path.join(self.dir, "prices.json")
        json.dump(PRICES, open(self.prices, "w"))
        self.contract = os.path.join(self.dir, "contrato.md")
        open(self.contract, "w").write(CONTRACT)
        self.base = os.path.join(self.dir, "retry")

    def tearDown(self):
        self.tmp.cleanup()


class TestAutoretry(Base):
    def test_fail_1_pass_2_com_memoria(self):
        """FAIL na 1ª, PASS na 2ª → tentativas=2 e kickoff da 2ª tem DIAGNÓSTICO PRÉVIO."""
        def script(seed, n):
            if seed == 100:  # tentativa 1: NUNCA entrega (FAIL por max_turns)
                return resp([{"type": "text", "text": "desisto"}], "end_turn")
            return resp([tool_use(1, "Write", {"path": "ok.txt", "content": "ok"})])
        fb = FakeBridge(script)
        agg = autoretry.rodar_com_retry(self.contract, self.base, 1.0, 10,
                                        n_retries=1, seed0=100, bridge_fn=fb)
        self.assertEqual(agg["veredito"], "PASS")
        self.assertEqual(agg["tentativas"], 2)
        self.assertEqual(agg["vereditos_por_tentativa"], ["FAIL", "PASS"])
        kickoff2 = fb.systems[1]
        self.assertIn("DIAGNÓSTICO PRÉVIO", kickoff2)
        self.assertIn("veredito anterior: FAIL", kickoff2)

    def test_pass_na_1_sem_retry(self):
        """PASS na 1ª → tentativas=1, zero re-tentativa, custo só da 1ª."""
        def script(seed, n):
            self.assertEqual(n, 1)
            return resp([tool_use(1, "Write", {"path": "ok.txt", "content": "ok"})])
        fb = FakeBridge(script)
        agg = autoretry.rodar_com_retry(self.contract, self.base, 1.0, 10,
                                        n_retries=2, seed0=100, bridge_fn=fb)
        self.assertEqual(agg["tentativas"], 1)
        self.assertEqual(agg["vereditos_por_tentativa"], ["PASS"])
        self.assertEqual([c for c in fb.calls if c[2]], [(100, 1, True)])
        self.assertGreater(agg["custo_total"], 0)

    def test_retries_0_nunca_re_tenta(self):
        """--retries 0 → paridade: 1 tentativa mesmo com FAIL."""
        fb = FakeBridge(lambda seed, n: resp([{"type": "text", "text": "falho"}], "end_turn"))
        agg = autoretry.rodar_com_retry(self.contract, self.base, 1.0, 10,
                                        n_retries=0, seed0=100, bridge_fn=fb)
        self.assertEqual(agg["tentativas"], 1)
        self.assertEqual(agg["veredito"], "FAIL")
        self.assertEqual([c for c in fb.calls if c[2]], [(100, 1, True)])

    def test_fail_estrutural_para_no_hard_cap(self):
        """FAIL sempre → para em 4 tentativas (1+3), custo ≤ budget+ε."""
        fb = FakeBridge(lambda seed, n: resp([{"type": "text", "text": "falho"}], "end_turn"))
        agg = autoretry.rodar_com_retry(self.contract, self.base, 1.0, 10,
                                        n_retries=10, seed0=100, bridge_fn=fb)
        self.assertEqual(agg["tentativas"], 4)
        self.assertEqual(agg["vereditos_por_tentativa"], ["FAIL"] * 4)
        self.assertLessEqual(agg["custo_total"], 1.0 + 1e-6)
        kickoffs = [c for c in fb.calls if c[2]]
        self.assertEqual(len(kickoffs), 4)
        self.assertEqual([c[0] for c in kickoffs], [100, 101, 102, 103])

    def test_custo_total_soma_exata(self):
        """custo_total = soma exata dos custos das tentativas."""
        fb = FakeBridge(lambda seed, n: resp([{"type": "text", "text": "falho"}], "end_turn"))
        agg = autoretry.rodar_com_retry(self.contract, self.base, 1.0, 10,
                                        n_retries=2, seed0=100, bridge_fn=fb)
        price = PRICES["models"]["z-ai/glm-5.3-flash"]
        por_chamada = (1000 * price["in"] + 200 * price["out"]) / 1e6
        esperado = len(fb.calls) * por_chamada
        self.assertAlmostEqual(agg["custo_total"], esperado, places=8)

    def test_summary_json_em_disco(self):
        """autoretry-summary.json escrito com o agregado completo."""
        fb = FakeBridge(lambda seed, n: resp([{"type": "text", "text": "falho"}], "end_turn"))
        agg = autoretry.rodar_com_retry(self.contract, self.base, 1.0, 10,
                                        n_retries=1, seed0=100, bridge_fn=fb)
        path = os.path.join(self.base, "autoretry-summary.json")
        self.assertTrue(os.path.isfile(path))
        disco = json.load(open(path, encoding="utf-8"))
        self.assertEqual(disco["veredito"], agg["veredito"])
        self.assertEqual(disco["tentativas"], agg["tentativas"])
        self.assertEqual(disco["vereditos_por_tentativa"], agg["vereditos_por_tentativa"])
        self.assertEqual(disco["budget_total"], 1.0)

    def test_budget_esgota_para_antes(self):
        """Budget estourado na 1ª → não há 2ª tentativa (restante ≤ 0)."""
        def script(seed, n):
            return resp([{"type": "text", "text": "caro"}], "end_turn",
                        inp=900_000, out=900_000)  # ~$0.585 por chamada
        fb = FakeBridge(script)
        agg = autoretry.rodar_com_retry(self.contract, self.base, 0.6, 10,
                                        n_retries=3, seed0=100, bridge_fn=fb)
        self.assertEqual(agg["veredito"], "FAIL")
        self.assertLess(agg["tentativas"], 4)


if __name__ == "__main__":
    unittest.main()
