"""Pane legível (fix 07/10): o harness emite harness-pane.log com 1 linha
PTBR/BRT por evento, e o pane do herdr segue ESSE log (não o JSONL cru).

Cobre o formato de cada tipo de evento + a existência do arquivo na run.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness  # noqa: E402


class PaneLineTest(unittest.TestCase):
    def test_inicio(self):
        ln = harness._pane_line({"tool": "_inicio", "seed": 8, "model": "z-ai/glm-5.3-flash",
                                 "budget_usd": 0.2, "max_turns": 60,
                                 "stop_conditions_declaradas": [{}, {}, {}, {}]})
        self.assertIn("INÍCIO", ln)
        self.assertIn("seed=8", ln)
        self.assertIn("stop_conditions=4", ln)
        self.assertIn("BRT", ln)
        self.assertNotIn("{", ln)  # nunca JSON cru

    def test_llm(self):
        ln = harness._pane_line({"tool": "llm", "turno": 1, "latencia_ms": 893,
                                "custo_usd": 0.000202, "cum_usd": 0.000202,
                                "stop_reason": "tool_use", "retries": 0,
                                "msgs_janela": 1})
        self.assertIn("turno 1", ln)
        self.assertIn("893ms", ln)
        self.assertIn("stop=tool_use", ln)

    def test_llm_erro(self):
        ln = harness._pane_line({"tool": "llm", "turno": 2, "erro": "boom 502",
                                 "tentativas": 3})
        self.assertIn("ERRO", ln)
        self.assertIn("boom 502", ln)

    def test_tool_worker(self):
        ln = harness._pane_line({"tool": "Bash", "turno": 1, "latencia_ms": 6,
                                "custo_usd": 0.0, "is_error": False,
                                "input": "grep -n _RE_BUDGET adaptador.py"})
        self.assertIn("| Bash |", ln)
        self.assertIn("| ok |", ln)
        self.assertIn("grep -n _RE_BUDGET", ln)

    def test_tool_worker_trunca_input_longo(self):
        ln = harness._pane_line({"tool": "Bash", "turno": 1, "latencia_ms": 6,
                                "custo_usd": 0.0, "is_error": True,
                                "input": "x" * 500})
        self.assertLessEqual(len(ln), 140)
        self.assertIn("ERRO", ln)

    def test_stop_check(self):
        ln = harness._pane_line({"tool": "_stop_check", "turno": 1,
                                 "stop_state": {"0:cmd": True, "1:marker": False},
                                 "todas": False})
        self.assertIn("1/2", ln)
        self.assertIn("pendentes: 1:marker", ln)

    def test_stop_check_todas(self):
        ln = harness._pane_line({"tool": "_stop_check", "turno": 1,
                                 "stop_state": {"0:cmd": True}, "todas": True})
        self.assertIn("TODAS", ln)

    def test_resumo_veredito(self):
        ln = harness._pane_line({"tool": "_resumo", "veredito": "PASS",
                                 "motivo": "stop_condition", "turnos": 1,
                                 "custo": {"usd": 0.000202}, "budget_usd": 0.2,
                                 "latencia_ms": {"p50": 893},
                                 "stop_conditions_cumpridas": "4/4",
                                 "trail": "/tmp/run-1/harness-trail.jsonl"})
        self.assertIn("VEREDITO PASS", ln)
        self.assertIn("4/4", ln)
        self.assertIn("1 turno(s)", ln)


if __name__ == "__main__":
    unittest.main()
