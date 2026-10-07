import pytest

from listkit import inverte, main, ordena, unicos


# --- ordena ---
def test_ordena_basico():
    assert ordena(["c", "a", "b"]) == ["a", "b", "c"]


def test_ordena_numeros_como_texto():
    assert ordena(["10", "2"]) == ["10", "2"]


def test_ordena_vazio():
    assert ordena([]) == []


def test_ordena_ja_ordenada():
    assert ordena(["a", "b"]) == ["a", "b"]


# --- unicos ---
def test_unicos_basico():
    assert unicos(["a", "b", "a"]) == ["a", "b"]


def test_unicos_ordem_primeira_aparicao():
    assert unicos(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]


def test_unicos_sem_repeticao():
    assert unicos(["x"]) == ["x"]


def test_unicos_vazio():
    assert unicos([]) == []


# --- inverte ---
def test_inverte_basico():
    assert inverte(["a", "b", "c"]) == ["c", "b", "a"]


def test_inverte_um():
    assert inverte(["solo"]) == ["solo"]


def test_inverte_vazio():
    assert inverte([]) == []


# --- CLI ---
def test_cli_ordena(capsys):
    assert main(["ordena", "c", "a", "b"]) == 0
    assert capsys.readouterr().out == "a b c\n"


def test_cli_unicos(capsys):
    assert main(["unicos", "a", "b", "a"]) == 0
    assert capsys.readouterr().out == "a b\n"


def test_cli_inverte(capsys):
    assert main(["inverte", "1", "2", "3"]) == 0
    assert capsys.readouterr().out == "3 2 1\n"


def test_cli_subcomando_invalido():
    with pytest.raises(SystemExit) as e:
        main(["nada", "x"])
    assert e.value.code != 0


def test_cli_help(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0