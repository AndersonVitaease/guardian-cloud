#!/usr/bin/env python3
"""Testes do scanner SEC-SCAN-01."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCANNER = os.path.join(REPO, "scripts", "sec_scan.py")


def run_scan(root):
    out = subprocess.run(["python3", SCANNER, root],
                         capture_output=True, text=True)
    hits = [json.loads(l) for l in out.stdout.splitlines() if l.strip()]
    return out.returncode, hits


class TestSecScan(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        subprocess.run(["git", "init", "-q", self.dir], check=True)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _write(self, name, content):
        p = os.path.join(self.dir, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(content)
        return p

    def _scan(self):
        return run_scan(self.dir)

    def test_exit_zero_sempre(self):
        rc, _ = self._scan()
        self.assertEqual(rc, 0)

    def test_arquivo_limpo_zero_hits(self):
        self._write("ok.py", "x = 1\nprint(x)\n")
        _, hits = self._scan()
        self.assertEqual(hits, [])

    def test_segredo_aws(self):
        self._write("a.py", 'KEY = "AKIAIOSFODNN7EXAMPLE"\n')
        _, hits = self._scan()
        self.assertEqual([h["tipo"] for h in hits], ["aws_key"])

    def test_segredo_private_key(self):
        self._write("k.pem", "-----BEGIN RSA PRIVATE KEY-----\nabc\n")
        _, hits = self._scan()
        self.assertEqual([h["tipo"] for h in hits], ["private_key"])

    def test_segredo_openai(self):
        self._write("b.py", 'k = "sk-abcdefghijklmnopqrstuvwx"\n')
        _, hits = self._scan()
        self.assertEqual([h["tipo"] for h in hits], ["openai_key"])

    def test_segredo_google(self):
        self._write("c.py", 'k = "AIzaSyA1234567890abcdefghijklmnopqrstuv"\n')
        _, hits = self._scan()
        self.assertEqual([h["tipo"] for h in hits], ["google_api_key"])

    def test_segredo_router(self):
        self._write("d.py", 'k = "OR_' + "a" * 40 + '"\n')
        _, hits = self._scan()
        self.assertEqual([h["tipo"] for h in hits], ["router_key"])

    def test_segredo_gsk(self):
        self._write("e.py", 'k = "gsk_abcdefghijklmnopqrst"\n')
        _, hits = self._scan()
        self.assertEqual([h["tipo"] for h in hits], ["gsk_key"])

    def test_segredo_bearer(self):
        self._write("f.py", 'h = "Bearer abcdefghijklmnop1234"\n')
        _, hits = self._scan()
        self.assertEqual([h["tipo"] for h in hits], ["bearer_token"])

    def test_segredo_password_assign(self):
        self._write("g.py", 'password = "supersecret123"\n')
        _, hits = self._scan()
        self.assertEqual([h["tipo"] for h in hits], ["password_assign"])

    def test_segredo_slack_webhook(self):
        self._write("h.py",
                    'u = "https://hooks.slack.com/services/T00/B00/XXXXXXXXXXXX"\n')
        _, hits = self._scan()
        self.assertEqual([h["tipo"] for h in hits], ["slack_webhook"])

    def test_segredo_discord_webhook(self):
        self._write("i.py",
                    'u = "https://discord.com/api/webhooks/12345/abcdefghijklmnop"\n')
        _, hits = self._scan()
        self.assertEqual([h["tipo"] for h in hits], ["discord_webhook"])

    def test_segredo_jwt(self):
        self._write("j.py",
                    't = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.SflKxwRJSMeKKF2QT4f"\n')
        _, hits = self._scan()
        self.assertEqual([h["tipo"] for h in hits], ["jwt_literal"])

    def test_vuln_eval(self):
        self._write("v.py", "eval('1+1')\n")
        _, hits = self._scan()
        self.assertEqual([h["tipo"] for h in hits], ["eval_exec"])

    def test_vuln_shell_true(self):
        self._write("w.py", "subprocess.run('ls', shell=True)\n")
        _, hits = self._scan()
        self.assertEqual([h["tipo"] for h in hits], ["shell_true"])

    def test_vuln_pickle(self):
        self._write("x.py", "import pickle\npickle.load(open('d','rb'))\n")
        _, hits = self._scan()
        self.assertEqual([h["tipo"] for h in hits], ["pickle_load"])

    def test_vuln_os_system(self):
        self._write("y.py", "import os\nos.system('ls')\n")
        _, hits = self._scan()
        self.assertEqual([h["tipo"] for h in hits], ["os_system"])

    def test_vuln_sudo(self):
        self._write("z.py", "subprocess.run('sudo rm -rf /tmp/x')\n")
        _, hits = self._scan()
        self.assertEqual([h["tipo"] for h in hits], ["sudo_use"])

    def test_vuln_sh_unquoted_var(self):
        self._write("s.sh", "rm $ARQUIVO\n")
        _, hits = self._scan()
        self.assertEqual([h["tipo"] for h in hits], ["sh_unquoted_var"])

    def test_falso_positivo_em_tests_ignorado(self):
        self._write("tests/test_fake.py", 'KEY = "AKIAIOSFODNN7EXAMPLE"\n')
        _, hits = self._scan()
        self.assertEqual(hits, [])

    def test_falso_positivo_placeholder_ignorado(self):
        self._write("p.py", 'password = "YOUR_PASSWORD_HERE"\n')
        _, hits = self._scan()
        self.assertEqual(hits, [])

    def test_preview_mascarado(self):
        self._write("m.py", 'KEY = "AKIAIOSFODNN7EXAMPLE"\n')
        _, hits = self._scan()
        self.assertEqual(hits[0]["preview"], "AKIA...")
        self.assertNotIn("IOSFODNN7EXAMPLE", hits[0]["preview"])

    def test_hit_tem_campos(self):
        self._write("n.py", 'KEY = "AKIAIOSFODNN7EXAMPLE"\n')
        _, hits = self._scan()
        h = hits[0]
        self.assertIn("arquivo", h)
        self.assertIn("linha", h)
        self.assertIn("tipo", h)
        self.assertIn("preview", h)


if __name__ == "__main__":
    unittest.main()