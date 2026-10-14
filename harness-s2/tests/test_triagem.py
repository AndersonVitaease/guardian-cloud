# -*- coding: utf-8 -*-
"""RD-TOOL-TRIAGEM-01 — testes com trails sintéticos em tempdir."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.triagem import triar, main  # noqa: E402


def _mk_tentativa(base, n, recs):
    d = os.path.join(base, "tentativa-%d" % n, "run-1")
    os.makedirs(d)
    with open(os.path.join(d, "harness-trail.jsonl"), "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")


def _bash(cmd, err=False, lat=10, turno=1):
    return {"tool": "Bash", "input": {"command": cmd}, "is_error": err,
            "latencia_ms": lat, "turno": turno}


def _resumo(veredito="FAIL", motivo="vagueio", turnos=9):
    return {"tool": "_resumo", "veredito": veredito, "motivo": motivo, "turnos": turnos}


class TriagemTest(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp()

    def _t(self):
        return triar(self.base)

    def test_leitura_recusada(self):
        recs = [_bash("cat x", err=True, lat=0) for _ in range(4)] + [_resumo()]
        _mk_tentativa(self.base, 1, recs)
        out = self._t()
        self.assertIn("LEITURA_RECUSADA", out["tentativas"][0]["causas"])
        self.assertEqual(out["causa_dominante"], "LEITURA_RECUSADA")
        self.assertIn("BASH-FILTRO-PIPE-01", out["acao"])

    def test_so_exploracao(self):
        recs = [_bash("ls x") for _ in range(16)] + [_resumo()]
        _mk_tentativa(self.base, 1, recs)
        out = self._t()
        self.assertIn("SO_EXPLORACAO", out["tentativas"][0]["causas"])
        self.assertEqual(out["causa_dominante"], "SO_EXPLORACAO")

    def test_edit_falhou(self):
        recs = [_bash("ls"),
                {"tool": "Edit", "input": {}, "is_error": True, "latencia_ms": 5, "turno": 2},
                {"tool": "Edit", "input": {}, "is_error": True, "latencia_ms": 5, "turno": 3}] + [_resumo()]
        _mk_tentativa(self.base, 1, recs)
        out = self._t()
        self.assertIn("EDIT_FALHOU", out["tentativas"][0]["causas"])
        self.assertEqual(out["causa_dominante"], "EDIT_FALHOU")

    def test_loop_comando_recusado(self):
        recs = [_bash("pwd", err=True) for _ in range(3)] + [_resumo()]
        _mk_tentativa(self.base, 1, recs)
        out = self._t()
        self.assertIn("LOOP_COMANDO_RECUSADO", out["tentativas"][0]["causas"])
        self.assertEqual(out["causa_dominante"], "LOOP_COMANDO_RECUSADO")

    def test_setup_permissao(self):
        recs = [_bash("ls"), _resumo(motivo="setup_permissao")]
        _mk_tentativa(self.base, 1, recs)
        out = self._t()
        self.assertIn("SETUP_PERMISSAO", out["tentativas"][0]["causas"])
        self.assertEqual(out["causa_dominante"], "SETUP_PERMISSAO")
        self.assertIn("chown", out["acao"])

    def test_vagueio_e_prioridade(self):
        recs = [_bash("cat x", err=True, lat=0) for _ in range(3)] + \
               [{"tool": "_vagueio", "turno": 5}] + [_resumo()]
        _mk_tentativa(self.base, 1, recs)
        out = self._t()
        causas = out["tentativas"][0]["causas"]
        self.assertIn("VAGUEIO", causas)
        self.assertIn("LEITURA_RECUSADA", causas)
        self.assertEqual(out["causa_dominante"], "LEITURA_RECUSADA")  # prioridade

    def test_stops_lentos(self):
        recs = [_bash("ls", lat=10),
                {"tool": "_stop_check", "latencia_ms": 100, "turno": 2},
                {"tool": "_stop_check", "latencia_ms": 100, "turno": 3}] + [_resumo()]
        _mk_tentativa(self.base, 1, recs)
        out = self._t()
        self.assertIn("STOPS_LENTOS", out["tentativas"][0]["causas"])

    def test_stops_sem_dado_omitido(self):
        recs = [_bash("ls", lat=10), {"tool": "_stop_check", "turno": 2}] + [_resumo()]
        _mk_tentativa(self.base, 1, recs)
        out = self._t()
        self.assertNotIn("STOPS_LENTOS", out["tentativas"][0]["causas"])

    def test_pass_final(self):
        _mk_tentativa(self.base, 1, [_bash("ls"), _resumo()])
        _mk_tentativa(self.base, 2, [_bash("ls"),
                                     {"tool": "Write", "input": {}, "is_error": False, "turno": 2},
                                     _resumo(veredito="PASS", motivo="stop_condition")])
        out = self._t()
        self.assertEqual(out["causa_dominante"], "PASS")
        self.assertEqual(out["tentativas"][-1]["veredito"], "PASS")

    def test_dir_vazio_exit_2(self):
        base = tempfile.mkdtemp()
        self.assertEqual(main([base]), 2)
        self.assertEqual(main([os.path.join(base, "nao-existe")]), 2)

    def test_deterministico(self):
        recs = [_bash("cat x", err=True, lat=0) for _ in range(4)] + [_resumo()]
        _mk_tentativa(self.base, 1, recs)
        a = json.dumps(triar(self.base), sort_keys=True)
        b = json.dumps(triar(self.base), sort_keys=True)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()