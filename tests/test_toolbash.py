"""Tool_bash — tools bash governadas via catálogo tools.json (RD-HARNESS-TOOLBASH-01).

Hermético: catálogo e scripts vivem em tmp, sem rede, sem /opt.
"""
import json
import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness  # noqa: E402


def make_catalog(dirpath, tools=None):
    """Catálogo + scripts fake em tmp. Retorna caminho do tools.json."""
    tools = tools or [
        {"name": "mission_cost", "command": "./mission_cost.sh", "args": "<missionId>",
         "description": "custo"},
        {"name": "flights", "command": "./flights.sh", "args": "", "description": "runs vivos"},
    ]
    with open(os.path.join(dirpath, "tools.json"), "w") as f:
        json.dump({"tools": tools}, f)
    with open(os.path.join(dirpath, "mission_cost.sh"), "w") as f:
        f.write('#!/bin/sh\nprintf \'{"ok":true,"custo_usd":0.01}\\n\'\n')
    with open(os.path.join(dirpath, "flights.sh"), "w") as f:
        f.write('#!/bin/sh\nprintf \'[]\\n\'\n')
    os.chmod(os.path.join(dirpath, "mission_cost.sh"), 0o755)
    os.chmod(os.path.join(dirpath, "flights.sh"), 0o755)
    return os.path.join(dirpath, "tools.json")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.catalog = make_catalog(self.dir)
        # nunca usar o catálogo real de /opt nestes testes
        self._old_dir = harness.TOOLS_BASH_DIR
        harness.TOOLS_BASH_DIR = self.dir

    def tearDown(self):
        harness.TOOLS_BASH_DIR = self._old_dir
        self.tmp.cleanup()

    def run_tb(self, inp, **kw):
        return harness.run_tool("tool_bash", inp, self.dir, **kw)


class TestCatalog(Base):
    def test_toolbash_existe_em_tools_com_enum_do_catalogo(self):
        self._old = harness.TOOLS
        try:
            harness.TOOLS = harness.build_tools()
            names = [t["name"] for t in harness.TOOLS]
            self.assertIn("tool_bash", names)
            tb = [t for t in harness.TOOLS if t["name"] == "tool_bash"][0]
            enum = tb["input_schema"]["properties"]["tool"].get("enum")
            self.assertIsNotNone(enum)
            self.assertEqual(sorted(enum), ["flights", "mission_cost"])
        finally:
            harness.TOOLS = self._old

    def test_catalogo_ausente_nao_registra_toolbash(self):
        harness.TOOLS_BASH_DIR = os.path.join(self.dir, "nao-existe")
        names = [t["name"] for t in harness.build_tools()]
        self.assertNotIn("tool_bash", names)
        self.assertIn("Bash", names)  # harness segue como hoje

    def test_catalogo_invalido_nao_registra_toolbash(self):
        harness.TOOLS_BASH_DIR = self.dir
        with open(self.catalog, "w") as f:
            f.write("{quebrado")
        names = [t["name"] for t in harness.build_tools()]
        self.assertNotIn("tool_bash", names)

    def test_env_harness_toolbash_0_desativa(self):
        old = os.environ.get("HARNESS_TOOLBASH")
        os.environ["HARNESS_TOOLBASH"] = "0"
        try:
            names = [t["name"] for t in harness.build_tools()]
            self.assertNotIn("tool_bash", names)
        finally:
            if old is None:
                os.environ.pop("HARNESS_TOOLBASH", None)
            else:
                os.environ["HARNESS_TOOLBASH"] = old


class TestRunTool(Base):
    def test_executa_script_permitido_e_trunca_4000(self):
        # script que devolve > 4000 chars
        big = os.path.join(self.dir, "big.sh")
        with open(big, "w") as f:
            f.write('#!/bin/sh\npython3 -c "print(\'x\'*9000)"\n')
        os.chmod(big, 0o755)
        with open(self.catalog, "w") as f:
            json.dump({"tools": [{"name": "big", "command": "./big.sh", "args": "",
                                  "description": "grande"}]}, f)
        out = self.run_tb({"tool": "big"})
        self.assertTrue(out.startswith("exit=0"))
        body = out.split("\n", 1)[1]
        self.assertLessEqual(len(body), 4000)
        self.assertEqual(len(body), 4000)

    def test_tool_fora_do_catalogo_erro_tipado(self):
        out = self.run_tb({"tool": "rm_rf"})
        self.assertTrue(out.startswith("ERRO"))
        self.assertIn("TOOL_NOT_IN_CATALOG", out)

    def test_args_caracteres_invalidos_erro_tipado(self):
        for bad in ["a; b", "x|y", "$(id)", "café", "-flag", "x" * 201]:
            # nota: whitespace (espaço/tab) é separador de args, não rejeitado
            out = self.run_tb({"tool": "mission_cost", "args": bad})
            self.assertTrue(out.startswith("ERRO"), f"args={bad!r} → {out!r}")
            self.assertIn("BAD_ARGS", out)

    def test_args_validos_executam_com_argv_sem_shell(self):
        out = self.run_tb({"tool": "mission_cost", "args": "RD-TOOLS-BASH-01A"})
        self.assertTrue(out.startswith("exit=0"))
        self.assertIn("custo_usd", out)

    def test_sem_shell_metacaractere_vira_erro_nao_executa(self):
        out = self.run_tb({"tool": "mission_cost", "args": "a;b"})
        self.assertIn("BAD_ARGS", out)

    def test_falha_do_script_erro_tipado_sem_crash(self):
        boom = os.path.join(self.dir, "boom.sh")
        with open(boom, "w") as f:
            f.write('#!/bin/sh\necho antes >&2\nexit 3\n')
        os.chmod(boom, 0o755)
        with open(self.catalog, "w") as f:
            json.dump({"tools": [{"name": "boom", "command": "./boom.sh", "args": "",
                                  "description": "falha"}]}, f)
        out = self.run_tb({"tool": "boom"})
        self.assertTrue(out.startswith("ERRO"))
        self.assertIn("SCRIPT_EXIT_3", out)

    def test_timeout_20s_erro_tipado(self):
        slow = os.path.join(self.dir, "slow.sh")
        with open(slow, "w") as f:
            f.write('#!/bin/sh\nsleep 30\n')
        os.chmod(slow, 0o755)
        with open(self.catalog, "w") as f:
            json.dump({"tools": [{"name": "slow", "command": "./slow.sh", "args": "",
                                  "description": "lento"}]}, f)
        out = self.run_tb({"tool": "slow"})  # run_tool default 120; handler usa 20
        self.assertTrue(out.startswith("ERRO"))

    def test_env_minimo_com_mission_state_dir(self):
        cap = os.path.join(self.dir, "env.sh")
        with open(cap, "w") as f:
            f.write('#!/bin/sh\nprintf "%s|%s\\n" "$MISSION_STATE_DIR" "${HOME:-none}"\n')
        os.chmod(cap, 0o755)
        with open(self.catalog, "w") as f:
            json.dump({"tools": [{"name": "envp", "command": "./env.sh", "args": "",
                                  "description": "env"}]}, f)
        old = os.environ.get("MISSION_STATE_DIR")
        os.environ.pop("MISSION_STATE_DIR", None)
        try:
            out = self.run_tb({"tool": "envp"})
        finally:
            if old is not None:
                os.environ["MISSION_STATE_DIR"] = old
        self.assertIn("/root/.hermes/mission-state|none", out)  # default, sem HOME


class TestSystemPrompt(Base):
    def test_prompt_instrui_tool_bash_quando_ativa(self):
        old = harness.TOOLS
        try:
            harness.TOOLS = harness.build_tools()
            s = harness.worker_system_prompt("/tmp/run-x", seed=7, contract="# CONTRATO\nx")
            self.assertIn("tool_bash", s)
        finally:
            harness.TOOLS = old

    def test_prompt_sem_tool_bash_quando_desativada(self):
        old = harness.TOOLS
        try:
            harness.TOOLS = harness.build_tools(enabled=False)
            s = harness.worker_system_prompt("/tmp/run-x", seed=7, contract="# CONTRATO\nx")
            self.assertNotIn("tool_bash", s)
        finally:
            harness.TOOLS = old


if __name__ == "__main__":
    unittest.main()


class TestBashShim(Base):
    def test_bash_com_json_toolbash_roteia_para_handler(self):
        # glm-flash às vezes chama Bash com o body JSON da tool_bash
        out = harness.run_tool("Bash", {"command": '{"tool":"mission_cost","args":"RD-1"}'},
                               self.dir)
        self.assertTrue(out.startswith("exit=0"))
        self.assertIn("custo_usd", out)

    def test_bash_json_com_command_nao_roteia(self):
        out = harness.run_tool("Bash", {"command": '{"command":"echo","tool":"x"}'}, self.dir)
        self.assertTrue("exit=" in out or out.startswith("ERRO"))
        self.assertNotIn("TOOL_NOT_IN_CATALOG", out)
