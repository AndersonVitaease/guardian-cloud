"""ADVISOR-MIDRUN-01 — advisor nativo dentro do loop (sem LLM real)."""
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness  # noqa: E402

PRICES = {"models": {"z-ai/glm-5.3-flash": {"in": 0.15, "out": 0.5, "cache_read": 0.03}}}

# Contrato impossível de cumprir: exige arquivo que o worker nunca escreve.
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


class StallBridge:
    """Worker nunca resolve stop-conditions; advisor devolve hint fixo."""

    def __init__(self):
        self.worker_calls = 0
        self.advisor_calls = 0
        self.advisor_messages = []
        self.worker_messages = []

    def __call__(self, messages, system, ledger, model=None):
        if system == harness.ADVISOR_SYSTEM:
            self.advisor_calls += 1
            self.advisor_messages.append(messages)
            d = resp([{"type": "text", "text": "Escreva o arquivo agora."}], "end_turn")
        else:
            self.worker_calls += 1
            self.worker_messages.append(json.loads(json.dumps(messages)))
            d = resp([tool_use(self.worker_calls, "Bash", {"command": "echo x"})])
        usd = ledger.add(d["model"], d["usage"])
        return d, usd, 0.01, 0


class AdvisorErrorBridge(StallBridge):
    """Advisor sempre falha (bridge error); worker segue emperrado."""

    def __call__(self, messages, system, ledger, model=None):
        if system == harness.ADVISOR_SYSTEM:
            self.advisor_calls += 1
            raise RuntimeError("advisor down")
        return super().__call__(messages, system, ledger, model=model)


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
        return harness.run_mission(self.contract, self.base, 10.0, max_turns, seed=3,
                                   ledger=harness.Ledger(self.prices), bridge_fn=bridge,
                                   log=io.StringIO(), **kw)

    def trail(self, s):
        return [json.loads(l) for l in open(s["trail"], encoding="utf-8")]


class TestAdvisorMidrun(Base):
    def test_hint_injetado_na_janela(self):
        """4º turno sem progresso → hint entra como user com prefixo."""
        fb = StallBridge()
        s = self.go(fb, max_turns=5)
        self.assertEqual(fb.advisor_calls, 2)  # turnos 4 e 5 estagnados
        msgs = fb.advisor_messages[0][0]["content"]
        self.assertIn("STOP-CONDITIONS PENDENTES", msgs)
        self.assertIn("nunca-existe.txt", msgs)
        # hint na janela do worker: mensagem user com prefixo, após o advisor
        achou = any(m["role"] == "user" and any(
            isinstance(b, dict) and b.get("type") == "text"
            and b.get("text", "").startswith("HINT DO ADVISOR (turno ")
            for b in (m["content"] if isinstance(m["content"], list) else
                      [{"type": "text", "text": m["content"]}]))
            for m in fb.worker_messages[-1])
        self.assertTrue(achou, "hint do advisor não apareceu na janela")

    def test_evento_no_trail(self):
        fb = StallBridge()
        s = self.go(fb, max_turns=5)
        evs = [e for e in self.trail(s) if e.get("kind") == "advisor"]
        self.assertEqual(len(evs), 2)  # turnos 4 e 5
        self.assertEqual(evs[0]["tool"], "_advisor")

    def test_desligado_nunca_chama(self):
        """HARNESS_ADVISOR=0 → paridade exata: advisor nunca chamado."""
        fb = StallBridge()
        old = harness.HARNESS_ADVISOR
        harness.HARNESS_ADVISOR = False
        try:
            s = self.go(fb, max_turns=5)
        finally:
            harness.HARNESS_ADVISOR = old
        self.assertEqual(fb.advisor_calls, 0)
        self.assertFalse(any(e.get("kind") == "advisor" for e in self.trail(s)))

    def test_teto_de_2_chamadas(self):
        fb = StallBridge()
        self.go(fb, max_turns=12)
        self.assertEqual(fb.advisor_calls, harness.ADVISOR_MAX_CALLS)

    def test_advisor_falho_run_segue(self):
        """Bridge error do advisor = aviso honesto, run continua até o teto."""
        fb = AdvisorErrorBridge()
        s = self.go(fb, max_turns=12)
        self.assertEqual(fb.advisor_calls, harness.ADVISOR_MAX_CALLS)
        avisos = [e for e in self.trail(s) if e.get("erro") == "advisor_falhou"]
        self.assertEqual(len(avisos), harness.ADVISOR_MAX_CALLS)
        self.assertEqual(s["veredito"], "FAIL")  # run seguiu até max_turns

    def test_custo_soma_no_ledger(self):
        fb = StallBridge()
        s = self.go(fb, max_turns=5)
        # worker (5) + advisor (2) chamadas, todas no MESMO ledger
        self.assertEqual(s["custo"]["calls"], 7)
        self.assertGreater(s["custo"]["usd"], 0.0)

    def test_prompt_do_advisor(self):
        w = harness.Window(raw_window=12)
        w.add(1, [{"type": "text", "text": "passo 1"}],
              [{"id": "tu1", "tool": "Bash", "input": {"command": "echo 1"},
                "content": "1", "is_error": False}])
        conds = [{"kind": "file", "path": "alvo.txt"}]
        p = harness.advisor_prompt(w, {"0:file": False}, conds)
        self.assertIn("tool_result: 1", p)
        self.assertIn("alvo.txt", p)
        self.assertIn("STOP-CONDITIONS PENDENTES", p)
        # truncamento
        w2 = harness.Window(raw_window=12)
        w2.add(1, [{"type": "text", "text": "x" * 3000}],
               [{"id": "t", "tool": "Bash", "input": {}, "content": "y" * 3000,
                 "is_error": False}])
        p2 = harness.advisor_prompt(w2, {"0:file": False}, conds)
        self.assertLess(max(len(l) for l in p2.splitlines()),
                        3000 + len(harness.ADVISOR_SYSTEM) + 200)


if __name__ == "__main__":
    unittest.main()