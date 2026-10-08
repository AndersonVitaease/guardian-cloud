"""STREAM-ALWAYS-01 — stream deixa de ser exclusivo do --pane.

(a) run sem --pane escolhe call_bridge_stream (on_token escreve no pane-log);
(b) BRIDGE_STREAM=0 → POST antigo (call_bridge_stream NÃO chamado);
(c) BridgeSseError → degrada para POST sem exceção;
(d) handle do pane-log funciona em modo headless (arquivo existe e recebe [tok]).
"""
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness  # noqa: E402
from bridge_sse import BridgeSseError  # noqa: E402

PRICES = {"models": {"z-ai/glm-5.3-flash": {"in": 0.15, "out": 0.5, "cache_read": 0.03}}}

CONTRACT = """# CONTRATO TESTE seed={{SEED}}
```harness-stop
file nunca-existe.txt
```
"""


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
        self.contract = os.path.join(self.dir, "contrato.md")
        open(self.contract, "w").write(CONTRACT)
        self.base = os.path.join(self.dir, "runs")

    def tearDown(self):
        self.tmp.cleanup()

    def go(self, max_turns=2, **kw):
        return harness.run_mission(self.contract, self.base, 10.0, max_turns, seed=3,
                                   ledger=harness.Ledger(self.prices),
                                   log=io.StringIO(), **kw)

    def trail(self, s):
        return [json.loads(l) for l in open(s["trail"], encoding="utf-8")]


class TestStreamAlways(Base):
    def test_a_stream_default_sem_pane(self):
        """Sem --pane: call_bridge_stream é chamado com on_token que escreve [tok]."""
        captured = {}

        def fake_stream(msgs, system, model, ledger, on_token=None, tools=None, **kw):
            captured["on_token"] = on_token
            if on_token:
                on_token("delta de texto ao vivo")
            d = resp([tool_use(1, "Bash", {"command": "echo x"})])
            usd = ledger.add(d["model"], d["usage"])
            return d, usd, 0.01, 0

        with mock.patch.object(harness, "call_bridge_stream", side_effect=fake_stream) as m, \
                mock.patch.object(harness, "call_bridge") as mpost:
            s = self.go()
            self.assertEqual(s["veredito"], "FAIL")  # contrato impossível; só o caminho importa
            m.assert_called()
            self.assertIn("on_token", captured)
            mpost.assert_not_called()
            # (d) headless: pane-log existe e recebeu o delta
            pane = os.path.join(s["run_dir"], "harness-pane.log")
            self.assertTrue(os.path.isfile(pane))
            body = open(pane, encoding="utf-8").read()
            self.assertIn("[tok] delta de texto ao vivo", body)

    def test_b_bridge_stream_0_post_antigo(self):
        """BRIDGE_STREAM=0 → gate da bridge respeitado: POST antigo."""
        os.environ["BRIDGE_STREAM"] = "0"
        try:
            with mock.patch.object(harness, "call_bridge_stream") as m, \
                    mock.patch.object(harness, "call_bridge") as mpost:
                mpost.side_effect = lambda msgs, system, ledger, model=None: (
                    (lambda d: (d, ledger.add(d["model"], d["usage"]), 0.01, 0))(
                        resp([tool_use(1, "Bash", {"command": "echo x"})])))
                s = self.go()
                self.assertEqual(s["veredito"], "FAIL")
                m.assert_not_called()
                mpost.assert_called()
        finally:
            os.environ.pop("BRIDGE_STREAM", None)

    def test_c_bridgesseerror_degrada(self):
        """BridgeSseError → degrada para POST sem derrubar a run."""
        with mock.patch.object(harness, "call_bridge_stream",
                               side_effect=BridgeSseError("stream recusado")), \
                mock.patch.object(harness, "call_bridge") as mpost:
            mpost.side_effect = lambda msgs, system, ledger, model=None: (
                (lambda d: (d, ledger.add(d["model"], d["usage"]), 0.01, 0))(
                    resp([tool_use(1, "Bash", {"command": "echo x"})])))
            s = self.go()
            self.assertEqual(s["veredito"], "FAIL")
            mpost.assert_called()
            evs = [e for e in self.trail(s) if e.get("tool") == "_stream"]
            self.assertTrue(evs and evs[0].get("degradou_para") == "POST")


if __name__ == "__main__":
    unittest.main()
