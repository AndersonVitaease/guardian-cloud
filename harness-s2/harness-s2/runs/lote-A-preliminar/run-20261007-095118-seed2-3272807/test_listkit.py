import subprocess
import sys

import listkit


def test_ordena_basico():
    assert listkit.ordena(["c", "a", "b"]) == ["a", "b", "c"]


def test_ordena_vazio():
    assert listkit.ordena([]) == []


def test_ordena_numeros_como_texto():
    assert listkit.ordena(["10", "2"]) == ["10", "2"]


def test_unicos_basico():
    assert listkit.unicos(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]


def test_unicos_preserva_ordem():
    assert listkit.unicos(["z", "a", "z", "m"]) == ["z", "a", "m"]


def test_unicos_vazio():
    assert listkit.unicos([]) == []


def test_inverte_basico():
    assert listkit.inverte(["a", "b", "c"]) == ["c", "b", "a"]


def test_inverte_um():
    assert listkit.inverte(["x"]) == ["x"]


def test_cli_ordena():
    r = subprocess.run([sys.executable, "listkit.py", "ordena", "c", "a", "b"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert r.stdout.strip() == "a b c"


def test_cli_unicos():
    r = subprocess.run([sys.executable, "listkit.py", "unicos", "a", "b", "a"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert r.stdout.strip() == "a b"


def test_cli_inverte():
    r = subprocess.run([sys.executable, "listkit.py", "inverte", "1", "2", "3"],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert r.stdout.strip() == "3 2 1"


def test_cli_help():
    r = subprocess.run([sys.executable, "listkit.py", "ordena", "--help"],
                       capture_output=True, text=True)
    assert r.returncode == 0


def test_cli_subcomando_invalido():
    r = subprocess.run([sys.executable, "listkit.py", "foo", "a"],
                       capture_output=True, text=True)
    assert r.returncode != 0