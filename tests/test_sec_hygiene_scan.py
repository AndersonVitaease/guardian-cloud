"""Testes do scanner SEC-HYGIENE-ROOT-01 (fixtures isolados, read-only no host)."""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from scripts import sec_hygiene_scan as scan  # noqa: E402


class TestCaddyfile(unittest.TestCase):
    def test_key_line_detected(self):
        with tempfile.NamedTemporaryFile("w", suffix=".caddy", delete=False) as f:
            f.write("example.com {\n  header Authorization \"secret_ABCDEFGH12345678\"\n}\n")
            p = f.name
        try:
            out = scan.scan_caddyfile(p)
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["kind"], "caddy-key-literal")
            self.assertEqual(out[0]["line"], 2)
            self.assertTrue(out[0]["token_masked"].startswith("secret_A"))
        finally:
            os.unlink(p)

    def test_clean_file_no_findings(self):
        with tempfile.NamedTemporaryFile("w", suffix=".caddy", delete=False) as f:
            f.write("example.com {\n  reverse_proxy localhost:8080\n}\n")
            p = f.name
        try:
            self.assertEqual(scan.scan_caddyfile(p), [])
        finally:
            os.unlink(p)


class TestProcArgv(unittest.TestCase):
    def _fake_proc(self, cmdline_bytes):
        d = tempfile.mkdtemp()
        pid = os.path.join(d, "4242")
        os.mkdir(pid)
        with open(os.path.join(pid, "cmdline"), "wb") as f:
            f.write(cmdline_bytes)
        return d

    def test_notion_token_detected(self):
        d = self._fake_proc(b"node\x00notion-mcp\x00--token\x00ntn_DEADBEEF12345678\x00")
        try:
            out = scan.scan_proc_argv(d)
            self.assertEqual(len(out), 1)
            self.assertEqual(out[0]["kind"], "proc-argv-notion-token")
            self.assertEqual(out[0]["pid"], "4242")
        finally:
            shutil.rmtree(d)

    def test_notion_without_token_ignored(self):
        d = self._fake_proc(b"node\x00notion-mcp\x00--help\x00")
        try:
            self.assertEqual(scan.scan_proc_argv(d), [])
        finally:
            shutil.rmtree(d)


class TestSecretsNames(unittest.TestCase):
    def test_pat_in_filename(self):
        d = tempfile.mkdtemp()
        open(os.path.join(d, "ghp_ABCDEFGHIJ.txt"), "w").close()
        open(os.path.join(d, "github-app.env"), "w").close()
        try:
            out = scan.scan_secrets_names(d)
            self.assertEqual(len(out), 1)
            self.assertIn("ghp_", out[0]["match"])
        finally:
            shutil.rmtree(d)


class TestTokensJson(unittest.TestCase):
    def test_malformed_json(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            f.write("{not valid json")
            p = f.name
        try:
            out = scan.scan_tokens_json(p, systemd_dir="/nonexistent")
            self.assertFalse(out[0]["parse_ok"])
        finally:
            os.unlink(p)

    def test_malformed_entries_and_consumers(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"a": "ok", "b": ["unexpected-list"]}, f)
            p = f.name
        sd = tempfile.mkdtemp()
        with open(os.path.join(sd, "foo.service"), "w") as f:
            f.write("[Service]\nEnvironmentFile=/data/tokens.json\n")
        try:
            out = scan.scan_tokens_json(p, systemd_dir=sd)
            self.assertTrue(out[0]["parse_ok"])
            self.assertEqual(out[0]["malformed_entries"], ["b"])
            self.assertEqual(out[0]["consumers"], ["foo.service"])
        finally:
            os.unlink(p)
            shutil.rmtree(sd)


class TestPorts(unittest.TestCase):
    def test_expected_ports(self):
        out = scan.scan_ports(expected={80, 443},
                              tcp_files=("tests/fixtures/proc_tcp_sample",))
        self.assertEqual(out[0]["unexpected"], [9999])
        self.assertEqual(out[0]["missing"], [443])


if __name__ == "__main__":
    unittest.main()