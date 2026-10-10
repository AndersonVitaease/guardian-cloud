import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from contrato_lint import lint  # noqa: E402


def codigos(texto):
    return [a["codigo"] for a in lint(texto)]


BASE_OK = """# MISSÃO RD-X-01 — exemplo

## MAPA
- a.py:10 função

```harness-stop
cmd cd /tmp && test -f a.py
```
"""


class TestFenceErrada(unittest.TestCase):
    def test_positivo(self):
        t = "# MISSÃO RD-X-01\n\n```h harness-stop\ncmd cd /tmp && true\n```\n"
        self.assertIn("FENCE_ERRADA", codigos(t))

    def test_negativo(self):
        self.assertNotIn("FENCE_ERRADA", codigos(BASE_OK))


class TestStopPathInexistente(unittest.TestCase):
    def test_positivo(self):
        t = "# MISSÃO RD-X-01\n\n```harness-stop\ncmd cd /caminho/que/nao/existe-xyz && test -f a.py\n```\n"
        self.assertIn("STOP_PATH_INEXISTENTE", codigos(t))

    def test_negativo(self):
        t = "# MISSÃO RD-X-01\n\n```harness-stop\ncmd cd /tmp && test -f a.py\n```\n"
        self.assertNotIn("STOP_PATH_INEXISTENTE", codigos(t))


class TestStopSoTrivial(unittest.TestCase):
    def test_positivo(self):
        t = "# MISSÃO RD-X-01\n\n```harness-stop\ncmd cd /tmp && test -f a.py\ncmd cd /tmp && echo ok\n```\n"
        self.assertIn("STOP_SO_TRIVIAL", codigos(t))

    def test_negativo(self):
        t = "# MISSÃO RD-X-01\n\n```harness-stop\ncmd cd /tmp && python3 prova.py\n```\n"
        self.assertNotIn("STOP_SO_TRIVIAL", codigos(t))


class TestSemMapa(unittest.TestCase):
    def test_positivo(self):
        t = ("# MISSÃO RD-X-01\nEdite a.js, b.mjs e c.py para corrigir o bug.\n\n"
             "```harness-stop\ncmd cd /tmp && python3 prova.py\n```\n")
        self.assertIn("SEM_MAPA", codigos(t))

    def test_negativo(self):
        t = ("# MISSÃO RD-X-01\n## MAPA\n- a.js:10 função\n\n"
             "```harness-stop\ncmd cd /tmp && python3 prova.py\n```\n")
        self.assertNotIn("SEM_MAPA", codigos(t))


class TestIdDivergente(unittest.TestCase):
    def test_positivo(self):
        t = ("# MISSÃO RD-X-01\n\n```harness-stop\ncmd cd /tmp && test -f RELATORIO-RD-Y-02.md\n```\n")
        self.assertIn("ID_DIVERGENTE", codigos(t))

    def test_negativo(self):
        t = ("# MISSÃO RD-X-01\n\n```harness-stop\ncmd cd /tmp && test -f RELATORIO-RD-X-01.md\n```\n")
        self.assertNotIn("ID_DIVERGENTE", codigos(t))


class TestProvaSemIsolamento(unittest.TestCase):
    def test_positivo(self):
        t = "# MISSÃO RD-X-01\n\n```harness-stop\ncmd cd /tmp && python3 prova-x.py\n```\n"
        self.assertIn("PROVA_SEM_ISOLAMENTO", codigos(t))

    def test_negativo(self):
        t = ("# MISSÃO RD-X-01\nUse mktemp para o banco.\n\n"
             "```harness-stop\ncmd cd /tmp && python3 prova-x.py\n```\n")
        self.assertNotIn("PROVA_SEM_ISOLAMENTO", codigos(t))


class TestRootPathRefinado(unittest.TestCase):
    def test_escrita_erro(self):
        t = "# MISSÃO RD-X-01\nEscreva o log em /opt/dados/log.txt\n"
        self.assertIn("PROIBIDO_ROOT_PATH", codigos(t))

    def test_leitura_aviso(self):
        t = "# MISSÃO RD-X-01\nLeia o contrato em /opt/mission-events/x.md\n"
        cs = codigos(t)
        self.assertIn("LEITURA_ROOT_PATH", cs)
        self.assertNotIn("PROIBIDO_ROOT_PATH", cs)


if __name__ == "__main__":
    unittest.main()