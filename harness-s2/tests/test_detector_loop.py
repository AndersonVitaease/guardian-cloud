# -*- coding: utf-8 -*-
"""Testes do detector de loop (trails fabricados em tmp)."""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from detector_loop import detectar_loop  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "detector_loop.py")


def _ev(**kw):
    return json.dumps(kw)


def _trail(tmp_path, stops, resumo=None, custo=0.01, turnos=None):
    linhas = [_ev(ts="t", turno=0, tool="_inicio")]
    t = 1
    for i, st in enumerate(stops):
        linhas.append(_ev(ts="t", turno=t, tool="llm", cum_usd=custo * (i + 1)))
        linhas.append(_ev(ts="t", turno=t, tool="_stop_check", stop_tick=st[1], stop_state=st[0]))
        t += 1
    if turnos is not None:
        t = turnos
    if resumo:
        linhas.append(_ev(ts="t", turno=t, tool="_resumo", veredito=resumo, motivo="ok"))
    p = tmp_path / "harness-trail.jsonl"
    p.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return str(p)


PEND = {"0:cmd": True, "1:cmd": False, "2:cmd": False}


def test_loop_verdadeiro(tmp_path):
    stops = [(PEND, [])] * 7
    p = _trail(tmp_path, stops)
    d = detectar_loop(p, janela=5)
    assert d["em_loop"] is True
    assert d["turnos_sem_progresso"] >= 5
    assert d["pendentes"] == ["1:cmd", "2:cmd"]
    assert d["ticks_novos"] is False


def test_com_progresso_nao_loop(tmp_path):
    stops = [(PEND, [])] * 4 + [(PEND, ["1:cmd"])] + [(PEND, [])] * 4
    p = _trail(tmp_path, stops)
    d = detectar_loop(p, janela=5)
    assert d["em_loop"] is False
    assert d["ticks_novos"] is True


def test_run_finalizada_pass(tmp_path):
    stops = [(PEND, [])] * 7
    p = _trail(tmp_path, stops, resumo="PASS")
    d = detectar_loop(p)
    assert d["em_loop"] is False
    assert d["veredito"] == "PASS"


def test_trail_vazio_e_inexistente(tmp_path):
    vazio = tmp_path / "vazio.jsonl"
    vazio.write_text("", encoding="utf-8")
    d = detectar_loop(str(vazio))
    assert d["em_loop"] is False and d["erro"] == "SEM TRAIL"
    d2 = detectar_loop(str(tmp_path / "nao-existe.jsonl"))
    assert d2["em_loop"] is False and d2["erro"] == "SEM TRAIL"


def test_janela_configuravel(tmp_path):
    stops = [(PEND, [])] * 4
    p = _trail(tmp_path, stops)
    assert detectar_loop(p, janela=3)["em_loop"] is True
    assert detectar_loop(p, janela=5)["em_loop"] is False


def test_cli_exit_codes(tmp_path):
    loop = _trail(tmp_path / "a" if False else tmp_path, [(PEND, [])] * 7)
    rc = subprocess.run([sys.executable, SCRIPT, loop], capture_output=True, text=True)
    assert rc.returncode == 2 and "LOOP DETECTADO" in rc.stdout
    fin = _trail(tmp_path, [(PEND, [])] * 7, resumo="PASS")
    rc2 = subprocess.run([sys.executable, SCRIPT, fin], capture_output=True, text=True)
    assert rc2.returncode == 0 and "RUN FINALIZADA" in rc2.stdout
    rc3 = subprocess.run([sys.executable, SCRIPT, str(tmp_path / "x.jsonl")], capture_output=True, text=True)
    assert rc3.returncode == 0 and "SEM TRAIL" in rc3.stdout
