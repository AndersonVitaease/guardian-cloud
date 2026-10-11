#!/usr/bin/env python3
"""FECHO-CONSISTENTE-01: teste do fechar_mirror.py — idempotencia, closed,
sem regressao, divergencia protegida."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


def _load():
    spec = importlib.util.spec_from_file_location(
        "fechar_mirror",
        "/home/worker/harness-s2/scripts/fechar_mirror.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestFecharMirror(unittest.TestCase):
    def setUp(self):
        self.mod = _load()
        self.tmp = tempfile.mkdtemp(prefix="test-fechar-mirror-")
        self.sd = Path(self.tmp) / "mirror"
        self.mid = "TEST-MIRROR-01"
        self.resumo = Path(self.tmp) / "resumo.json"
        self.resumo.write_text(json.dumps({"veredito": "PASS"}))

    def _mirror(self):
        return json.loads((self.sd / ("%s.json" % self.mid)).read_text())

    def test_mirror_vira_closed_com_verdict(self):
        (self.sd).mkdir(parents=True, exist_ok=True)
        (self.sd / ("%s.json" % self.mid)).write_text(json.dumps(
            {"missionId": self.mid, "status": "failed", "verdict": None}))
        out = self.mod.fechar_mirror(self.mid, str(self.resumo),
                                     state_dir=str(self.sd))
        self.assertTrue(out["ok"])
        m = self._mirror()
        self.assertEqual(m["status"], "closed")
        self.assertEqual(m["verdict"], "PASS")
        self.assertEqual(m["veredito"], "PASS")

    def test_fecho_idempotente_nao_muda_nada(self):
        (self.sd).mkdir(parents=True, exist_ok=True)
        (self.sd / ("%s.json" % self.mid)).write_text(json.dumps(
            {"missionId": self.mid, "status": "closed", "verdict": "PASS",
             "closedAt": "2026-01-01T00:00:00Z"}))
        out = self.mod.fechar_mirror(self.mid, str(self.resumo),
                                     state_dir=str(self.sd))
        self.assertTrue(out["ok"])
        self.assertEqual(out["acao"], "idempotente")
        m = self._mirror()
        self.assertEqual(m["closedAt"], "2026-01-01T00:00:00Z")
        self.assertEqual(m["status"], "closed")
        self.assertEqual(m["verdict"], "PASS")

    def test_nao_regredir_de_closed(self):
        # resumo sem verdict chamado sobre mirror closed PASS: permanece closed
        (self.sd).mkdir(parents=True, exist_ok=True)
        (self.sd / ("%s.json" % self.mid)).write_text(json.dumps(
            {"missionId": self.mid, "status": "closed", "verdict": "PASS"}))
        resumo_vazio = Path(self.tmp) / "vazio.json"
        resumo_vazio.write_text("{}")
        out = self.mod.fechar_mirror(self.mid, str(resumo_vazio),
                                     state_dir=str(self.sd))
        self.assertTrue(out["ok"])
        m = self._mirror()
        self.assertEqual(m["status"], "closed")
        self.assertEqual(m["verdict"], "PASS")

    def test_verdict_divergente_nao_sobrescreve(self):
        (self.sd).mkdir(parents=True, exist_ok=True)
        (self.sd / ("%s.json" % self.mid)).write_text(json.dumps(
            {"missionId": self.mid, "status": "closed", "verdict": "PASS"}))
        resumo_fail = Path(self.tmp) / "fail.json"
        resumo_fail.write_text(json.dumps({"veredito": "FAIL"}))
        out = self.mod.fechar_mirror(self.mid, str(resumo_fail),
                                     state_dir=str(self.sd))
        self.assertFalse(out["ok"])
        self.assertEqual(out["acao"], "divergente")
        m = self._mirror()
        self.assertEqual(m["verdict"], "PASS")

    def test_mirror_ausente_cria_closed(self):
        out = self.mod.fechar_mirror(self.mid, str(self.resumo),
                                     state_dir=str(self.sd))
        self.assertTrue(out["ok"])
        self.assertTrue(out["criado"])
        m = self._mirror()
        self.assertEqual(m["status"], "closed")
        self.assertEqual(m["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main(verbosity=2)
