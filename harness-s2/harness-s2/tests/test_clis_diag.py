# Rodar: python3 -m pytest tests/test_clis_diag.py -q
"""Testes para os 3 CLIs de diagnóstico sem cobertura: run_tempo, trail_saude, runs_diff."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import run_tempo  # noqa: E402
import trail_saude  # noqa: E402
import runs_diff  # noqa: E402


def _ev(**kw):
    ev = {"ts": "2026-01-01T00:00:00Z", "turno": 0}
    ev.update(kw)
    return ev


def _escrever(tmp, nome, eventos, lixo=None):
    path = os.path.join(tmp, nome)
    with open(path, "w", encoding="utf-8") as f:
        for e in eventos:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
        if lixo is not None:
            f.write(lixo + "\n")
    return path


class TestTempoDaRun(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_trail_finalizado(self):
        evs = [
            _ev(tool="_inicio", turno=0, custo_usd=0.0),
            _ev(tool="llm", turno=1, latencia_ms=100, custo_usd=0.01),
            _ev(tool="bash", turno=2, custo_usd=0.0),
            _ev(tool="llm", turno=3, latencia_ms=300, custo_usd=0.02),
            _ev(tool="_resumo", turno=3, custo_usd=0.0, veredito="PASS"),
        ]
        p = _escrever(self.tmp, "t.jsonl", evs)
        out = run_tempo.tempo_da_run(p)
        self.assertIn("turnos=3", out)
        self.assertIn("custo=$0.030000", out)
        self.assertIn("veredito=PASS", out)

    def test_um_evento_wall_zero(self):
        p = _escrever(self.tmp, "t.jsonl", [_ev(tool="_inicio", turno=0)])
        out = run_tempo.tempo_da_run(p)
        self.assertIn("wall=00:00:00", out)
        self.assertIn("turnos=0", out)

    def test_trail_inexistente(self):
        p = os.path.join(self.tmp, "nada.jsonl")
        self.assertEqual(run_tempo.tempo_da_run(p), "SEM TRAIL")

    def test_trail_inexistente_exit1_sem_excecao(self):
        p = os.path.join(self.tmp, "nada.jsonl")
        rc = run_tempo.main(["run_tempo.py", p])
        self.assertEqual(rc, 1)


class TestSaudeDoTrail(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_trail_saudavel(self):
        evs = [
            _ev(tool="_inicio", turno=0),
            _ev(tool="llm", turno=1),
            _ev(tool="bash", turno=2),
            _ev(tool="_resumo", turno=2, veredito="PASS"),
        ]
        p = _escrever(self.tmp, "t.jsonl", evs)
        self.assertEqual(trail_saude.saude_do_trail(p), "SAUDÁVEL | 4 eventos")

    def test_linha_lixo(self):
        evs = [_ev(tool="_inicio", turno=0), _ev(tool="llm", turno=1)]
        p = _escrever(self.tmp, "t.jsonl", evs, lixo="isto não é json {")
        out = trail_saude.saude_do_trail(p)
        self.assertTrue(out.startswith("DOENTE"))
        self.assertIn("não é JSON parseável", out)

    def test_turnos_decrescentes(self):
        evs = [_ev(tool="_inicio", turno=0), _ev(tool="llm", turno=2), _ev(tool="bash", turno=1)]
        p = _escrever(self.tmp, "t.jsonl", evs)
        out = trail_saude.saude_do_trail(p)
        self.assertTrue(out.startswith("DOENTE"))
        self.assertIn("decrescente", out)


class TestDiffRuns(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_delta_custo_e_turnos(self):
        a = [_ev(tool="_inicio", turno=0, custo_usd=0.0), _ev(tool="llm", turno=1, custo_usd=0.01)]
        b = [
            _ev(tool="_inicio", turno=0, custo_usd=0.0),
            _ev(tool="llm", turno=1, custo_usd=0.02),
            _ev(tool="llm", turno=2, custo_usd=0.03),
        ]
        pa = _escrever(self.tmp, "a.jsonl", a)
        pb = _escrever(self.tmp, "b.jsonl", b)
        out = runs_diff.diff_runs(pa, pb)
        esperado_dc = f"{0.05 - 0.01:.6f}".replace(".", ",")
        self.assertIn(f"Δcusto={esperado_dc}", out)
        self.assertIn("Δturnos=1", out)


class TestParidadeImport(unittest.TestCase):
    def test_tres_clis_como_modulo_sem_excecao(self):
        tmp = tempfile.mkdtemp()
        evs = [
            _ev(tool="_inicio", turno=0, custo_usd=0.0),
            _ev(tool="llm", turno=1, latencia_ms=50, custo_usd=0.01),
            _ev(tool="_resumo", turno=1, custo_usd=0.0, veredito="PASS"),
        ]
        p = _escrever(tmp, "t.jsonl", evs)
        self.assertIn("veredito=PASS", run_tempo.tempo_da_run(p))
        self.assertTrue(trail_saude.saude_do_trail(p).startswith("SAUDÁVEL"))
        self.assertIn("Δturnos=0", runs_diff.diff_runs(p, p))
