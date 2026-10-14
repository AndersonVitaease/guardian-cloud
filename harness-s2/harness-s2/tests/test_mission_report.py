# Testes do emissor mission-ops ← harness (HARNESS-SPRINT4-01, item 2)
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mission_report import emitir_run


SUMMARY_PASS = {"veredito": "PASS", "motivo": "stop_condition", "run_dir": "/tmp/run-1",
                "seed": 0, "cum_usd": 0.42, "mission": "X-01",
                "latencia_ms": {"p50": 900, "p99": 2100}, "trail": "/tmp/run-1/harness-trail.jsonl"}
SUMMARY_FAIL = {"veredito": "FAIL", "motivo": "budget_excedido", "run_dir": "/tmp/run-2",
                "seed": 0, "cum_usd": 1.99, "mission": "X-01", "trail": ""}


class TestMissionReport(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.spool = os.path.join(self.d, "spool.jsonl")
        self.sigs = os.path.join(self.d, "sigs.json")

    def _ler_spool(self):
        with open(self.spool, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def test_pass_emite_mission_completed(self):
        ev = emitir_run(SUMMARY_PASS, self.spool, self.sigs)
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["kind"], "mission_completed")
        self.assertEqual(ev[0]["missionId"], "X-01")
        self.assertEqual(ev[0]["source"], "harness-v2")
        self.assertIn("harness PASS", ev[0]["detail"])

    def test_fail_emite_mission_failed_com_motivo(self):
        ev = emitir_run(SUMMARY_FAIL, self.spool, self.sigs)
        self.assertEqual(ev[0]["kind"], "mission_failed")
        self.assertIn("budget_excedido", ev[0]["detail"])

    def test_dedupe_mesma_transicao_nao_reemite(self):
        emitir_run(SUMMARY_PASS, self.spool, self.sigs)
        ev2 = emitir_run(SUMMARY_PASS, self.spool, self.sigs)
        self.assertEqual(ev2, [])
        self.assertEqual(len(self._ler_spool()), 1)

    def test_transicoes_diferentes_emitem(self):
        emitir_run(SUMMARY_PASS, self.spool, self.sigs)
        ev = emitir_run(SUMMARY_FAIL, self.spool, self.sigs)
        self.assertEqual(len(ev), 1)
        self.assertEqual(len(self._ler_spool()), 2)

    def test_spool_ausente_nao_cria_nem_sobe(self):
        ev = emitir_run(SUMMARY_PASS, os.path.join(self.d, "no", "spool.jsonl"), self.sigs)
        self.assertEqual(ev, [])
        self.assertFalse(os.path.exists(os.path.join(self.d, "no")))

    def test_detail_limitado_a_400(self):
        s = dict(SUMMARY_PASS, trail="/tmp/run-1/harness-trail.jsonl")
        ev = emitir_run(s, self.spool, self.sigs)
        self.assertLessEqual(len(ev[0]["detail"]), 400)

    def test_trilha_resumida_no_detail(self):
        trail = os.path.join(self.d, "trail.jsonl")
        with open(trail, "w", encoding="utf-8") as f:
            for i in range(3):
                f.write(json.dumps({"ts": "t", "turno": i, "tool": "Bash",
                                    "latencia_ms": 100 * (i + 1)}) + "\n")
        ev = emitir_run(dict(SUMMARY_PASS, trail=trail), self.spool, self.sigs)
        self.assertIn("turnos=3", ev[0]["detail"])
        self.assertIn("p50=200ms", ev[0]["detail"])

    def test_assinaturas_persistidas(self):
        emitir_run(SUMMARY_PASS, self.spool, self.sigs)
        with open(self.sigs, encoding="utf-8") as f:
            sigs = json.load(f)
        self.assertEqual(sigs, ["mission_completed|X-01|harness:pass"])


if __name__ == "__main__":
    unittest.main()