#!/usr/bin/env python3
"""Testes do detector de vagueio (detector-vagueio-01)."""
import json
import os
import subprocess
import sys

import pytest

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "detector_vagueio.py")
PY = "/usr/bin/python3"


def _ev(tool, cmd, turno=0):
    return {"ts": "2026-10-07T21:00:00Z", "turno": turno, "tool": tool, "input": cmd}


def _escrever_trail(tmp_path, eventos, nome="harness-trail.jsonl"):
    p = tmp_path / nome
    with open(p, "w", encoding="utf-8") as f:
        for e in eventos:
            f.write(json.dumps(e) + "\n")
    return str(p)


def _bash(cmd, turno=0):
    return _ev("Bash", json.dumps({"command": cmd}), turno)


def _ler(tool="Read", cmd="ler arquivo", turno=0):
    return _ev(tool, cmd, turno)


def test_trail_writer_limpo_false(tmp_path):
    evs = [_bash("cat > a.py <<EOF\nx=1\nEOF", i) for i in range(6)]
    p = _escrever_trail(tmp_path, evs)
    from scripts.detector_vagueio import analisar_trail
    r = analisar_trail(p)
    assert r["vagueando"] is False
    assert r["turnos_uteis"] == 6


def test_cauda_readonly_true(tmp_path):
    evs = [_bash("cat > a.py <<EOF\nx=1\nEOF", 0), _bash("cat > b.py <<EOF\ny=2\nEOF", 1)]
    evs += [_ler(turno=i) for i in range(2, 8)]
    p = _escrever_trail(tmp_path, evs)
    from scripts.detector_vagueio import analisar_trail
    r = analisar_trail(p)
    assert r["vagueando"] is True
    assert r["leitura_pct"] == 100.0


def test_comando_repetido_3x_true(tmp_path):
    # janela=3 com 3 reads identicos: 100% READ + repeticao 3x -> True
    evs = [_ler(cmd="grep foo log.txt", turno=i) for i in range(3)]
    p = _escrever_trail(tmp_path, evs)
    from scripts.detector_vagueio import analisar_trail
    r = analisar_trail(p, janela=3)
    assert r["vagueando"] is True


def test_linha_corrompida_pulada(tmp_path):
    p = tmp_path / "harness-trail.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        f.write("{corrompida aqui\n")
        f.write(json.dumps(_bash("cat > a.py <<EOF\nx=1\nEOF", 0)) + "\n")
        f.write("nao e json\n")
        f.write(json.dumps(_bash("cat > b.py <<EOF\ny=2\nEOF", 1)) + "\n")
    from scripts.detector_vagueio import analisar_trail
    r = analisar_trail(str(p))
    assert r["turnos_uteis"] == 2
    assert r["vagueando"] is False


def test_trail_ausente(tmp_path):
    from scripts.detector_vagueio import analisar_trail
    r = analisar_trail(str(tmp_path / "nao_existe.jsonl"))
    assert r["vagueando"] is False
    assert r["motivo"] == "trail ausente"


def test_eventos_prefixo_ignorados(tmp_path):
    evs = [_ev("_inicio", "{}", 0), _ev("_stop_check", "{}", 1), _ev("_resumo", "{}", 2)]
    evs += [_ler(turno=i) for i in range(3, 9)]
    p = _escrever_trail(tmp_path, evs)
    from scripts.detector_vagueio import analisar_trail
    r = analisar_trail(p)
    assert r["turnos_uteis"] == 6
    assert r["vagueando"] is True


def test_janela_limiar_inclusivo(tmp_path):
    # 5 reads + 1 write na janela: 83.3% READ >= 83% -> True (limiar inclusivo)
    evs = [_bash("cat > a.py <<EOF\nx=1\nEOF", 0)]
    evs += [_ler(cmd="grep %d f%d" % (i, i), turno=i + 1) for i in range(5)]
    p = _escrever_trail(tmp_path, evs)
    from scripts.detector_vagueio import analisar_trail
    r = analisar_trail(p, janela=6)
    assert r["leitura_pct"] == pytest.approx(83.3, abs=0.1)
    assert r["vagueando"] is True


def test_janela_abaixo_limiar(tmp_path):
    # 4 reads + 2 writes na janela: 66.7% READ < 83% -> False
    evs = [_bash("cat > a.py <<EOF\nx=1\nEOF", 0), _bash("cat > b.py <<EOF\ny=2\nEOF", 1)]
    evs += [_ler(cmd="grep %d f%d" % (i, i), turno=i + 2) for i in range(4)]
    p = _escrever_trail(tmp_path, evs)
    from scripts.detector_vagueio import analisar_trail
    r = analisar_trail(p, janela=6)
    assert r["leitura_pct"] == pytest.approx(66.7, abs=0.1)
    assert r["vagueando"] is False


def test_write_shaped_bash_varios_tokens(tmp_path):
    evs = [_bash("tee saida.txt <<EOF\nx\nEOF", 0),
           _bash("sed -i 's/a/b/' f.txt", 1),
           _bash("cp a b", 2),
           _bash("patch -p0 < p.diff", 3),
           _bash("echo x > f.txt", 4),
           _ler(turno=5)]
    p = _escrever_trail(tmp_path, evs)
    from scripts.detector_vagueio import analisar_trail
    r = analisar_trail(p)
    assert r["vagueando"] is False
    assert r["leitura_pct"] == pytest.approx(16.7, abs=0.1)


def test_cli_exit_codes(tmp_path):
    evs = [_bash("cat > a.py <<EOF\nx=1\nEOF", i) for i in range(6)]
    p_writer = _escrever_trail(tmp_path, evs, "writer.jsonl")
    evs_ro = [_ler(turno=i) for i in range(6)]
    p_vague = _escrever_trail(tmp_path, evs_ro, "vague.jsonl")
    r0 = subprocess.run([PY, SCRIPT, "--trail", p_writer], capture_output=True)
    assert r0.returncode == 0
    r1 = subprocess.run([PY, SCRIPT, "--trail", p_vague, "--json"], capture_output=True)
    assert r1.returncode == 1
    out = json.loads(r1.stdout.decode())
    assert out["vagueando"] is True
    r2 = subprocess.run([PY, SCRIPT], capture_output=True)
    assert r2.returncode == 2


def test_cli_janela_respeitada(tmp_path):
    # 6 reads identicos no fim, 1 write antes: --janela muda a janela analisada
    evs = [_bash("cat > a.py <<EOF\nx=1\nEOF", 0)]
    evs += [_ler(cmd="tail -n 5 log", turno=i + 1) for i in range(6)]
    p = _escrever_trail(tmp_path, evs)
    r6 = subprocess.run([PY, SCRIPT, "--trail", p, "--janela", "6", "--json"],
                        capture_output=True)
    assert r6.returncode == 1  # janela=6: so reads identicos -> vagueando
    r7 = subprocess.run([PY, SCRIPT, "--trail", p, "--janela", "7", "--json"],
                        capture_output=True)
    out7 = json.loads(r7.stdout.decode())
    # janela=7 inclui o write: leitura_pct cai de 100 para ~85.7
    assert out7["leitura_pct"] == pytest.approx(85.7, abs=0.1)
    assert out7["turnos_uteis"] == 7