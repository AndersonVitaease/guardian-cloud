# -*- coding: utf-8 -*-
"""GB-FUNIL-UNICO-01: teste do funil unico de despacho (espelho nativo)."""
import hashlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
import espelho_nativo  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))


def ok(msg):
    print("ok: %s" % msg)


def teste_espelho_nativo():
    with tempfile.TemporaryDirectory() as d:
        mid = "GB-FUNIL-UNICO-01-TESTE"
        assert espelho_nativo.nascer_espelho(mid, d) is True
        caminho = os.path.join(d, mid + espelho_nativo.MARCA)
        assert os.path.isfile(caminho), "espelho nao nasceu"
        # fail-closed: segundo nascimento deve recusar
        assert espelho_nativo.nascer_espelho(mid, d) is False, "ESPELHO_NAO_NASCEU esperado"
        assert espelho_nativo.pousar_espelho(mid, d) is True
        assert not os.path.exists(caminho), "espelho nao pousou"
        # idempotente
        assert espelho_nativo.pousar_espelho(mid, d) is True
    ok("nascer/pousar espelho nativo (fail-closed, idempotente)")


def teste_import_no_despachante():
    fonte = os.path.join(BASE, "scripts", "despachar_missao.py")
    with open(fonte, encoding="utf-8") as f:
        src = f.read()
    assert "espelho_nativo" in src, "despachar_missao.py nao importa espelho_nativo"
    ok("despachar_missao.py chama espelho_nativo")


def teste_sha256_sync():
    def sha(p):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            h.update(f.read())
        return h.hexdigest()
    repo = os.path.join(BASE, "scripts", "despachar_missao.py")
    ref = os.path.join(BASE, "fixtures", "despachar_missao.expected.py")
    assert os.path.isfile(ref), "copia de referencia ausente em fixtures/"
    assert sha(repo) == sha(ref), "dessincronia: despachar_missao.py != fixtures/despachar_missao.expected.py"
    ok("sha256 sincrono: repo == fixtures/despachar_missao.expected.py")


def main():
    teste_espelho_nativo()
    teste_import_no_despachante()
    teste_sha256_sync()
    print("GB-FUNIL-UNICO-01-PROVA-OK")


if __name__ == "__main__":
    main()