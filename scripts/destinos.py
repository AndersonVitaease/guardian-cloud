# -*- coding: utf-8 -*-
"""GB-DESP-ORDEM-01: DESTINOS — declaração ÚNICA de onde postar cada artefato.

Fim dos caminhos hard-coded espalhados: despachar_missao.py, contratador.sh e
espelho_nativo.py importam daqui. Para ver o bloco markdown do contrato:
    python3 scripts/destinos.py   # imprime "## DESTINOS" + lista
"""
import os

DESTINOS = {
    "ABA": "herdr (via scripts/mount-espelho.sh)",
    "ESPELHO_SALA": "/tmp/ag-live",
    "ESPELHO_NATIVO": "/tmp/espelho-nativo",
    "LEDGER": "/root/.hermes/mission-state",
    "AVISO": "scripts/aviso_chat.sh",
    "RESUMO": "/tmp/resumo-<id>.json",
    "SPOOL": "/opt/mission-events/spool.jsonl",
}


def resumo(mid):
    """Caminho do resumo JSON da missão (RESUMO)."""
    return "/tmp/resumo-%s.json" % mid


def espelho_sala(mid):
    """Caminho do espelho de sala da missão (ESPELHO_SALA)."""
    return os.path.join(DESTINOS["ESPELHO_SALA"], mid + ".espelho.json")


def espelho_nativo_dir():
    """Diretório do espelho nativo (guard de duplicidade, GB-FUNIL-UNICO-01)."""
    return DESTINOS["ESPELHO_NATIVO"]


if __name__ == "__main__":
    print("## DESTINOS")
    for _k, _v in DESTINOS.items():
        print("- %s: `%s`" % (_k, _v))