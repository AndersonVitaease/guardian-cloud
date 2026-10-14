"""Testes para scripts/pane_status.py (usando tmp dirs)."""
import os
import sys
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import pane_status  # noqa: E402


class TestPaneStatus(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _criar_run(self, nome, linhas):
        run_dir = os.path.join(self.base, nome)
        os.makedirs(run_dir, exist_ok=True)
        with open(os.path.join(run_dir, "harness-pane.log"), "w", encoding="utf-8") as f:
            f.write("\n".join(linhas) + "\n")
        return run_dir

    def test_veredito_pass(self):
        run_dir = self._criar_run("run-20260101-000000", [
            "INICIO missao x",
            "VEREDITO PASS | testes verdes",
        ])
        msg, code = pane_status.status_do_pane(run_dir)
        self.assertEqual(code, 0)
        self.assertTrue(msg.startswith("VEREDITO PASS"))
        self.assertIn("testes verdes", msg)

    def test_em_andamento(self):
        run_dir = self._criar_run("run-20260102-000000", [
            "INICIO missao y",
            "EVENTO passo 3 executado",
        ])
        msg, code = pane_status.status_do_pane(run_dir)
        self.assertEqual(code, 0)
        self.assertTrue(msg.startswith("EM ANDAMENTO"))
        self.assertIn("passo 3 executado", msg)

    def test_sem_pane_log(self):
        run_dir = os.path.join(self.base, "run-vazio")
        os.makedirs(run_dir, exist_ok=True)
        msg, code = pane_status.status_do_pane(run_dir)
        self.assertEqual(code, 1)
        self.assertIn("SEM PANE LOG", msg)

    def test_cli_exit_codes(self):
        run_ok = self._criar_run("run-20260103-000000", ["VEREDITO FAIL | algo falhou"])
        with patch("sys.stdout", new=StringIO()) as out:
            code = pane_status.main([run_ok])
        self.assertEqual(code, 0)
        self.assertIn("VEREDITO FAIL", out.getvalue())
        run_vazio = os.path.join(self.base, "run-nada")
        os.makedirs(run_vazio, exist_ok=True)
        with patch("sys.stdout", new=StringIO()) as out:
            code = pane_status.main([run_vazio])
        self.assertEqual(code, 1)
        self.assertIn("SEM PANE LOG", out.getvalue())


if __name__ == "__main__":
    unittest.main()
