import pytest
from numkit import soma, media, maximo, fmt, main


def test_soma_basica():
    assert soma([1.0, 2.0, 3.5]) == 6.5


def test_soma_vazia():
    assert soma([]) == 0


def test_soma_negativos():
    assert soma([-1, -2.5, 3]) == -0.5


def test_media_basica():
    assert media([2.0, 4.0]) == 3.0


def test_media_um_elemento():
    assert media([7.5]) == 7.5


def test_media_vazia_erro():
    with pytest.raises(ValueError):
        media([])


def test_maximo_basico():
    assert maximo([1, 9.5, 3]) == 9.5


def test_maximo_negativos():
    assert maximo([-5, -2, -9]) == -2


def test_maximo_vazio_erro():
    with pytest.raises(ValueError):
        maximo([])


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


def test_cli_subcomando_invalido():
    with pytest.raises(SystemExit) as e:
        main(["foo", "1"])
    assert e.value.code != 0