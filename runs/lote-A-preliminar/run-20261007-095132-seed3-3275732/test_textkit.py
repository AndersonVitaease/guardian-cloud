import subprocess
import sys

import textkit


def test_conta_basico():
    assert textkit.conta("um dois três") == 3


def test_conta_espacos_multiplos():
    assert textkit.conta("a   b") == 2


def test_conta_vazio():
    assert textkit.conta("") == 0


def test_conta_uma_palavra():
    assert textkit.conta("solo") == 1


def test_inverte_basico():
    assert textkit.inverte("abc") == "cba"


def test_inverte_vazio():
    assert textkit.inverte("") == ""


def test_inverte_palindromo():
    assert textkit.inverte("arara") == "arara"


def test_maiusculas_basico():
    assert textkit.maiusculas("olá mundo") == "OLÁ MUNDO"


def test_maiusculas_ja_maiusculas():
    assert textkit.maiusculas("ABC") == "ABC"


def run_cli(args):
    return subprocess.run([sys.executable, "textkit.py"] + args,
                          capture_output=True, text=True)


def test_cli_conta():
    r = run_cli(["conta", "um dois três"])
    assert r.returncode == 0
    assert r.stdout.strip() == "3"


def test_cli_inverte():
    r = run_cli(["inverte", "abc"])
    assert r.returncode == 0
    assert r.stdout.strip() == "cba"


def test_cli_maiusculas():
    r = run_cli(["maiusculas", "olá"])
    assert r.returncode == 0
    assert r.stdout.strip() == "OLÁ"


def test_cli_help_exit_zero():
    assert subprocess.run([sys.executable, "textkit.py", "conta", "--help"]).returncode == 0


def test_cli_subcomando_invalido():
    r = subprocess.run([sys.executable, "textkit.py", "foo", "x"], capture_output=True)
    assert r.returncode != 0