import subprocess
import sys

import pytest

import listkit


def test_ordena_basico():
    assert listkit.ordena(["c", "a", "b"]) == ["a", "b", "c"]


def test_ordena_vazio():
    assert listkit.ordena([]) == []


def test_ordena_numeros_como_str():
    assert listkit.ordena(["10", "2", "1"]) == ["1", "10", "2"]


def test_unicos_basico():
    assert listkit.unicos(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]


def test_unicos_sem_repeticao():
    assert listkit.unicos(["x"]) == ["x"]


def test_unicos_ordem_primeira_aparicao():
    assert listkit.unicos(["z", "a", "z", "a", "m"]) == ["z", "a", "m"]


def test_inverte_basico():
    assert listkit.inverte(["1", "2", "3"]) == ["3", "2", "1"]


def test_inverte_um():
    assert listkit.inverte(["solo"]) == ["solo"]


def test_inverte_nao_mutar_entrada():
    e = ["a", "b"]
    listkit.inverte(e)
    assert e == ["a", "b"]


def run_cli(args):
    return subprocess.run([sys.executable, "listkit.py"] + args,
                          capture_output=True, text=True)


def test_cli_ordena():
    r = run_cli(["ordena", "banana", "abacate", "uva"])
    assert r.returncode == 0
    assert r.stdout.strip() == "abacate banana uva"


def test_cli_unicos():
    r = run_cli(["unicos", "a", "b", "a"])
    assert r.returncode == 0
    assert r.stdout.strip() == "a b"


def test_cli_inverte():
    r = run_cli(["inverte", "1", "2", "3"])
    assert r.returncode == 0
    assert r.stdout.strip() == "3 2 1"


def test_cli_help_exit_zero():
    assert subprocess.run([sys.executable, "listkit.py", "ordena", "--help"]).returncode == 0


def test_cli_subcomando_invalido():
    r = subprocess.run([sys.executable, "listkit.py", "foo", "x"],
                       capture_output=True)
    assert r.returncode != 0