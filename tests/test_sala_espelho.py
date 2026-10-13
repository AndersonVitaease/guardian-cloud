#!/usr/bin/env python3
"""GB-SALA-ESPELHO-02 — suite hermetica (unittest, stdlib).

Ciclo: nascimento (espelho gravado pelo despachar_missao) -> sala (/tmp/ag-live)
-> pouso (fechar_mirror renomeia para .espelho.pousado.json) -> sai da sala.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

FIXTURE = os.path.join(ROOT, "tests", "fixtures",
                       "TESTE-ESPELHO-20261012112709.espelho.json")


def _gravar_espelho(ag_live_dir, mid, tab):
    """Replica o bloco GB-SALA-ESPELHO-02 do despachar_missao.py (fail-open)."""
    try:
        os.makedirs(ag_live_dir, exist_ok=True)
        path = os.path.join(ag_live_dir, "%s.espelho.json" % mid)
        dados = {
            "id": mid,
            "tab_id": tab,
            "pane_id": tab,
            "workspace_id": tab.split(":", 1)[0],
            "status": "running",
            "started_at": "2026-10-13T08:24:57-03:00",
        }
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
        return True
    except Exception:
        return False


class TestSalaEspelho(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ag-live-test-")
        self.ag_live = os.path.join(self.tmp, "ag-live")

    def test_01_formato_do_fixture(self):
        """Espelho gravado no formato EXATO do fixture."""
        self.assertTrue(_gravar_espelho(self.ag_live, "MID-1", "w0:pabc"))
        with open(os.path.join(self.ag_live, "MID-1.espelho.json")) as f:
            dados = json.load(f)
        with open(FIXTURE) as f:
            fixture = json.load(f)
        self.assertEqual(sorted(dados), sorted(fixture))
        self.assertEqual(dados["id"], "MID-1")
        self.assertEqual(dados["tab_id"], "w0:pabc")
        self.assertEqual(dados["pane_id"], "w0:pabc")
        self.assertEqual(dados["workspace_id"], "w0")
        self.assertEqual(dados["status"], "running")
        self.assertIn("started_at", dados)

    def test_02_sobrescrita_em_retry(self):
        """Retry de despacho sobrescreve (sem duplicar session_start na ponte)."""
        self.assertTrue(_gravar_espelho(self.ag_live, "MID-2", "w1:px"))
        self.assertTrue(_gravar_espelho(self.ag_live, "MID-2", "w1:py"))
        with open(os.path.join(self.ag_live, "MID-2.espelho.json")) as f:
            dados = json.load(f)
        self.assertEqual(dados["tab_id"], "w1:py")
        arquivos = os.listdir(self.ag_live)
        self.assertEqual(arquivos, ["MID-2.espelho.json"])

    def test_03_fail_open_dir_ilegivel(self):
        """Escrita falha -> fail-open (False), sem levantar."""
        bloqueio = os.path.join(self.tmp, "arquivo")
        with open(bloqueio, "w") as f:
            f.write("x")
        # caminho "dir" que na verdade e um arquivo regular -> makedirs falha
        self.assertFalse(_gravar_espelho(bloqueio, "MID-3", "w2:pz"))

    def test_04_pouso_renomeia_e_sai_da_sala(self):
        """fechar_mirror renomeia para .pousado; ponte nao ve mais running."""
        self.assertTrue(_gravar_espelho(self.ag_live, "MID-4", "w3:pt"))
        resumo = os.path.join(self.tmp, "resumo-MID-4.json")
        with open(resumo, "w") as f:
            json.dump({"veredito": "PASSE"}, f)
        env = dict(os.environ, AG_LIVE_DIR=self.ag_live)
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "fechar_mirror.py"),
             "MID-4", "--resumo", resumo,
             "--state-dir", self.tmp],
            capture_output=True, text=True, env=env, cwd=ROOT)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["espelho_ag_live"]["acao"], "pousado")
        pousado = os.path.join(self.ag_live, "MID-4.espelho.pousado.json")
        self.assertTrue(os.path.isfile(pousado))
        # a ponte observa o rename: nao ha mais espelho running na sala
        self.assertFalse(os.path.isfile(
            os.path.join(self.ag_live, "MID-4.espelho.json")))
        with open(pousado) as f:
            self.assertEqual(json.load(f)["status"], "running")

    def test_05_fecho_sem_espelho_noop_tipado(self):
        """Fecho de missao sem espelho = noop tipado, fail-open."""
        resumo = os.path.join(self.tmp, "resumo-MID-5.json")
        with open(resumo, "w") as f:
            json.dump({"veredito": "FAIL"}, f)
        env = dict(os.environ, AG_LIVE_DIR=self.ag_live)
        proc = subprocess.run(
            [sys.executable, os.path.join(ROOT, "scripts", "fechar_mirror.py"),
             "MID-5", "--resumo", resumo,
             "--state-dir", self.tmp],
            capture_output=True, text=True, env=env, cwd=ROOT)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(out["espelho_ag_live"]["acao"], "noop")
        self.assertEqual(out["ok"], True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
    print("GB-SALA-ESPELHO-02-PROVA-OK")