"""Suíte BATCH-PARALELO-01 — batch paralelo, sem rede (bridge falso injetado)."""
import io
import json
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness  # noqa: E402
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import batch  # noqa: E402

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
    """Roteiriza respostas; cobra via ledger compartilhado."""

    def __init__(self, script_fn=None):
        self.script_fn = script_fn or (lambda seed, call: [])
        self.calls = {}

    def __call__(self, messages, system, ledger, model=None):
        import re as _re
        m = _re.search(r"seed desta run: (\d+)", system or "")
        seed = int(m.group(1)) if m else None
        key = id(threading.current_thread())
        n = self.calls.get(key, 0) + 1
        self.calls[key] = n
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
        self.base = os.path.join(self.dir, "batch")

    def tearDown(self):
        self.tmp.cleanup()


class TestBatch(Base):
    def test_3_seeds_pass_em_paralelo(self):
        """3 seeds mockadas PASS em paralelo → agregado {PASS:3}, custo=soma, 3 dirs."""
        def script(seed, n):
            if n == 1:
                return resp([tool_use(1, "Write", {"path": "ok.txt", "content": "ok"})])
            return resp([], "end_turn")
        agg = batch.rodar_batch(self.contract, self.base, 3, 1.0, 10,
                                seed0=100, bridge_fn=FakeBridge(script))
        self.assertEqual(agg["vereditos"], {"PASS": 3, "FAIL": 0})
        self.assertGreater(agg["custo_total"], 0)
        self.assertEqual(len(agg["runs"]), 3)
        dirs = [r["run_dir"] for r in agg["runs"]]
        self.assertEqual(len(set(dirs)), 3)
        for k in (100, 101, 102):
            self.assertTrue(any(f"batch-s{k}" in d for d in dirs), dirs)
        self.assertTrue(os.path.isfile(os.path.join(self.base, "batch-summary.json")))

    def test_budget_excedido_aborta_todas(self):
        """Mock caro → threads param com FAIL budget_excedido; custo ≤ budget+ε."""
        def script(seed, n):
            return resp([{"type": "text", "text": "caro"}], "end_turn",
                        inp=900_000, out=900_000)  # ~$0.585 por chamada
        agg = batch.rodar_batch(self.contract, self.base, 3, 0.6, 10,
                                seed0=200, bridge_fn=FakeBridge(script))
        self.assertEqual(agg["vereditos"]["PASS"], 0)
        self.assertGreater(agg["vereditos"]["FAIL"], 0)
        self.assertLessEqual(agg["custo_total"], 0.6 + 1e-6)
        for r in agg["runs"]:
            if r["veredito"] == "FAIL":
                self.assertEqual(r["motivo"], "budget_excedido")

    def test_stop_flag_aborta_outra_thread(self):
        """Thread A sinaliza stop_flag → nenhuma thread faz 3ª chamada."""
        flag = threading.Event()
        per_thread = {}
        lk = threading.Lock()

        bar = threading.Barrier(2)

        def script(seed, n):
            with lk:
                key = id(threading.current_thread())
                per_thread[key] = per_thread.get(key, 0) + 1
            if n == 1:
                bar.wait(timeout=5.0)  # ambas as threads fizeram a 1ª chamada
                flag.set()  # sinaliza abort
                return resp([tool_use(1, "Write", {"path": "a.txt", "content": "x"})])
            if n >= 2:
                # determinístico: qualquer 2ª+ chamada SÓ é alcançada se o
                # stop_flag ainda não foi visto — espera o flag e falha.
                self.assertTrue(flag.wait(timeout=2.0),
                                "chamada após stop_flag setado")
                raise AssertionError("chamada após stop_flag setado")
            raise AssertionError("inacessível")

        # stop_flag externo injetável — ver HINTS.md da run stopflag-pair-01
        agg = batch.rodar_batch(self.contract, self.base, 2, 10.0, 10,
                                seed0=300, bridge_fn=FakeBridge(script),
                                stop_flag=flag)
        self.assertEqual(agg["vereditos"]["PASS"], 0)
        for k, v in per_thread.items():
            self.assertLessEqual(v, 2, f"thread {k} fez {v} chamadas (stop_flag falhou)")

    def test_ledger_thread_safe_10k(self):
        """2 threads × 10k add() concorrentes → total exato; paridade single-thread."""
        led = harness.Ledger(self.prices)
        usage = {"input_tokens": 1000, "output_tokens": 1000}

        def worker():
            for _ in range(10_000):
                led.add("z-ai/glm-5.3-flash", usage)

        ts = [threading.Thread(target=worker) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(led.in_tok, 20_000_000)
        self.assertEqual(led.out_tok, 20_000_000)
        self.assertEqual(len(led.calls), 20_000)
        self.assertAlmostEqual(led.cost, 20_000 * 0.00065, places=6)
        # paridade single-thread
        led2 = harness.Ledger(self.prices)
        for _ in range(10):
            led2.add("z-ai/glm-5.3-flash", usage)
        self.assertAlmostEqual(led2.cost, 10 * 0.00065, places=10)

    def test_prefixo_painel_por_seed(self):
        """Painel das runs de batch tem linhas com prefixo [s<k>] na 1ª coluna."""
        def script(seed, n):
            if n == 1:
                return resp([tool_use(1, "Write", {"path": "ok.txt", "content": "ok"})])
            return resp([], "end_turn")
        agg = batch.rodar_batch(self.contract, self.base, 2, 1.0, 10,
                                seed0=400, bridge_fn=FakeBridge(script))
        for r in agg["runs"]:
            k = r["seed"]
            pane = os.path.join(r["run_dir"], "harness-pane.log")
            self.assertTrue(os.path.isfile(pane), pane)
            lines = [l for l in open(pane, encoding="utf-8").read().splitlines() if l.strip()]
            self.assertTrue(lines)
            for l in lines:
                self.assertTrue(l.startswith(f"[s{k}] "), f"{l!r} sem prefixo [s{k}]")

    def test_batch_summary_json(self):
        """batch-summary.json contém o agregado completo."""
        def script(seed, n):
            if n == 1:
                return resp([tool_use(1, "Write", {"path": "ok.txt", "content": "ok"})])
            return resp([], "end_turn")
        agg = batch.rodar_batch(self.contract, self.base, 2, 1.0, 10,
                                seed0=500, bridge_fn=FakeBridge(script))
        disk = json.load(open(os.path.join(self.base, "batch-summary.json"), encoding="utf-8"))
        self.assertEqual(disk["vereditos"], agg["vereditos"])
        self.assertEqual(disk["custo_total"], agg["custo_total"])
        self.assertEqual(disk["budget_total"], 1.0)
        self.assertEqual(len(disk["runs"]), 2)

    def test_pane_line_sem_prefixo_paridade(self):
        """_pane_line sem prefixo = snapshot de 1 linha (paridade exata)."""
        rec = {"tool": "_resumo", "veredito": "PASS", "motivo": "stop_condition",
               "turnos": 3, "custo": {"usd": 0.0123}, "budget_usd": 1.0,
               "latencia_ms": {"p50": 100, "p99": 200},
               "stop_conditions_cumpridas": "2/2", "trail": "t.jsonl"}
        sem = harness._pane_line(rec)
        com_none = harness._pane_line(rec, prefix=None)
        self.assertEqual(sem, com_none)
        self.assertTrue(sem.startswith("["))
        self.assertIn("VEREDITO PASS", sem)
        self.assertEqual(len(sem.splitlines()), 1)
        com = harness._pane_line(rec, prefix="[s7]")
        self.assertTrue(com.startswith("[s7] ["))
        self.assertIn("VEREDITO PASS", com)


if __name__ == "__main__":
    unittest.main()
