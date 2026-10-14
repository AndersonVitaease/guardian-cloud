# RD-TB-CALLER-01: testes do caller de auditoria (TOOLS_CALLER) no tool_bash.
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness  # noqa: E402

captured = {}


def _capture_run(argv, **kwargs):
    class R:
        returncode = 0
        stdout = ""
        stderr = ""
    captured["env"] = kwargs.get("env")
    captured["argv"] = argv
    return R()


class TestTBCaller(unittest.TestCase):

    def setUp(self):
        captured.clear()
        self._old = harness._CALLER_ID
        harness._CALLER_ID = "harness"

    def tearDown(self):
        harness._CALLER_ID = self._old

    def _run_tool_bash(self, catalog):
        with mock.patch.object(harness.subprocess, "run", side_effect=_capture_run):
            harness._tool_bash({"tool": "code_find", "args": "x ."},
                               catalog=catalog)

    def test_default_caller_harness(self):
        """(a) Sem run_mission, o caller é 'harness'."""
        self._run_tool_bash({"code_find": "/bin/true"})
        self.assertEqual(captured["env"].get("TOOLS_CALLER"), "harness")

    def test_caller_com_mission_id(self):
        """(b) Após definir o id da missão, env contém TOOLS_CALLER=harness:<ID>."""
        harness._CALLER_ID = harness._sanitize_caller("harness:RD-TB-CALLER-01")
        self._run_tool_bash({"code_find": "/bin/true"})
        self.assertEqual(captured["env"].get("TOOLS_CALLER"),
                         "harness:RD-TB-CALLER-01")

    def test_saneamento_caller(self):
        """(c) Caracteres fora de [A-Za-z0-9._:-] viram '_'; trunca a 60."""
        self.assertEqual(harness._sanitize_caller("harness:RD TB/CALLER!"),
                         "harness:RD_TB_CALLER_")
        self.assertEqual(len(harness._sanitize_caller("a" * 100)), 60)
        self.assertEqual(harness._sanitize_caller("harness:áé"), "harness:__")
        harness._CALLER_ID = "harness:RD TB/CALLER!"
        self._run_tool_bash({"code_find": "/bin/true"})
        self.assertEqual(captured["env"].get("TOOLS_CALLER"),
                         "harness:RD_TB_CALLER_")

    def test_caminho_redirect_tambem_leva_caller(self):
        """(d) Redirecionamento do Bash: cat -> recusa (nao executa);
        grep -rn -> redireciona para tool_bash com o caller no env."""
        cat = {"code_find": "/bin/true"}
        with mock.patch.object(harness.subprocess, "run", side_effect=_capture_run):
            r = harness._bash_redirect("cat harness.py")
        self.assertEqual(r["kind"], "refuse")
        self.assertEqual(r["error"], "FILE_READ")
        self.assertNotIn("env", captured)
        harness._CALLER_ID = harness._sanitize_caller("harness:RD-TB-CALLER-01")
        with mock.patch.object(harness.subprocess, "run", side_effect=_capture_run):
            v = harness._bash_redirect("grep -rn x .")
        self.assertEqual(v["kind"], "redirect")
        with mock.patch.object(harness.subprocess, "run", side_effect=_capture_run):
            harness._tool_bash({"tool": v["tool"], "args": v["args"]},
                               catalog=cat)
        self.assertEqual(captured["env"].get("TOOLS_CALLER"),
                         "harness:RD-TB-CALLER-01")


if __name__ == "__main__":
    unittest.main()
