"""HARNESS-CLOSE-01 — fase de fecho determinística (sem LLM real)."""
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness  # noqa: E402

PRICES = {"models": {"z-ai/glm-5.3-flash": {"in": 0.15, "out": 0.5, "cache_read": 0.03}}}

CLOSE_PROMPT = ("FASE DE FECHO: rode os stops de fecho pendentes, commit os "
                "arquivos da missão com o ID no assunto, rode a suíte, mostre git log -1")


def tool_use(i, name, inp):
    return {"type": "tool_use", "id": f"tu{i}", "name": name, "input": inp}


def resp(content, stop="tool_use", inp=1000, out=200):
    return {"model": "z-ai/glm-5.3-flash", "content": content, "stop_reason": stop,
            "usage": {"input_tokens": inp, "output_tokens": out}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.prices = os.path.join(self.dir, "prices.json")
        json.dump(PRICES, open(self.prices, "w"))
        self.base = os.path.join(self.dir, "runs")
        self.close = mock.patch.object(harness, "HARNESS_CLOSE", True)
        self.close.start()
        self.addCleanup(self.close.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def contract(self, body):
        p = os.path.join(self.dir, "contrato.md")
        open(p, "w").write(body)
        return p

    def go(self, bridge, contract, max_turns=12, **kw):
        return harness.run_mission(contract, self.base, 10.0, max_turns, seed=3,
                                   ledger=harness.Ledger(self.prices), bridge_fn=bridge,
                                   log=io.StringIO(), vagueio=False, **kw)

    def trail(self, s):
        return [json.loads(l) for l in open(s["trail"], encoding="utf-8")]


class IdleBridge:
    """Worker só faz echo — nunca cumpre nada."""

    def __init__(self):
        self.calls = 0
        self.messages = []

    def __call__(self, messages, system, ledger, model=None):
        self.calls += 1
        self.messages.append(json.loads(json.dumps(messages)))
        d = resp([tool_use(self.calls, "Bash", {"command": "echo x"})])
        usd = ledger.add(d["model"], d["usage"])
        return d, usd, 0.01, 0


class TestParseClose(Base):
    def test_parse_close_conditions(self):
        c = self.contract("# M\n```harness-close\ncmd true\nfile a.txt\n```\n")
        conds = harness.parse_close_conditions(open(c).read())
        self.assertEqual(conds, [{"kind": "cmd", "cmd": "true"},
                                 {"kind": "file", "path": "a.txt"}])

    def test_sem_bloco(self):
        c = self.contract("# M\n```harness-stop\ncmd true\n```\n")
        self.assertEqual(harness.parse_close_conditions(open(c).read()), [])


class TestClose(Base):
    def test_reprompt_e_fail_honesto(self):
        """Stops verdes + close vermelho → 3 ciclos de reprompt, depois FAIL."""
        ct = ("# MISSÃO X\n```harness-stop\ncmd true\n```\n"
              "```harness-close\ncmd false\n```\n")
        fb = IdleBridge()
        s = self.go(fb, self.contract(ct), max_turns=10)
        self.assertEqual(s["veredito"], "FAIL")
        self.assertEqual(s["motivo"], "fecho_incompleto")
        evs = [e for e in self.trail(s) if e.get("tool") == "_close_reprompt"]
        self.assertEqual(len(evs), 3)
        self.assertEqual(s["close_ciclos"], 3)
        self.assertFalse(s["close_state"]["0:cmd"])
        # prompt de fecho injetado na janela
        achou = any(any(isinstance(b, dict) and b.get("type") == "text"
                        and CLOSE_PROMPT in b.get("text", "")
                        for b in m.get("content", []))
                    for m in fb.messages[-1])
        self.assertTrue(achou, "prompt de fecho não injetado")

    def test_close_verde_pass(self):
        ct = ("# MISSÃO X\n```harness-stop\ncmd true\n```\n"
              "```harness-close\ncmd true\n```\n")
        s = self.go(IdleBridge(), self.contract(ct), max_turns=6)
        self.assertEqual(s["veredito"], "PASS")
        self.assertEqual(s["motivo"], "stop_condition")
        self.assertTrue(s["close_state"]["0:cmd"])
        self.assertEqual(s["close_ciclos"], 0)

    def test_sem_bloco_close_comportamento_inalterado(self):
        ct = "# MISSÃO X\n```harness-stop\ncmd true\n```\n"
        s = self.go(IdleBridge(), self.contract(ct), max_turns=6)
        self.assertEqual(s["veredito"], "PASS")
        self.assertEqual(s["motivo"], "stop_condition")
        self.assertNotIn("close_state", s)

    def test_rollback_desliga(self):
        self.close.stop()
        with mock.patch.object(harness, "HARNESS_CLOSE", False):
            ct = ("# MISSÃO X\n```harness-stop\ncmd true\n```\n"
                  "```harness-close\ncmd false\n```\n")
            s = self.go(IdleBridge(), self.contract(ct), max_turns=6)
        self.assertEqual(s["veredito"], "PASS")
        self.assertEqual(s["motivo"], "stop_condition")

    def test_fail_incompleto_estado_git_no_summary(self):
        ct = ("# MISSÃO X\n```harness-stop\ncmd true\n```\n"
              "```harness-close\ncmd false\n```\n")
        s = self.go(IdleBridge(), self.contract(ct), max_turns=10)
        self.assertIn("git_status", json.dumps(s.get("recomendacao") or {}))


if __name__ == "__main__":
    unittest.main()
