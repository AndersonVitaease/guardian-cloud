"""Suíte do harness v2 — sem rede: bridge falso injetado via bridge_fn."""
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness  # noqa: E402

PRICES = {"models": {"z-ai/glm-5.3-flash": {"in": 0.15, "out": 0.5, "cache_read": 0.03}}}

CONTRACT = """# CONTRATO TESTE seed={{SEED}}
```harness-stop
# comentário ignorado
file ok.txt
cmd test "$(cat ok.txt)" = ok
marker PASS rel.md
```
"""


def tool_use(i, name, inp):
    return {"type": "tool_use", "id": f"tu{i}", "name": name, "input": inp}


def resp(content, stop="tool_use", inp=1000, out=200):
    return {"model": "z-ai/glm-5.3-flash", "content": content, "stop_reason": stop,
            "usage": {"input_tokens": inp, "output_tokens": out}}


class FakeBridge:
    """Devolve respostas roteirizadas e grava o que recebeu (messages/system)."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def __call__(self, messages, system, ledger, model=None):
        self.calls.append({"messages": json.loads(json.dumps(messages)), "system": system})
        d = self.script.pop(0) if self.script else resp([{"type": "text", "text": "fim"}], "end_turn")
        usd = ledger.add(d["model"], d["usage"])
        return d, usd, 0.01 * len(self.calls), 0


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.prices = os.path.join(self.dir, "prices.json")
        json.dump(PRICES, open(self.prices, "w"))
        self.contract = os.path.join(self.dir, "contrato.md")
        open(self.contract, "w").write(CONTRACT)
        self.base = os.path.join(self.dir, "runs")

    def tearDown(self):
        self.tmp.cleanup()

    def run_with(self, script, budget=1.0, max_turns=10, seed=7, **kw):
        fb = FakeBridge(script)
        s = harness.run_mission(self.contract, self.base, budget, max_turns, seed=seed,
                                ledger=harness.Ledger(self.prices), bridge_fn=fb,
                                log=io.StringIO(), **kw)
        return s, fb

    def trail(self, s):
        return [json.loads(line) for line in open(s["trail"], encoding="utf-8")]


HAPPY = [
    resp([tool_use(1, "Write", {"path": "ok.txt", "content": "ok"})]),
    resp([{"type": "text", "text": "agora o relatório"},
          tool_use(2, "Write", {"path": "rel.md", "content": "Veredito: PASS"})]),
]


class TestStopConditions(Base):
    def test_parse(self):
        conds = harness.parse_stop_conditions(CONTRACT)
        self.assertEqual([c["kind"] for c in conds], ["file", "cmd", "marker"])
        self.assertEqual(conds[2], {"kind": "marker", "marker": "PASS", "path": "rel.md"})

    def test_sem_bloco_nunca_cumpre(self):
        self.assertEqual(harness.parse_stop_conditions("# nada"), [])
        self.assertEqual(harness.check_stop_conditions([], self.dir), (False, {}))

    def test_check_parcial_e_total(self):
        conds = harness.parse_stop_conditions(CONTRACT)
        done, st = harness.check_stop_conditions(conds, self.dir)
        self.assertFalse(done)
        self.assertEqual(st, {"0:file": False, "1:cmd": False, "2:marker": False})
        open(os.path.join(self.dir, "ok.txt"), "w").write("ok")
        done, st = harness.check_stop_conditions(conds, self.dir)
        self.assertFalse(done)
        self.assertTrue(st["0:file"] and st["1:cmd"])
        open(os.path.join(self.dir, "rel.md"), "w").write("x PASS")
        self.assertTrue(harness.check_stop_conditions(conds, self.dir)[0])

    def test_arquivo_vazio_nao_conta(self):
        open(os.path.join(self.dir, "ok.txt"), "w").close()
        conds = [{"kind": "file", "path": "ok.txt"}]
        self.assertFalse(harness.check_stop_conditions(conds, self.dir)[0])


class TestWindow(unittest.TestCase):
    def fill(self, w, n):
        for t in range(1, n + 1):
            a = [{"type": "text", "text": f"passo {t}"}, tool_use(t, "Bash", {"command": f"echo {t}"})]
            w.add(t, a, [{"id": f"tu{t}", "tool": "Bash", "input": {"command": f"echo {t}"},
                          "content": f"exit=0\n{t}", "is_error": False}])

    def test_compacta_antigos_em_sumario(self):
        w = harness.Window(raw_window=3)
        self.fill(w, 8)
        msgs = w.messages("KICK")
        self.assertEqual(len(msgs), 1 + 2 * 3)
        self.assertIn("SUMÁRIO", msgs[0]["content"])
        self.assertIn("t1 Bash", msgs[0]["content"])
        self.assertIn("t5 assistente: passo 5", msgs[0]["content"])
        self.assertNotIn("t6 ", msgs[0]["content"])   # t6..t8 estão crus

    def test_pares_tool_use_tool_result_integros(self):
        w = harness.Window(raw_window=4)
        self.fill(w, 9)
        msgs = w.messages("KICK")
        roles = [m["role"] for m in msgs]
        self.assertEqual(roles, ["user"] + ["assistant", "user"] * 4)
        for a, u in zip(msgs[1::2], msgs[2::2]):
            ids = [b["id"] for b in a["content"] if b["type"] == "tool_use"]
            self.assertEqual(ids, [b["tool_use_id"] for b in u["content"]])

    def test_tamanho_limitado(self):
        w = harness.Window(raw_window=2, max_summary=10)
        self.fill(w, 200)
        self.assertEqual(len(w.summary_lines), 10)
        self.assertIn("omitidas", w.messages("K")[0]["content"])
        self.assertLess(len(json.dumps(w.messages("K"))), 6000)

    def test_resultado_grande_truncado(self):
        w = harness.Window(raw_window=2)
        w.add(1, [tool_use(1, "Read", {"path": "x"})],
              [{"id": "tu1", "tool": "Read", "input": {}, "content": "a" * 50000, "is_error": False}])
        c = w.messages("K")[2]["content"][0]["content"]
        self.assertLess(len(c), harness.MAX_TOOL_CHARS + 100)
        self.assertIn("truncados", c)

    def test_turno_sem_tool_vira_nudge(self):
        w = harness.Window()
        w.add(1, [{"type": "text", "text": "acabei"}], nudge="continue X")
        self.assertEqual(w.messages("K")[2]["content"], [{"type": "text", "text": "continue X"}])


class TestBackoff(unittest.TestCase):
    def setUp(self):
        self.orig = harness.call_bridge_once
        self.sleeps = []

    def tearDown(self):
        harness.call_bridge_once = self.orig

    def ledger(self):
        led = harness.Ledger.__new__(harness.Ledger)
        led.prices = PRICES["models"]
        led.in_tok = led.out_tok = led.cache_tok = 0
        led.cost, led.calls = 0.0, []
        return led

    def test_falha_3x_depois_fail_honesto(self):
        n = []

        def boom(*a):
            n.append(1)
            raise ConnectionError("down")
        harness.call_bridge_once = boom
        with self.assertRaises(harness.BridgeError) as cm:
            harness.call_bridge([], "", self.ledger(), sleep=self.sleeps.append)
        self.assertEqual(len(n), 3)                 # exatamente 3 tentativas — nunca martelada
        self.assertEqual(self.sleeps, [1, 2])       # backoff 2^n entre tentativas
        self.assertIn("down", str(cm.exception))

    def test_recupera_na_segunda(self):
        seq = [ConnectionError("x"), (resp([], "end_turn"), 0.5)]

        def flaky(*a):
            r = seq.pop(0)
            if isinstance(r, Exception):
                raise r
            return r
        harness.call_bridge_once = flaky
        led = self.ledger()
        d, usd, dt, retries = harness.call_bridge([], "", led, sleep=self.sleeps.append)
        self.assertEqual((retries, self.sleeps, len(led.calls)), (1, [1], 1))
        self.assertGreater(usd, 0)

    def test_bridge_error_vira_fail_na_run(self):
        def dead(messages, system, ledger, model=None):
            raise harness.BridgeError("HTTPError: 503")
        with tempfile.TemporaryDirectory() as d:
            c = os.path.join(d, "c.md")
            open(c, "w").write(CONTRACT)
            json.dump(PRICES, open(os.path.join(d, "p.json"), "w"))
            s = harness.run_mission(c, d, 1.0, 5, ledger=harness.Ledger(os.path.join(d, "p.json")),
                                    bridge_fn=dead, log=io.StringIO())
        self.assertEqual(s["veredito"], "FAIL")
        self.assertTrue(s["motivo"].startswith("bridge_error"))


class TestRunLoop(Base):
    def test_pass_por_stop_condition(self):
        s, fb = self.run_with(HAPPY)
        self.assertEqual((s["veredito"], s["motivo"], s["turnos"]), ("PASS", "stop_condition", 2))
        self.assertEqual(s["stop_conditions_cumpridas"], "3/3")
        self.assertGreater(s["custo"]["usd"], 0)
        # contrato SEMPRE no topo (system) com seed substituído
        for c in fb.calls:
            self.assertIn("CONTRATO TESTE seed=7", c["system"])
        # 2ª chamada carrega o tool_result do 1º turno
        self.assertEqual(fb.calls[1]["messages"][2]["content"][0]["tool_use_id"], "tu1")

    def test_trilha_estruturada(self):
        s, _ = self.run_with(HAPPY)
        rows = self.trail(s)
        llm = [r for r in rows if r["tool"] == "llm"]
        self.assertEqual(len(llm), 2)
        for r in llm:
            for k in ("ts", "turno", "latencia_ms", "custo_usd", "bytes"):
                self.assertIn(k, r)
        writes = [r for r in rows if r["tool"] == "Write"]
        self.assertEqual(writes[0]["bytes"], len("OK wrote ok.txt (2 bytes)"))
        self.assertEqual(writes[0]["input"], {"path": "ok.txt", "content_bytes": 2})
        self.assertTrue(os.path.isabs(rows[0]["run_dir"]))
        ticks = [r for r in rows if r["tool"] == "_stop_check"]
        self.assertEqual(ticks[0]["stop_tick"], ["0:file", "1:cmd"])
        self.assertEqual(ticks[1]["stop_tick"], ["2:marker"])
        self.assertEqual(rows[-1]["tool"], "_resumo")
        self.assertEqual(rows[-1]["veredito"], "PASS")
        self.assertIn("p99", rows[-1]["latencia_ms"])

    def test_budget_abort(self):
        loop = [resp([tool_use(i, "Bash", {"command": "true"})], inp=100000, out=0)
                for i in range(50)]
        s, fb = self.run_with(loop, budget=0.05, max_turns=50)   # 0.015 USD/turno
        self.assertEqual((s["veredito"], s["motivo"]), ("FAIL", "budget_excedido"))
        self.assertEqual(len(fb.calls), 4)                         # aborta ao cruzar o teto
        self.assertGreaterEqual(s["custo"]["usd"], 0.05)

    def test_max_turns(self):
        loop = [resp([tool_use(i, "Bash", {"command": "true"})]) for i in range(10)]
        s, fb = self.run_with(loop, max_turns=3)
        self.assertEqual((s["veredito"], s["motivo"], len(fb.calls)), ("FAIL", "max_turns", 3))

    def test_parou_sem_stop_condition(self):
        s, fb = self.run_with([], max_stalls=2)
        self.assertEqual((s["veredito"], s["motivo"], len(fb.calls)),
                         ("FAIL", "parou_sem_stop_condition", 2))
        # o 2º turno recebeu o nudge com as pendências
        self.assertIn("pendentes", fb.calls[1]["messages"][2]["content"][0]["text"])

    def test_janela_limitada_em_run_longa(self):
        loop = [resp([tool_use(i, "Bash", {"command": f"echo {i}"})]) for i in range(30)]
        s, fb = self.run_with(loop, max_turns=30)
        self.assertLessEqual(len(fb.calls[-1]["messages"]), 1 + 2 * harness.RAW_WINDOW)
        self.assertIn("SUMÁRIO", fb.calls[-1]["messages"][0]["content"])


class TestIsolamento(Base):
    def test_cada_run_cwd_novo_e_vazio(self):
        s1, _ = self.run_with(HAPPY)
        s2, fb2 = self.run_with([])            # 2ª run não enxerga artefatos da 1ª
        self.assertNotEqual(s1["run_dir"], s2["run_dir"])
        self.assertTrue(os.path.isfile(os.path.join(s1["run_dir"], "ok.txt")))
        self.assertFalse(os.path.exists(os.path.join(s2["run_dir"], "ok.txt")))
        self.assertEqual(s2["veredito"], "FAIL")
        self.assertIn(s2["run_dir"], fb2.calls[0]["system"])

    def test_make_run_dir_nunca_reusa(self):
        ds = {harness.make_run_dir(self.base, 1) for _ in range(5)}
        self.assertEqual(len(ds), 5)
        for d in ds:
            self.assertEqual(os.listdir(d), [])

    def test_tools_confinadas_ao_cwd(self):
        d = harness.make_run_dir(self.base, 0)
        out = harness.run_tool("Write", {"path": "../fora.txt", "content": "x"}, d)
        self.assertTrue(out.startswith("ERRO: PermissionError"))
        self.assertFalse(os.path.exists(os.path.join(self.base, "fora.txt")))
        self.assertTrue(harness.run_tool("Read", {"path": "/etc/hostname"}, d).startswith("ERRO"))
        self.assertTrue(harness.run_tool("Write", {"path": "sub/a.txt", "content": "y"}, d).startswith("OK"))
        self.assertEqual(harness.run_tool("Read", {"path": "sub/a.txt"}, d), "y")

    def test_edit_e_bash(self):
        d = harness.make_run_dir(self.base, 0)
        harness.run_tool("Write", {"path": "a.txt", "content": "foo bar"}, d)
        self.assertEqual(harness.run_tool("Edit", {"path": "a.txt", "old_string": "zzz", "new_string": "q"}, d),
                         "ERRO: old_string não encontrado")
        harness.run_tool("Edit", {"path": "a.txt", "old_string": "foo", "new_string": "baz"}, d)
        out = harness.run_tool("Bash", {"command": "cat a.txt; echo; basename \"$(pwd)\""}, d)
        self.assertEqual(out, f"exit=0\nbaz bar\n{os.path.basename(d)}")


class TestUtil(unittest.TestCase):
    def test_pctl(self):
        v = list(range(1, 101))
        self.assertEqual(harness.pctl(v, 50), 51)
        self.assertEqual(harness.pctl(v, 99), 99)
        self.assertEqual(harness.pctl([], 50), 0)
        self.assertEqual(harness.pctl([5], 99), 5)

    def test_ledger_preco_glm(self):
        led = harness.Ledger.__new__(harness.Ledger)
        led.prices = PRICES["models"]
        led.in_tok = led.out_tok = led.cache_tok = 0
        led.cost, led.calls = 0.0, []
        usd = led.add("z-ai/glm-5.3-flash", {"input_tokens": 1_000_000, "output_tokens": 1_000_000})
        self.assertAlmostEqual(usd, 0.65)


# ---------------------------------------------------------------- sprint 6

class Sprint6StopCheckTolerante(unittest.TestCase):
    """Entrega 1: stop-check tolerante a formato de reporter + escape de ^."""

    def test_marker_regex_casa_os_3_formatos(self):
        rx = harness.marker_regex("fail 0")
        for fmt in ("# fail 0", "ℹ fail 0", "✖ 0"):
            self.assertTrue(rx.search(fmt), fmt)

    def test_marker_regex_escape_de_circunflexo(self):
        # ^ declarado vira âncora de linha (escape automático), nunca literal
        rx = harness.marker_regex("^fail 0")
        self.assertTrue(rx.search("ℹ pass 3\nℹ fail 0\n"))  # engata em alguma linha
        self.assertFalse(rx.search("xx fail 0"))              # não casa no meio da linha

    def test_marker_regex_nao_casa_se_falso(self):
        rx = harness.marker_regex("fail 0")
        self.assertFalse(rx.search("✖ 2"))
        self.assertFalse(rx.search("pass 12"))

    def test_marker_cond_arquivo_tolerante(self):
        conds = [{"kind": "marker", "marker": "fail 0", "path": "r.txt"}]
        for fmt in ("# fail 0", "ℹ fail 0", "✖ 0"):
            with tempfile.TemporaryDirectory() as d:
                open(os.path.join(d, "r.txt"), "w").write(f"blabla\n{fmt}\nfim\n")
                done, state = harness.check_stop_conditions(conds, d)
                self.assertTrue(state["0:marker"], fmt)
                self.assertTrue(done)

    def test_parse_cmdout(self):
        text = "```harness-stop\nfile ok.txt\ncmdout fail 0 :: cat run-report.txt\n```\n"
        conds = harness.parse_stop_conditions(text)
        self.assertEqual(conds[0], {"kind": "file", "path": "ok.txt"})
        self.assertEqual(conds[1], {"kind": "cmdout", "marker": "fail 0",
                                     "cmd": "cat run-report.txt"})

    def test_cmdout_engata_nos_3_formatos(self):
        # mesmo cmd, 3 formatos de reporter: stop engata nos 3
        for fmt in ("# fail 0", "ℹ fail 0", "✖ 0"):
            conds = [{"kind": "cmdout", "marker": "fail 0", "cmd": f"echo '{fmt}'"}]
            with tempfile.TemporaryDirectory() as d:
                done, state = harness.check_stop_conditions(conds, d)
                self.assertTrue(state["0:cmdout"], fmt)
                self.assertTrue(done)

    def test_cmdout_exige_exit_zero(self):
        conds = [{"kind": "cmdout", "marker": "fail 0",
                  "cmd": "echo 'ℹ fail 0'; exit 3"}]
        with tempfile.TemporaryDirectory() as d:
            done, state = harness.check_stop_conditions(conds, d)
            self.assertFalse(state["0:cmdout"])
            self.assertFalse(done)

    def test_cmdout_casa_contra_saida_bruta_multilinha(self):
        conds = [{"kind": "cmdout", "marker": "^fail 0",
                  "cmd": "printf 'ℹ pass 3\\nℹ fail 0\\n'"}]
        with tempfile.TemporaryDirectory() as d:
            done, state = harness.check_stop_conditions(conds, d)
            self.assertTrue(state["0:cmdout"])


if __name__ == "__main__":
    unittest.main()
