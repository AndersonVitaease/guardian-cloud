import io
import json
import time

import pytest

from scripts.latencia_e2e import latencia_stream


def _fabricado(n, delay=0.0):
    """Reader fabricado: N linhas SSE, com sleep injetável entre elas."""
    linhas = [b"data: evento %d\n\n" % i for i in range(n)]

    class Resp(io.BufferedIOBase):
        def __iter__(self):
            return self

        def __next__(self):
            if not linhas:
                raise StopIteration
            if delay:
                time.sleep(delay)
            return linhas.pop(0)

    return Resp()


def test_tempos_coerentes(tmp_path):
    out = str(tmp_path / "lat.jsonl")
    reg = latencia_stream(_post=lambda p: _fabricado(10, delay=0.01), _out=out)
    assert reg["total"] >= reg["primeiro_evento"] > 0
    assert reg["eventos"] == 10


def test_stream_vazio_exit_honesto(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        latencia_stream(_post=lambda p: _fabricado(0), _out=str(tmp_path / "l.jsonl"))
    assert e.value.code == 1
    assert "vazio" in capsys.readouterr().out


def test_jsonl_uma_linha_por_rodada(tmp_path):
    out = str(tmp_path / "lat.jsonl")
    latencia_stream(_post=lambda p: _fabricado(3), _out=out)
    latencia_stream(_post=lambda p: _fabricado(5), _out=out)
    linhas = [json.loads(l) for l in open(out)]
    assert len(linhas) == 2
    assert linhas[0]["eventos"] == 3 and linhas[1]["eventos"] == 5


def test_bridge_recusado_exit_1(capsys):
    def falha(p):
        raise ConnectionError("recusado")
    with pytest.raises(SystemExit) as e:
        latencia_stream(_post=falha, _out="/tmp/x.jsonl")
    assert e.value.code == 1
