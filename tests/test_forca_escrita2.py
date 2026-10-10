"""FORCA-ESCRITA-02 — stream respeita tools, barreira na execução e
quebra de loop de Edit idêntico.

Cobertura:
1. _default_reader envia body["tools"] quando presente (fallback TOOLS).
2. Barreira: dentro da janela de força-escrita, tool_use fora de
   Write/Edit NÃO é executado — vira ERRO FORÇA-ESCRITA.
3. Barreira não bloqueia Write/Edit nem é ativa fora da janela.
4. Loop de Edit: repetição idêntica ganha aviso REPETIDO; outro Edit ou
   sucesso zera o contador.
"""
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bridge_sse  # noqa: E402
import harness  # noqa: E402

PRICES = {"models": {
    "z-ai/glm-5.3-flash": {"in": 0.15, "out": 0.5, "cache_read": 0.03},
}}

CONTRACT = """# CONTRATO TESTE seed={{SEED}}
```harness-stop
file alvo.txt
```
"""


def tool_use(i, name, inp):
    return {"type": "tool_use", "id": f"tu{i}", "name": name, "input": inp}


class FakeUlopen:
    """Captura o payload enviado e devolve um stream SSE mínimo."""

    def __init__(self):
        self.payload = None

    def __call__(self, req, timeout=300):
        self.payload = json.loads(req.data.decode())
        return io.BytesIO(b"data: [DONE]\n\n")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestStreamTools(unittest.TestCase):
    def test_default_reader_respeita_tools_do_body(self):
        fake = FakeUlopen()
        orig = urllib.request.urlopen
        urllib.request.urlopen = fake
        try:
            body = {"model": "m", "max_tokens": 10, "system": [],
                    "messages": [], "tools": [{"name": "Write"}, {"name": "Edit"}]}
            list(bridge_sse._default_reader(body))
        finally:
            urllib.request.urlopen = orig
        self.assertEqual([t["name"] for t in fake.payload["tools"]],
                         ["Write", "Edit"])

    def test_default_reader_fallback_para_tools_padrao(self):
        fake = FakeUlopen()
        orig = urllib.request.urlopen
        urllib.request.urlopen = fake
        try:
            body = {"model": "m", "max_tokens": 10, "system": [], "messages": []}
            list(bridge_sse._default_reader(body))
        finally:
            urllib.request.urlopen = orig
        names = {t["name"] for t in fake.payload["tools"]}
        self.assertEqual(names, {t["name"] for t in harness.TOOLS})


class ForcaBridge:
    """Roteiro por turno: lista de (tool_name, input). Registra tools."""

    def __init__(self, script):
        self.script = list(script)
        self.n = 0
        self.tools_por_turno = []

    def __call__(self, messages, system, ledger, model=None, tools=None):
        self.n += 1
        self.tools_por_turno.append(tools)
        name, inp = self.script.pop(0)
        d = {"model": model, "content": [tool_use(self.n, name, inp)],
             "stop_reason": "tool_use",
             "usage": {"input_tokens": 1000, "output_tokens": 100}}
        usd = ledger.add(d["model"], d["usage"])
        return d, usd, 0.01, 0


class Base(unittest.TestCase):
    def setUp(self):
        self._adv = harness.HARNESS_ADVISOR
        harness.HARNESS_ADVISOR = False
        self._forca = harness.FORCA_ESCRITA
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.prices = os.path.join(self.dir, "prices.json")
        json.dump(PRICES, open(self.prices, "w"))
        self.contract = os.path.join(self.dir, "contrato.md")
        open(self.contract, "w").write(CONTRACT)
        self.base = os.path.join(self.dir, "runs")

    def tearDown(self):
        harness.HARNESS_ADVISOR = self._adv
        harness.FORCA_ESCRITA = self._forca
        harness._reset_edit_fail_state()
        self.tmp.cleanup()

    def go(self, bridge, max_turns=20, **kw):
        return harness.run_mission(self.contract, self.base, 10.0, max_turns,
                                   seed=7, ledger=harness.Ledger(self.prices),
                                   bridge_fn=bridge, log=io.StringIO(),
                                   escada=False, **kw)

    def trail(self, s):
        return [json.loads(l) for l in open(s["trail"], encoding="utf-8")]


class TestBarreiraExecucao(Base):
    def test_bash_na_janela_forca_e_barrado(self):
        """(a) após ativação, Bash emitido pelo modelo NÃO executa: vira
        ERRO FORÇA-ESCRITA e o arquivo de efeito não é criado."""
        fb = ForcaBridge([("Bash", {"command": "ls -la /tmp | head"})] * 4
                         + [("Bash", {"command": "echo pwned > pwned.txt"})] * 2
                         + [("Write", {"path": "alvo.txt", "content": "ok"})])
        s = self.go(fb, max_turns=20)
        # o efeito do comando barrado não pode existir em lugar nenhum
        for root, _, files in os.walk(self.base):
            self.assertNotIn("pwned.txt", files)
        # e o trail registra os turnos de Bash como erro (barrados)
        errs = [e for e in self.trail(s)
                if e.get("tool") == "Bash" and e.get("is_error")]
        self.assertTrue(errs)

    def test_barreira_nao_bloqueia_write_na_janela(self):
        """(b) Write dentro da janela executa normalmente (PASS)."""
        fb = ForcaBridge([("Bash", {"command": "ls -la /tmp | head"})] * 4
                         + [("Write", {"path": "alvo.txt", "content": "pronto"})])
        s = self.go(fb, max_turns=20)
        self.assertEqual(s["veredito"], "PASS")

    def test_barreira_nao_bloqueia_edit_na_janela(self):
        """(c) Edit dentro da janela executa normalmente."""
        fb = ForcaBridge([("Write", {"path": "alvo.txt", "content": "v1\n"})]
                         + [("Bash", {"command": "ls -la /tmp | head"})] * 4
                         + [("Edit", {"path": "alvo.txt", "old_string": "v1",
                                      "new_string": "v2"})])
        s = self.go(fb, max_turns=20)
        self.assertEqual(s["veredito"], "PASS")

    def test_fora_da_janela_bash_executa(self):
        """(d) sem força-escrita ativa (run já escreveu), Bash executa."""
        fb = ForcaBridge([("Write", {"path": "nota.txt", "content": "x"})]
                         + [("Bash", {"command": "echo fora > alvo.txt"})] * 3)
        s = self.go(fb, max_turns=20)
        # o comando teve efeito real: alvo.txt criado pelo Bash no run_dir
        self.assertTrue(os.path.exists(os.path.join(s["run_dir"], "alvo.txt")))
        bash_evs = [e for e in self.trail(s) if e.get("tool") == "Bash"]
        self.assertTrue(bash_evs)
        self.assertFalse(any(e.get("is_error") for e in bash_evs))
        self.assertEqual(s["veredito"], "PASS")


class TestEditLoop(Base):
    def setUp(self):
        super().setUp()
        harness._reset_edit_fail_state()
        self.arq = os.path.join(self.dir, "alvo.txt")
        open(self.arq, "w").write("linha um\nlinha dois\n")

    def test_repeticao_identica_ganha_aviso(self):
        inp = {"path": self.arq, "old_string": "nao existe",
               "new_string": "x"}
        r1 = harness.run_tool("Edit", dict(inp), self.dir)
        r2 = harness.run_tool("Edit", dict(inp), self.dir)
        self.assertIn("old_string não encontrado", r1)
        self.assertNotIn("REPETIDO", r1)
        self.assertIn("REPETIDO 2x", r2)
        r3 = harness.run_tool("Edit", dict(inp), self.dir)
        self.assertIn("REPETIDO 3x", r3)

    def test_outro_edit_zera_contador(self):
        r1 = harness.run_tool("Edit", {"path": self.arq,
                                       "old_string": "nao existe A",
                                       "new_string": "x"}, self.dir)
        # outro Edit (old_string diferente) que também falha: zera e recomeça
        r2 = harness.run_tool("Edit", {"path": self.arq,
                                       "old_string": "nao existe B",
                                       "new_string": "x"}, self.dir)
        self.assertNotIn("REPETIDO", r2)
        # repetindo o B duas vezes: só na 2ª repetição aparece aviso
        r3 = harness.run_tool("Edit", {"path": self.arq,
                                       "old_string": "nao existe B",
                                       "new_string": "x"}, self.dir)
        self.assertIn("REPETIDO 2x", r3)

    def test_edit_bem_sucedido_zera_contador(self):
        harness.run_tool("Edit", {"path": self.arq, "old_string": "nao existe",
                                  "new_string": "x"}, self.dir)
        # Edit bem-sucedido zera
        r = harness.run_tool("Edit", {"path": self.arq, "old_string": "linha um",
                                      "new_string": "linha 1"}, self.dir)
        self.assertTrue(r.startswith("OK"))
        r2 = harness.run_tool("Edit", {"path": self.arq, "old_string": "nao existe",
                                       "new_string": "x"}, self.dir)
        self.assertNotIn("REPETIDO", r2)


if __name__ == "__main__":
    unittest.main()