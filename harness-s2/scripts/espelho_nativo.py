# -*- coding: utf-8 -*-
"""GB-FUNIL-UNICO-01: porta unica de despacho — trava de espelho nativo.

Modulo compartilhado extraido de scripts/despachar_missao.py (FATIA A).
A copia do consumer do despachante deve ser 1:1 deste arquivo (ver
CONTRATO-APLICACAO.md). nascer_espelho e fail-closed: se o espelho ja
existe, retorna False (chamador deve falhar tipado ESPELHO_NAO_NASCEU).
"""
import os

try:  # GB-DESP-ORDEM-01: destino unico em scripts/destinos.py
    import destinos as _destinos
except ImportError:
    _destinos = None

MARCA = ".espelho-nativo"


def _dir(esp_dir=None):
    if esp_dir:
        return esp_dir
    if os.environ.get("ESP_DIR"):
        return os.environ["ESP_DIR"]
    if _destinos is not None:
        return _destinos.espelho_nativo_dir()
    return "/tmp/espelho-nativo"


def nascer_espelho(mid, esp_dir=None):
    """Cria marcador atomico do espelho para a missao. False se ja existe."""
    d = _dir(esp_dir)
    os.makedirs(d, exist_ok=True)
    caminho = os.path.join(d, "%s%s" % (mid, MARCA))
    try:
        fd = os.open(caminho, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w") as f:
        f.write(mid + "\n")
    return True


def pousar_espelho(mid, esp_dir=None):
    """Remove o marcador do espelho (idempotente)."""
    caminho = os.path.join(_dir(esp_dir), "%s%s" % (mid, MARCA))
    try:
        os.unlink(caminho)
    except FileNotFoundError:
        pass
    return True
