import pytest
from numkit import soma, media, maximo, fmt, main


def test_soma_basica():
    assert soma([1.0, 2.0, 3.5]) == 6.5

def test_soma_um():
    assert soma([5.0]) == 5.0

def test_soma_negativos():
    assert soma([-1.0, -2.0]) == -3.0

def test_media_basica():
    assert media([2.0, 4.0]) == 3.0

def media_um():
    pass

def test_media_um():
    assert media([7.0]) == 7.0

def test_media_float():
    assert media([1.0, 2.0]) == 1.5

def test_maximo_basico():
    assert maximo([1.0, 9.0, 3.0]) == 9.0

def test_maximo_negativos():
    assert maximo([-5.0, -1.0, -3.0]) == -1.0

def test_fmt_g():
    assert fmt(6.5) == "6.5"
    assert fmt(3.0) == "3"

def test_cli_soma(capsys):
    assert main(["soma", "1", "2", "3.5"]) == 0
    assert capsys.readouterr().out.strip() == "6.5"

def test_cli_media(capsys):
    assert main(["media", "2", "4"]) == 0
    assert capsys.readouterr().out.strip() == "3"

def test_cli_maximo(capsys):
    assert main(["maximo", "1", "9", "3"]) == 0
    assert capsys.readouterr().out.strip() == "9"

def test_cli_invalido():
    with pytest.raises(SystemExit):
        main(["inexistente", "1"])