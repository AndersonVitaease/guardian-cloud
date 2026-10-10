"""RD-HARN-DEBUGINFRA-01: --modo debug + --memoria trail no harness.py (CLI direto)."""
import io
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness  # noqa: E402

PRICES = {"models": {"z-ai/glm-5.3-flash": {"in": 0.15, "out": 0.5, "cache_read": 0.03}}}

CONTRACT = """# CONTRATO TESTE seed={{SEED}}
```harness-stop
file ok.txt
```
"""


def tool_use(i, name, inp):
    return {"type": "tool_use", "id": f"tu{i}", "name": name, "input": inp}


def resp(content, stop="tool_use", inp=1000, out=200):
    return {"model": "z-ai/glm-5.3-flash", "content": content, "stop_reason": stop,
            "usage": {"input_tokens": inp, "output_tokens": out}}


class FakeBridge:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def __call__(self, messages, system, ledger, model=None):
        self.calls.append({"messages": json.loads(json.dumps(messages)), "system": system})
        d = self.script.pop(0) if self.script else resp([{"type": "text", "text": "fim"}], "end_turn")
        usd = ledger.add(d["model"], d["usage"])
        return d, usd, 0.01 * len(self.calls), 0


FIM = [resp([{"type": "text", "text": "relatório final"}], "end_turn")]


def _fabricar_trail(path):
    recs = [
        {"ts": "t1", "turno": 1, "tool": "Bash",
         "result": "exit=1\nERRO: PermissionError: caminho fora do cwd"},
        {"ts": "t2", "turno": 2, "tool": "Bash", "result": "exit=0\n3 passed"},
        {"ts": "t3", "tool": "_resumo", "veredito": "FAIL", "motivo": "max_turns",
         "stop_conditions_cumpridas": "1/2",
         "stop_conditions": [{"kind": "file", "path": "a.txt", "ok": True},
                             {"kind": "cmd", "cmd": "pytest", "ok": False}]},
    ]
    with open(path, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.prices = os.path.join(self.dir, "prices.json")
        json.dump(PRICES, open(self.prices, "w"))
        self.contract = os.path.join(self.dir, "contrato.md")
        open(self.contract, "w").write(CONTRACT)
        self.base = os.path.join(self.dir, "runs")
        self._env = os.environ.pop("HARNESS_MODO_DEBUG", None)

    def tearDown(self):
        if self._env is not None:
            os.environ["HARNESS_MODO_DEBUG"] = self._env
        self.tmp.cleanup()

    def run_with(self, script, budget=1.0, max_turns=6, seed=7, **kw):
        fb = FakeBridge(script)
        s = harness.run_mission(self.contract, self.base, budget, max_turns, seed=seed,
                                 ledger=harness.Ledger(self.prices), bridge_fn=fb,
                                 log=io.StringIO(), vagueio=False, **kw)
        return s, fb

    def _main(self, extra):
        with mock.patch.object(harness, "run_mission",
                               return_value={"veredito": "PASS", "run_dir": self.dir}) as rm:
            rc = harness.main(["--contract", self.contract, "--cwd", self.base] + extra)
        return rc, (rm.call_args.kwargs if rm.call_args else None)


class TestModoDebug(Base):
    def test_debug_alarga_parametros(self):
        rw, ms, mtc = harness.aplicar_modo_debug("debug", 12, 60, 4000)
        self.assertEqual((rw, ms, mtc), (40, 120, 12000))

    def test_modo_normal_nao_muda(self):
        rw, ms, mtc = harness.aplicar_modo_debug("normal", 12, 60, 4000)
        self.assertEqual((rw, ms, mtc), (12, 60, 4000))

    def test_rollback_env_desliga_debug(self):
        os.environ["HARNESS_MODO_DEBUG"] = "0"
        rw, ms, mtc = harness.aplicar_modo_debug("debug", 12, 60, 4000)
        self.assertEqual((rw, ms, mtc), (12, 60, 4000))

    def test_main_modo_debug_flui_para_run_mission(self):
        rc, kw = self._main(["--modo", "debug"])
        self.assertEqual((kw["raw_window"], kw["max_summary"], kw["max_tool_chars"]),
                         (40, 120, 12000))
        self.assertEqual(kw["modo"], "debug")


class TestMemoriaTrail(Base):
    def test_memoria_injeta_diagnostico_previo_no_kickoff(self):
        trail = os.path.join(self.dir, "harness-trail.jsonl")
        _fabricar_trail(trail)
        s, fb = self.run_with(FIM, memoria_trail=trail)
        self.assertIn("DIAGNOSTICO PREVIO", fb.calls[0]["system"])
        self.assertIn("PENDENTE", fb.calls[0]["system"])

    def test_memoria_ausente_ignorada_sem_quebrar(self):
        s, fb = self.run_with(FIM, memoria_trail=os.path.join(self.dir, "nao-existe.jsonl"))
        self.assertNotIn("DIAGNOSTICO PREVIO", fb.calls[0]["system"])

    def test_main_memoria_inexistente_erro_claro(self):
        rc, kw = self._main(["--memoria", os.path.join(self.dir, "nao-existe.jsonl")])
        self.assertEqual(rc, 2)
        self.assertIsNone(kw)  # run_mission nem foi chamado

    def test_main_memoria_valida_passa_caminho(self):
        trail = os.path.join(self.dir, "harness-trail.jsonl")
        _fabricar_trail(trail)
        rc, kw = self._main(["--memoria", trail])
        self.assertEqual(rc, 0)
        self.assertEqual(kw["memoria_trail"], trail)


class TestCombinado(Base):
    def test_stop_flag_debug_e_memoria_coexistem(self):
        trail = os.path.join(self.dir, "harness-trail.jsonl")
        _fabricar_trail(trail)
        stop = threading.Event()
        s, fb = self.run_with(FIM, memoria_trail=trail, stop_flag=stop,
                              raw_window=40, max_summary=120, max_tool_chars=12000)
        self.assertIn("DIAGNOSTICO PREVIO", fb.calls[0]["system"])
        self.assertFalse(stop.is_set())  # run terminou sem stop externo
        self.assertEqual(s["veredito"], "FAIL")  # contrato não cumprido, mas sem crash


if __name__ == "__main__":
    unittest.main()