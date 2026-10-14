import subprocess
import sys

from textkit import conta, inverte, maiusculas, main


# --- conta ---
def test_conta_basico():
    assert conta("um dois tres") == 3


def test_conta_espacos_multiplos():
    assert conta("a   b") == 2


def test_conta_vazio():
    assert conta("") == 0


def test_conta_somente_espacos():
    assert conta("   ") == 0


def test_conta_uma_palavra():
    assert conta("solo") == 1


# --- inverte ---
def test_inverte_basico():
    assert inverte("abc") == "cba"


def test_inverte_palindromo():
    assert inverte("arara") == "arara"


def test_inverte_vazio():
    assert inverte("") == ""


# --- maiusculas ---
def test_maiusculas_basico():
    assert maiusculas("abc") == "ABC"


def test_maiusculas_mista():
    assert maiusculas("aBc DeF") == "ABC DEF"


def test_maiusculas_acento():
    assert maiusculas("ação") == "AÇÃO"


# --- CLI ---
def run_cli(args):
    return subprocess.run(
        [sys.executable, "textkit.py"] + args, capture_output=True, text=True
    )


def test_cli_conta():
    r = run_cli(["conta", "um dois tres"])
    assert r.returncode == 0
    assert r.stdout.strip() == "3"


def test_cli_inverte():
    r = run_cli(["inverte", "abc"])
    assert r.returncode == 0
    assert r.stdout.strip() == "cba"


def test_cli_maiusculas():
    r = run_cli(["maiusculas", "ola mundo"])
    assert r.returncode == 0
    assert r.stdout.strip() == "OLA MUNDO"


def test_cli_subcomando_invalido():
    r = run_cli(["nada"])
    assert r.returncode != 0


def test_cli_help():
    r = run_cli(["conta", "--help"])
    assert r.returncode == 0


def test_main_retorna_zero():
    assert main(["conta", "x"]) == 0