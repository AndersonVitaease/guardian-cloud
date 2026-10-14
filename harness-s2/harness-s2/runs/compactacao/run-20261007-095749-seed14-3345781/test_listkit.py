import pytest

from listkit import ordena, unicos, inverte, main


# --- funções ---
def test_ordena_basico():
    assert ordena(["b", "a", "c"]) == ["a", "b", "c"]

def test_ordena_numeros_como_texto():
    assert ordena(["10", "2"]) == ["10", "2"]

def test_ordena_vazio():
    assert ordena([]) == []

def test_unicos_basico():
    assert unicos(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]

def test_unicos_sem_repeticao():
    assert unicos(["x"]) == ["x"]

def test_unicos_vazio():
    assert unicos([]) == []

def test_inverte_basico():
    assert inverte(["a", "b", "c"]) == ["c", "b", "a"]

def test_inverte_um():
    assert inverte(["solo"]) == ["solo"]

def test_inverte_nao_altera_original():
    l = ["1", "2"]
    inverte(l)
    assert l == ["1", "2"]


# --- CLI ---
def test_cli_ordena(capsys):
    assert main(["ordena", "b", "a"]) == 0
    assert capsys.readouterr().out == "a b\n"

def test_cli_unicos(capsys):
    assert main(["unicos", "a", "a", "b"]) == 0
    assert capsys.readouterr().out == "a b\n"

def test_cli_inverte(capsys):
    assert main(["inverte", "1", "2", "3"]) == 0
    assert capsys.readouterr().out == "3 2 1\n"

def test_cli_subcomando_invalido():
    with pytest.raises(SystemExit) as e:
        main(["foo"])
    assert e.value.code != 0