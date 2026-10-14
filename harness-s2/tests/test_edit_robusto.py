"""RD-HARNESS-EDIT-ROBUSTO-01: Edit tolerante a indentação + dica difflib + loop de recusa."""
import os
import tempfile
import unittest

import harness as h


class TestEditRobusto(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def _write(self, name, content):
        with open(os.path.join(self.d, name), "w") as f:
            f.write(content)

    def _read(self, name):
        with open(os.path.join(self.d, name)) as f:
            return f.read()

    def test_edit_exato_inalterado(self):
        self._write("a.py", "def f():\n    x = 1\n    return x\n")
        r = h.run_tool("Edit", {"path": "a.py", "old_string": "x = 1",
                                "new_string": "x = 2"}, self.d)
        self.assertTrue(r.startswith("OK edited"), r)
        self.assertIn("    x = 2\n", self._read("a.py"))

    def test_casa_ignorando_indentacao_e_reindenta(self):
        self._write("a.py", "def f():\n    x = 1\n    y = 2\n    return x\n")
        r = h.run_tool("Edit", {"path": "a.py",
                                "old_string": "x = 1\n y = 2",
                                "new_string": "x = 10\ny = 20"}, self.d)
        self.assertTrue(r.startswith("OK edited"), r)
        self.assertIn("casou ignorando indentação", r)
        self.assertIn("    x = 10\n    y = 20\n", self._read("a.py"))
        self.assertIn("return x", self._read("a.py"))

    def test_ambiguo_erro(self):
        self._write("a.py", "x = 1\ny = 2\nx = 1\ny = 2\n")
        r = h.run_tool("Edit", {"path": "a.py",
                                "old_string": "  x = 1\n  y = 2",
                                "new_string": "z"}, self.d)
        self.assertTrue(r.startswith("ERRO: old_string ambíguo"), r)
        self.assertIn("2 ocorrências", r)

    def test_sem_casamento_dica_parecida(self):
        self._write("a.py", "def f():\n    x = 1\n    return x\n")
        r = h.run_tool("Edit", {"path": "a.py", "old_string": "return xx",
                                "new_string": "z"}, self.d)
        self.assertTrue(r.startswith("ERRO: old_string não encontrado"), r)
        self.assertIn("Trecho mais parecido", r)
        self.assertIn("return x", r)

    def test_loop_recusa_repetido(self):
        h.HARNESS_TOOLBASH = True
        h.HARNESS_TOOLBASH_ENFORCE = True
        c = {"command": "cat /etc/hostname"}
        r1 = h.run_tool("Bash", c, self.d)
        self.assertIn("LEITURA_MECANICA_RECUSADA", r1)
        self.assertNotIn("REPETIDO", r1)
        r2 = h.run_tool("Bash", c, self.d)
        self.assertIn("REPETIDO 2x", r2)
        r3 = h.run_tool("Bash", {"command": "echo oi"}, self.d)
        self.assertNotIn("REPETIDO", r3)


if __name__ == "__main__":
    unittest.main()
