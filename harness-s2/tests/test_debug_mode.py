"""DEBUGMODE-INFRA-02: presets --modo + memória entre runs (--memoria)."""
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mission_run  # noqa: E402
import harness  # noqa: E402


class TestPresets(unittest.TestCase):
    def test_preset_debug(self):
        p = mission_run.PRESETS["debug"]
        self.assertEqual((p["raw_window"], p["max_summary"], p["max_tool_chars"]),
                         (40, 120, 12000))

    def test_preset_normal_paridade(self):
        p = mission_run.PRESETS["normal"]
        self.assertEqual((p["raw_window"], p["max_summary"], p["max_tool_chars"]),
                         (harness.RAW_WINDOW, harness.MAX_SUMMARY_LINES,
                          harness.MAX_TOOL_CHARS))
        self.assertEqual((p["raw_window"], p["max_summary"], p["max_tool_chars"]),
                         (12, 60, 4000))

    def _run_main(self, d, extra):
        missao = os.path.join(d, "missao-x.md")
        open(missao, "w").write("# missao-x\n```harness-stop\nfile ok.txt\n```\n")
        with mock.patch.object(mission_run, "run_mission",
                               return_value={"veredito": "PASS"}) as rm, \
             mock.patch.object(mission_run, "emitir_run"):
            mission_run.main(["--mission", missao, "--cwd", d] + extra)
        return rm.call_args.kwargs

    def test_main_aplica_preset_debug(self):
        with tempfile.TemporaryDirectory() as d:
            kw = self._run_main(d, ["--modo", "debug"])
            self.assertEqual((kw["raw_window"], kw["max_summary"],
                              kw["max_tool_chars"]), (40, 120, 12000))

    def test_main_default_normal(self):
        with tempfile.TemporaryDirectory() as d:
            kw = self._run_main(d, [])
            self.assertEqual((kw["raw_window"], kw["max_summary"],
                              kw["max_tool_chars"]), (12, 60, 4000))


def _fabricar_trail(path):
    recs = [
        {"ts": "t1", "turno": 1, "tool": "Bash",
         "result": "exit=1\nERRO: PermissionError: caminho fora do cwd"},
        {"ts": "t2", "turno": 2, "tool": "Bash",
         "result": "exit=0\n3 passed"},
        {"ts": "t3", "tool": "_resumo", "veredito": "FAIL", "motivo": "max_turns",
         "stop_conditions_cumpridas": "1/2",
         "stop_conditions": [{"kind": "file", "path": "a.txt", "ok": True},
                             {"kind": "cmd", "cmd": "pytest", "ok": False}]},
    ]
    with open(path, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


class TestMemoria(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.trail = os.path.join(self.tmp.name, "trail.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def _kickoff(self, argv_extra=()):
        missao = os.path.join(self.tmp.name, "missao-x.md")
        open(missao, "w").write("# missao-x\n```harness-stop\nfile ok.txt\n```\n")
        with mock.patch.object(mission_run, "run_mission",
                               return_value={"veredito": "PASS"}) as rm, \
             mock.patch.object(mission_run, "emitir_run"):
            mission_run.main(["--mission", missao, "--cwd", self.tmp.name,
                              "--memoria", self.trail] + list(argv_extra))
        return rm.call_args.kwargs["contract_prefix"]

    def test_trail_fabricado(self):
        _fabricar_trail(self.trail)
        prefix = self._kickoff()
        self.assertIn("## DIAGNÓSTICO PRÉVIO (run anterior)", prefix)
        self.assertIn("veredito anterior: FAIL", prefix)
        self.assertIn("motivo: max_turns", prefix)
        self.assertIn("3 passed", prefix)
        self.assertIn("PermissionError", prefix)

    def test_trail_corrompido_avisa_e_segue(self):
        open(self.trail, "w").write("{json quebrado\n")
        err = io.StringIO()
        with mock.patch.object(sys, "stderr", err):
            prefix = self._kickoff()
        self.assertEqual(prefix, "")
        self.assertIn("aviso", err.getvalue())

    def test_trail_ausente_avisa_e_segue(self):
        err = io.StringIO()
        with mock.patch.object(sys, "stderr", err):
            prefix = self._kickoff()
        self.assertEqual(prefix, "")
        self.assertIn("aviso", err.getvalue())

    def test_contrato_em_disco_intacto(self):
        missao = os.path.join(self.tmp.name, "missao-x.md")
        conteudo = "# missao-x\n```harness-stop\nfile ok.txt\n```\n"
        open(missao, "w").write(conteudo)
        _fabricar_trail(self.trail)
        with mock.patch.object(mission_run, "run_mission",
                               return_value={"veredito": "PASS"}), \
             mock.patch.object(mission_run, "emitir_run"):
            mission_run.main(["--mission", missao, "--cwd", self.tmp.name,
                              "--memoria", self.trail])
        self.assertEqual(open(missao, encoding="utf-8").read(), conteudo)


if __name__ == "__main__":
    unittest.main()
