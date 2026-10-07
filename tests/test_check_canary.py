"""Verificador da canária: solução de referência passa nos 3 temas; desvios falham."""
import json
import os
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "canary"))
import check_canary  # noqa: E402

IMPL = {
    0: ("textkit", {"conta": "str(len(a.x[0].split()))", "inverte": "a.x[0][::-1]",
                    "maiusculas": "a.x[0].upper()"}, 1),
    1: ("numkit", {"soma": "format(sum(map(float, a.x)), 'g')",
                   "media": "format(sum(map(float, a.x)) / len(a.x), 'g')",
                   "maximo": "format(max(map(float, a.x)), 'g')"}, "+"),
    2: ("listkit", {"ordena": "' '.join(sorted(a.x))", "unicos": "' '.join(dict.fromkeys(a.x))",
                    "inverte": "' '.join(a.x[::-1])"}, "+"),
}


def build(d, seed, n_tests=10):
    name, subs, nargs = IMPL[seed % 3]
    sp = "\n".join(f"    s = sp.add_parser({k!r}); s.add_argument('x', nargs={nargs!r})" for k in subs)
    run = "\n".join(f"    if a.cmd == {k!r}: return {v}" for k, v in subs.items())
    open(os.path.join(d, f"{name}.py"), "w").write(textwrap.dedent(f"""\
import argparse, sys
def parser():
    p = argparse.ArgumentParser(); sp = p.add_subparsers(dest='cmd', required=True)
{sp}
    return p
def run(a):
{run}
if __name__ == '__main__':
    print(run(parser().parse_args()))
"""))
    open(os.path.join(d, f"test_{name}.py"), "w").write(
        "".join(f"def test_{i}():\n    assert True\n" for i in range(n_tests)))
    open(os.path.join(d, "README.md"), "w").write(" ".join(subs))
    json.dump({"mission": f"CANARIA-MEDIA-S{seed}",
               "cmd": [{"run": "python3 -m pytest -q -p no:cacheprovider", "expect_exit": 0}],
               "file": [{"path": f"{name}.py"}, {"path": "README.md"}]},
              open(os.path.join(d, "verify.json"), "w"))
    return name


class TestCheckCanary(unittest.TestCase):
    def test_referencia_passa_nos_3_temas(self):
        for seed in (0, 1, 2, 5):
            with tempfile.TemporaryDirectory() as d:
                build(d, seed)
                self.assertEqual(check_canary.check(seed, d), [], f"seed={seed}")

    def test_tema_errado_falha(self):
        with tempfile.TemporaryDirectory() as d:
            build(d, 0)
            self.assertTrue(check_canary.check(1, d))     # seed 1 exige numkit.py

    def test_poucos_testes_falha(self):
        with tempfile.TemporaryDirectory() as d:
            build(d, 2, n_tests=9)
            self.assertTrue(any("pytest" in e for e in check_canary.check(2, d)))

    def test_verify_sem_mission_ou_file_falha(self):
        with tempfile.TemporaryDirectory() as d:
            build(d, 1)
            json.dump({"cmd": [{"run": "true"}], "file": [{"path": "nao.txt"}]},
                      open(os.path.join(d, "verify.json"), "w"))
            errs = check_canary.check(1, d)
            self.assertTrue(any("mission" in e for e in errs))
            self.assertTrue(any("nao.txt" in e for e in errs))

    def test_readme_sem_subcomando_falha(self):
        with tempfile.TemporaryDirectory() as d:
            build(d, 0)
            open(os.path.join(d, "README.md"), "w").write("conta inverte")
            self.assertTrue(any("maiusculas" in e for e in check_canary.check(0, d)))

    def test_pin_python_absoluto(self):
        pin = check_canary.pin_python
        self.assertEqual(pin("python3 -m pytest -q"), f"{check_canary.PY} -m pytest -q")
        self.assertEqual(pin("cd x && python3 a.py && python3"), f"cd x && {check_canary.PY} a.py && {check_canary.PY}")
        self.assertEqual(pin("/usr/bin/python3 a.py"), "/usr/bin/python3 a.py")
        self.assertEqual(pin("python3.12 a.py; mypython3 b"), "python3.12 a.py; mypython3 b")


if __name__ == "__main__":
    unittest.main()
