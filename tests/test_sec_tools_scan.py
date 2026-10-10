import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import sec_tools_scan as sts

VULN = """#!/usr/bin/env bash
ID="${1:-}"
BRANCH="rd-$ID"
WT_ADD="git worktree add -b \\"$BRANCH\\" /tmp/wt-$ID"
eval "$WT_ADD"
OUT=$(printf '{"ok":false,"error":"%s"}\\n' "$MERGE_OUT")
grep -E "$PAT" file.txt
cd $DIR
"""

SAFE = """#!/usr/bin/env bash
ID="${1:-}"
case "$ID" in ''|*[!A-Za-z0-9._-]*) fail INVALID_MISSION_ID ;; esac
rg -e "$PAT" -- "$DIR"
cd "$DIR"
printf '%s\\n' "$OUT"
"""


class TestScanScript(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="sec-test-")

    def _w(self, name, src):
        p = os.path.join(self.d, name)
        with open(p, "w") as fh:
            fh.write(src)
        return p

    def test_vulnerable_eval(self):
        f = self._w("vuln.sh", VULN)
        out = sts.scan_script(f)
        evals = [x for x in out if x["check"] == "eval"]
        self.assertTrue(evals, "esperava achado de eval")
        self.assertEqual(evals[0]["sev"], "EXPLORAVEL")

    def test_vulnerable_grep(self):
        f = self._w("vuln.sh", VULN)
        out = sts.scan_script(f)
        self.assertTrue([x for x in out if x["check"] == "grep -e/-E"
                         and x["sev"] == "VALIDACAO_AUSENTE"])

    def test_vulnerable_cd(self):
        f = self._w("vuln.sh", VULN)
        out = sts.scan_script(f)
        self.assertTrue([x for x in out if x["check"] == "cd unquoted"])

    def test_vulnerable_json_printf(self):
        f = self._w("vuln.sh", VULN)
        out = sts.scan_script(f)
        self.assertTrue([x for x in out if x["check"] == "json-printf"])

    def test_safe_no_eval(self):
        f = self._w("safe.sh", SAFE)
        out = sts.scan_script(f)
        self.assertEqual([x for x in out if x["check"] == "eval"], [])

    def test_safe_grep_ok(self):
        f = self._w("safe.sh", SAFE)
        out = sts.scan_script(f)
        greps = [x for x in out if x["check"] == "grep -e/-E"]
        self.assertEqual(greps, [])

    def test_main_json_output(self):
        f = self._w("vuln.sh", VULN)
        import io
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            sts.main(self.d)
        finally:
            sys.stdout = old
        d = json.loads(buf.getvalue())
        self.assertTrue(d["ok"])
        self.assertGreaterEqual(d["n_findings"], 3)

    def test_audit_proof_missing_tool(self):
        r = sts.audit_proof(tempfile.mkdtemp())
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main()