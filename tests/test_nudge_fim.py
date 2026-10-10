"""NUDGE-FIM-01 — perto do fim do orcamento de turnos o harness injeta UMA vez
um aviso deterministico (sem LLM): parar de explorar, escrever o que falta e
COMMITAR com o id da missao no assunto. Origem (09/10): workers de codigo
deixam o resultado sem commit / vagueiam ate o fim e o supervisor precisa fechar.

Regra: restantes = max(2, ceil(max_turns * NUDGE_FIM_PCT)); ao fim do turno T com
max_turns - T == restantes (e a run ainda nao terminou) injeta o nudge na janela
(mesmo mecanismo do advisor: win.add(turn, [texto '(harness)'], nudge=...)) e
emite evento de trail tool='_nudge_fim' com 'turno' e 'restantes'. Uma vez so.
"""
import io
import json
import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import harness  # noqa: E402

PRICES = {"models": {"z-ai/glm-5.3-flash": {"in": 0.15, "out": 0.5, "cache_read": 0.03}}}

CONTRACT = """# MISSÃO NUDGE-TESTE-9 — contrato de teste seed={{SEED}}
```harness-stop
file alvo.txt
```
"""


def tool_use(i, name, inp):
    return {"type": "tool_use", "id": f"tu{i}", "name": name, "input": inp}


class Bridge:
    """Explora (Bash) em todos os turnos, exceto os listados em escreve_em
    (1-based) onde faz Write que satisfaz a stop. Guarda as mensagens de cada chamada."""

    def __init__(self, escreve_em=()):
        self.escreve_em = set(escreve_em)
        self.n = 0
        self.vistas = []

    def __call__(self, messages, system, ledger, model=None):
        self.n += 1
        self.vistas.append(json.dumps(messages, ensure_ascii=False))
        if self.n in self.escreve_em:
            tu = tool_use(self.n, "Write", {"path": "alvo.txt", "content": "pronto"})
        else:
            tu = tool_use(self.n, "Bash", {"command": "echo explorando"})
        d = {"model": model, "content": [tu], "stop_reason": "tool_use",
             "usage": {"input_tokens": 1000, "output_tokens": 100}}
        usd = ledger.add(d["model"], d["usage"])
        return d, usd, 0.01, 0


class Base(unittest.TestCase):
    def setUp(self):
        self._adv = harness.HARNESS_ADVISOR
        harness.HARNESS_ADVISOR = False
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.prices = os.path.join(self.dir, "prices.json")
        json.dump(PRICES, open(self.prices, "w"))
        self.contract = os.path.join(self.dir, "contrato.md")
        open(self.contract, "w").write(CONTRACT)
        self.base = os.path.join(self.dir, "runs")

    def tearDown(self):
        harness.HARNESS_ADVISOR = self._adv
        self.tmp.cleanup()

    def go(self, bridge, max_turns):
        # vagueio=False: o teste cobre so o nudge, nao o abort antecipado
        return harness.run_mission(self.contract, self.base, 10.0, max_turns, seed=7,
                                   ledger=harness.Ledger(self.prices), bridge_fn=bridge,
                                   log=io.StringIO(), escada=False, vagueio=False)

    def eventos(self, s, tool):
        return [json.loads(l) for l in open(s["trail"], encoding="utf-8")
                if json.loads(l).get("tool") == tool]


class TestNudgeFim(Base):
    def test_constante_e_default(self):
        self.assertTrue(harness.NUDGE_FIM)
        self.assertAlmostEqual(harness.NUDGE_FIM_PCT, 0.2)

    def test_dispara_uma_vez_no_turno_certo(self):
        b = Bridge()
        s = self.go(b, max_turns=10)
        ev = self.eventos(s, "_nudge_fim")
        restantes = max(2, math.ceil(10 * harness.NUDGE_FIM_PCT))
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["restantes"], restantes)
        self.assertEqual(ev[0]["turno"], 10 - restantes)

    def test_nudge_chega_ao_modelo_so_depois_do_gatilho(self):
        b = Bridge()
        self.go(b, max_turns=10)
        # chamadas 1..8 (antes do fim do turno 8) nao veem o aviso; a 9a vê
        for i in range(0, 8):
            self.assertNotIn("NUDGE-FIM", b.vistas[i], f"chamada {i + 1}")
        self.assertIn("NUDGE-FIM", b.vistas[8])

    def test_texto_manda_commitar_com_id_da_missao(self):
        b = Bridge()
        self.go(b, max_turns=10)
        v = b.vistas[8]
        self.assertIn("NUDGE-TESTE-9", v)
        self.assertIn("commit", v.lower())

    def test_nao_dispara_se_run_termina_antes(self):
        b = Bridge(escreve_em={3})   # Write no turno 3 -> PASS
        s = self.go(b, max_turns=10)
        self.assertEqual(s["veredito"], "PASS")
        self.assertEqual(self.eventos(s, "_nudge_fim"), [])

    def test_piso_de_2_turnos_em_run_curta(self):
        b = Bridge()
        s = self.go(b, max_turns=5)   # ceil(5*0.2)=1 -> piso 2
        ev = self.eventos(s, "_nudge_fim")
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]["restantes"], 2)
        self.assertEqual(ev[0]["turno"], 3)

    def test_desligado_por_atributo(self):
        old = harness.NUDGE_FIM
        harness.NUDGE_FIM = False
        try:
            b = Bridge()
            s = self.go(b, max_turns=10)
        finally:
            harness.NUDGE_FIM = old
        self.assertEqual(self.eventos(s, "_nudge_fim"), [])
        for v in b.vistas:
            self.assertNotIn("NUDGE-FIM", v)


if __name__ == "__main__":
    unittest.main()
