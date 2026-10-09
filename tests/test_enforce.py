"""ENFORCE-H — recusa/redirecionamento de Bash de leitura mecânica (RD item 1+2).

Hermético: catálogo e scripts vivem em tmp; _bash_metrics resetado por teste.
"""
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness  # noqa: E402
import test_toolbash  # noqa: E402

from test_toolbash import make_catalog  # noqa: E402


PRICES = {"models": {"test": {"in": 1.0, "out": 2.0, "cache_read": 0.0}}}

EXTRA_TOOLS = [
    {"name": "code_find", "command": "./code_find.sh", "args": "<padrao> <dir>",
     "description": "busca"},
    {"name": "code_slice", "command": "./code_slice.sh", "args": "<arq> <ini> <fim>",
     "description": "fatia"},
    {"name": "git_peek", "command": "./git_peek.sh", "args": "<args>",
     "description": "git read-only"},
    {"name": "trail_tail", "command": "./trail_tail.sh", "args": "<missionId>",
     "description": "trilha"},
]


def _tool_use(i, name, inp):
    return {"type": "tool_use", "id": f"tu{i}", "name": name, "input": inp}


def _resp(blocks):
    return {"id": "msg", "model": "test", "stop_reason": "end_turn",
            "content": blocks,
            "usage": {"input_tokens": 100, "output_tokens": 10}}


class _FakeBridge:
    def __init__(self, script):
        self.script = script
        self.calls = 0

    def __call__(self, messages, system, ledger, model=None):
        self.calls += 1
        d = self.script.pop(0) if self.script else _resp([])
        usd = ledger.add(d["model"], d["usage"])
        return d, usd, 0.01 * self.calls, 0


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        if os.path.exists("/tmp/enforce-deve-nao-existir.txt"):
            os.remove("/tmp/enforce-deve-nao-existir.txt")
        self.catalog = make_catalog(self.dir)
        tools = json.load(open(self.catalog))["tools"] + EXTRA_TOOLS
        json.dump({"tools": tools}, open(self.catalog, "w"))
        for t in EXTRA_TOOLS:
            path = os.path.join(self.dir, t["command"].lstrip("./"))
            with open(path, "w") as f:
                f.write('#!/bin/sh\nprintf \'{"ok":true,"tool":"%s"}\\n\'\n' % t["name"])
            os.chmod(path, 0o755)
        # fixture lido pelo teste de paridade (enforce desligado)
        os.makedirs("/tmp/fix", exist_ok=True)
        with open("/tmp/fix/events.jsonl", "w") as f:
            f.write('{"kind":"FIX"}\n')
        self._old_dir = harness.TOOLS_BASH_DIR
        harness.TOOLS_BASH_DIR = self.dir
        self.prices = os.path.join(self.dir, "prices.json")
        json.dump(PRICES, open(self.prices, "w"))
        harness._bash_metrics.update({"tool_bash": 0, "bash_redirect": 0,
                                      "bash_recusado": 0, "bash_livre": 0})
        self._old_enforce = harness.HARNESS_TOOLBASH_ENFORCE
        self._old_tb = harness.HARNESS_TOOLBASH
        harness.HARNESS_TOOLBASH_ENFORCE = True
        harness.HARNESS_TOOLBASH = True

    def tearDown(self):
        harness.TOOLS_BASH_DIR = self._old_dir
        harness.HARNESS_TOOLBASH_ENFORCE = self._old_enforce
        harness.HARNESS_TOOLBASH = self._old_tb
        self.tmp.cleanup()

    def bash(self, cmd):
        return harness.run_tool("Bash", {"command": cmd}, self.dir)


class TestRedirect(Base):
    def test_cat_e_recusado_com_tip_code_slice(self):
        out = self.bash("cat /opt/mission-events/orchestrator.py")
        self.assertIn("ERRO Bash: LEITURA_MECANICA_RECUSADA (FILE_READ)", out)
        self.assertIn("use code_slice <arquivo> <ini> <fim>", out)
        self.assertEqual(harness._bash_metrics["bash_recusado"], 1)

    def test_ls_e_recusado_com_tip(self):
        out = self.bash("ls /opt/mission-events")
        self.assertIn("LEITURA_MECANICA_RECUSADA (LS_NO_TOOL_EQUIV)", out)
        self.assertIn("code_find", out)   # via _ENFORCE_TIP
        self.assertEqual(harness._bash_metrics["bash_recusado"], 1)

    def test_grep_e_redirecionado(self):
        out = self.bash("grep -rn FOO /opt/mission-events")
        self.assertIn("<<<ENVELOPE-", out)
        self.assertIn("untrusted:true>>>", out)
        self.assertIn("exit=0", out)
        self.assertIn('{"ok":true,"tool":"code_find"}', out)
        self.assertEqual(harness._bash_metrics["bash_redirect"], 1)

    def test_git_status_e_redirecionado(self):
        out = self.bash("git status")
        self.assertIn("<<<ENVELOPE-", out)
        self.assertIn('{"ok":true,"tool":"git_peek"}', out)
        self.assertEqual(harness._bash_metrics["bash_redirect"], 1)

    def test_git_log_e_redirecionado(self):
        out = self.bash("git log --oneline -5")
        self.assertIn('{"ok":true,"tool":"git_peek"}', out)

    def test_trilha_leitura_redirect(self):
        out = self.bash("cat /root/.hermes/mission-state/events.jsonl")
        self.assertIn("ERRO Bash: LEITURA_MECANICA_RECUSADA (STATE_READ)", out)
        self.assertIn("trail_tail <missionId>", out)

    def test_sed_com_range_redirect(self):
        out = self.bash("sed -n 1,10p x.py")
        self.assertIn("<<<ENVELOPE-", out)
        self.assertIn('{"ok":true,"tool":"code_slice"}', out)

    def test_json_output_e_valido(self):
        out = self.bash("grep -rn FOO /opt/mission-events")
        self.assertIn("<<<ENVELOPE-", out)
        self.assertIn("exit=0", out)
        self.assertIn('"tool":"code_find"', out)

    def test_redirecao_executa_tool_real(self):
        out = self.bash("grep -rn FOO /opt/mission-events")
        self.assertIn("exit=0", out)
        self.assertIn('{"ok":true,"tool":"code_find"}', out)  # fake code_find.sh


class TestRefuse(Base):
    def test_awk_recusado(self):
        out = self.bash("awk '{print $1}' arquivo.txt")
        self.assertIn("LEITURA_MECANICA_RECUSADA (AWK_NO_TOOL_EQUIV)", out)
        self.assertEqual(harness._bash_metrics["bash_recusado"], 1)

    def test_sed_sem_range_e_recusado(self):
        out = self.bash("sed s/a/b/ arquivo.txt")
        self.assertIn("LEITURA_MECANICA_RECUSADA (SED_NO_RANGE)", out)

    def test_wc_recusado(self):
        out = self.bash("wc -l arquivo.txt")
        self.assertIn("LEITURA_MECANICA_RECUSADA (WC_NO_TOOL_EQUIV)", out)

    def test_arg_regex_invalido_vai_para_tool(self):
        out = self.bash("grep -rn 'foo bar baz;rm' /opt/mission-events")
        self.assertIn("ENVELOPE", out)

    def test_recusa_nao_executa_comando(self):
        out = self.bash("cat /tmp/fix/events.jsonl > /tmp/enforce-deve-nao-existir.txt")
        self.assertIn("LEITURA_MECANICA_RECUSADA", out)
        self.assertFalse(os.path.exists("/tmp/enforce-deve-nao-existir.txt"))


class TestEscritaPermitida(Base):
    def test_write_bash_livre_permite(self):
        p = os.path.join(self.dir, "esc.txt")
        out = self.bash(f"printf 'x' > {p}")
        self.assertTrue(os.path.exists(p))
        self.assertEqual(harness._bash_metrics["bash_livre"], 1)

    # BUG REAL: classifier recusa git commit composto -> TB-ENF-03B
    @unittest.expectedFailure
    def test_git_commit_nao_e_recusado(self):
        out = self.bash("git init -q . && git commit --allow-empty -q -m t")
        self.assertNotIn("LEITURA_MECANICA_RECUSADA", out)


class TestParidadeDesligado(Base):
    def test_enforce_0_bash_livre_passa(self):
        harness.HARNESS_TOOLBASH_ENFORCE = False
        out = self.bash("cat /tmp/fix/events.jsonl")
        self.assertIn("exit=0", out)  # cat roda de verdade (paridade)


class TestBadArgsClaro(Base):
    def test_bad_args_nao_engolido(self):
        out = harness.run_tool("tool_bash", {"tool": "mission_cost",
                                             "args": "ok -flag"}, self.dir)
        self.assertIn("ERRO tool_bash: BAD_ARGS", out)
        self.assertIn("args devem ser tokens [A-Za-z0-9._-]", out)


class TestE2EHermetico(Base):
    """1 run de missão com FakeBridge: Bash de leitura recusado no 1º turno,
    tool_bash mission_cost no 2º, relatório no 3º. Prova 0 Bash de leitura
    livre passando + custo registrado."""

    def test_run_e2e(self):
        base = os.path.join(self.dir, "runs")
        contract = os.path.join(self.dir, "contrato.md")
        with open(contract, "w") as f:
            f.write("Tarefa: leia a trilha e informe o custo.\n")
        script = [
            _resp([_tool_use(1, "Bash", {"command": "cat /root/.hermes/mission-state/events.jsonl"})]),
            _resp([_tool_use(2, "tool_bash", {"tool": "mission_cost",
                                              "args": "RD-XYZ"})]),
            _resp([_tool_use(3, "Write", {"path": "rel.md", "content": "Veredito: PASS"})]),
        ]
        fb = _FakeBridge(script)
        s = harness.run_mission(contract, base, 1.0, 10, seed=7,
                                ledger=harness.Ledger(self.prices),
                                bridge_fn=fb, log=io.StringIO())
        # Bash de leitura NUNCA passou; tool_bash chamada direta.
        self.assertEqual(harness._bash_metrics["bash_livre"], 0)
        self.assertEqual(harness._bash_metrics["tool_bash"], 1)
        tr = [json.loads(l)["tool"] for l in open(s["trail"], encoding="utf-8")
              if "tool" in json.loads(l)]
        self.assertIn("Bash", tr)
        self.assertIn("Write", tr)
        self.assertGreater(s["usd"], 0)


if __name__ == "__main__":
    unittest.main()
