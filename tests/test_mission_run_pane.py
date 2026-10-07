"""Sprint 6, entrega 3 — modo --pane do mission_run.py.

Unit-testa SÓ a MONTAGEM dos comandos herdr (argvs exatos), a falha honesta
com herdr indisponível e o stream da última linha do trail. A execução real
(tab create + send-text + espelho) não roda no sandbox — o herdr é
inacessível daqui e o canário da sprint roda SEM --pane (pane é do supervisor).
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import mission_run  # noqa: E402


class PaneMountTest(unittest.TestCase):
    def test_title_run_prefixo(self):
        self.assertEqual(mission_run.pane_title("HARNESS-SPRINT6-01"),
                         "RUN:HARNESS-SPRINT6-01")

    def test_mount_argv_tab_create(self):
        m = mission_run.pane_mount("M-1")
        self.assertEqual(m["tab_create"],
                         ["herdr", "tab", "create", "--label", "RUN:M-1"])
        self.assertEqual(m["title"], "RUN:M-1")

    def test_mount_argv_send_text_espelho_tail(self):
        m = mission_run.pane_mount("M-1")
        self.assertEqual(m["send_text"],
                         ["herdr", "pane", "send-text", "<TAB>",
                          "tail -n +1 -F <RUN>/harness-trail.jsonl\n"])

    def test_mount_usa_label_nao_title(self):
        # E2E achou: herdr tab create usa --label (não --title)
        m = mission_run.pane_mount("M-1")
        self.assertIn("--label", m["tab_create"])
        self.assertNotIn("--title", m["tab_create"])
        self.assertEqual(m["tab_create"][m["tab_create"].index("--label") + 1],
                         "RUN:M-1")

    def test_extract_pane_id_do_json(self):
        # E2E achou: herdr tab create devolve JSON com root_pane.pane_id
        out = '{"id":"cli:tab:create","result":{"root_pane":{"pane_id":"w8:pN","cwd":"/root"}}}'
        self.assertEqual(mission_run.extract_pane_id(out), "w8:pN")

    def test_extract_pane_id_json_quebrado_ou_vazio(self):
        # nunca levanta: vazio/lixo/JSON sem pane → None (runtime segue SEM espelho)
        for bad in ("", "lixo", "{}", '{"result":{}}', '{"result":{"root_pane":{}}}'):
            self.assertIsNone(mission_run.extract_pane_id(bad), repr(bad))

    def test_mount_nao_executa_nada(self):
        # montagem é pura: NENHUM subprocess no caminho
        with mock.patch.object(mission_run.subprocess, "run") as run:
            mission_run.pane_mount("M-1")
            run.assert_not_called()


class RequireHerdrTest(unittest.TestCase):
    def test_falha_honesta_sem_herdr(self):
        with mock.patch.object(mission_run.shutil, "which", return_value=None):
            with self.assertRaises(mission_run.PaneUnavailable) as ctx:
                mission_run.require_herdr()
            self.assertIn("herdr indisponível", str(ctx.exception))

    def test_ok_com_herdr(self):
        with mock.patch.object(mission_run.shutil, "which",
                               return_value="/usr/local/bin/herdr"):
            self.assertEqual(mission_run.require_herdr(), "/usr/local/bin/herdr")


class StreamTrailTest(unittest.TestCase):
    def test_ultima_linha_do_trail(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "run-1"))
            p = os.path.join(d, "run-1", "harness-trail.jsonl")
            open(p, "w").write('{"a":1}\n{"a":2}\n')
            self.assertEqual(mission_run.last_trail_line(d), {"a": 2})
            # trail ainda não existe → None (não levanta)
            self.assertIsNone(mission_run.last_trail_line(os.path.join(d, "nao-existe")))


if __name__ == "__main__":
    unittest.main()