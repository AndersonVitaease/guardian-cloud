"""Testes opt-in do systemd-run real (RD-TEST-SYSTEMD-01).

Sem TEST_SYSTEMD_REAL=1: todos os testes dão skip (default seguro).
Com TEST_SYSTEMD_REAL=1: exercita systemd-run real via subprocess.

Rodável como script: python3 tests/test_systemd_real.py
Se TEST_SYSTEMD_REAL=1 e tudo PASS, imprime 'SYSTEMD_RUN_REAL_OK'.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

GATE = os.environ.get("TEST_SYSTEMD_REAL") == "1"

# Caminho do despachante, relativo à raiz do repo (tests/ -> ..)
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESPACHANTE = os.path.join(REPO, "scripts", "despachante.py")


@unittest.skipUnless(GATE, "opt-in: defina TEST_SYSTEMD_REAL=1")
class TestSystemdRunReal(unittest.TestCase):
    def test_systemd_run_true(self):
        pid = os.getpid()
        argv = [
            "systemd-run",
            "--unit=harness-probe-%d" % pid,
            "--collect",
            "/bin/true",
        ]
        r = subprocess.run(argv, capture_output=True, text=True, timeout=25)
        if r.returncode != 0 and ("Interactive authentication required" in r.stderr
                                  or "Failed to connect to bus" in r.stderr):
            self.skipTest("systemd-run real indisponivel sem bus/sessao e sem "
                          "sudo passwordless (uid=%d): %s"
                          % (os.getuid(), r.stderr.strip()))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("probe", r.stdout + r.stderr)

    def test_dry_run_default_seguro(self):
        with tempfile.TemporaryDirectory() as td:
            plano = os.path.join(td, "plano.json")
            with open(plano, "w") as f:
                f.write(json.dumps({"politica_fail": "parar", "missoes": [
                    {"id": "probe-dry", "contrato_path": "contratos/probe-dry.md",
                     "cwd": td, "seed": 1, "budget": 1.0, "max_turns": 1,
                     "deps": []}]}))
            r = subprocess.run(
                [sys.executable, DESPACHANTE, "--dry-run", plano],
                capture_output=True,
                text=True,
                timeout=25,
                cwd=REPO,
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("systemd-run", r.stdout)


if __name__ == "__main__":
    result = unittest.main(exit=False).result
    if GATE and result.wasSuccessful():
        print("SYSTEMD_RUN_REAL_OK")
    sys.exit(0 if result.wasSuccessful() else 1)