# Testes do adaptador missão-ops → harness (HARNESS-SPRINT4-01, item 1)
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adaptador import AdaptadorSetupError, adaptar_contrato


MISSAO_COM_BLOCO = """# MISSÃO X-01 — teste

**Componente:** /tmp/alvo

## Entregas
1. Fazer coisa.

## Provas
- `/usr/bin/python3 -m pytest tests/ -q` verde.

## Regras
budget US$ 1.5 para o loop.

```harness-stop
file entregavel.txt
cmd /usr/bin/python3 -c "import os; assert os.path.isfile('entregavel.txt')"
marker FEITO entregavel.txt
```

**consequence: true**
"""

MISSAO_SEM_BLOCO_DETERMINISTICA = """# MISSÃO Y-02 — sem bloco

## Entregas
1. Rodar suíte.

## Provas
- Suíte relevante verde: `/usr/bin/python3 -m pytest test/x.test.ts -q`

## Regras
Sem push/merge; budget US$ 2 para o loop; pane CLI trava 30min = PARE.
"""

MISSAO_SEM_BLOCO_NAO_DETERMINISTICA = """# MISSÃO Z-03 — prova subjetiva

## Entregas
1. Melhorar o design.

## Provas
- Design bonito e consistente (julgamento humano).

## Regras
budget US$ 1 para o loop.
"""


class TestAdaptador(unittest.TestCase):
    def test_bloco_inline_vence(self):
        c = adaptar_contrato(MISSAO_COM_BLOCO, cwd="/tmp/run-x")
        self.assertEqual([x["kind"] for x in c["stop_conditions"]],
                         ["file", "cmd", "marker"])
        self.assertEqual(c["budget_usd"], 1.5)
        self.assertEqual(c["max_turns"], 60)  # default

    def test_deriva_cmd_de_provas(self):
        c = adaptar_contrato(MISSAO_SEM_BLOCO_DETERMINISTICA, cwd="/tmp/run-y")
        kinds = [x["kind"] for x in c["stop_conditions"]]
        self.assertEqual(kinds, ["cmd"])
        self.assertIn("/usr/bin/python3 -m pytest test/x.test.ts",
                      c["stop_conditions"][0]["cmd"])
        self.assertEqual(c["budget_usd"], 2.0)

    def test_sem_prova_deterministica_falha_no_setup(self):
        with self.assertRaises(AdaptadorSetupError):
            adaptar_contrato(MISSAO_SEM_BLOCO_NAO_DETERMINISTICA, cwd="/tmp/run-z")

    def test_budget_default_quando_nao_declarado(self):
        m = MISSAO_SEM_BLOCO_DETERMINISTICA.replace("budget US$ 2 para o loop; ", "")
        c = adaptar_contrato(m, cwd="/tmp/run-w")
        self.assertEqual(c["budget_usd"], 1.0)  # default conservador

    def test_max_turns_override(self):
        c = adaptar_contrato(MISSAO_COM_BLOCO, cwd="/tmp/r", max_turns=25)
        self.assertEqual(c["max_turns"], 25)

    def test_harness_cwd_placeholder_substituido(self):
        m = MISSAO_COM_BLOCO.replace("file entregavel.txt",
                                     "file {{HARNESS_CWD}}/entregavel.txt")
        c = adaptar_contrato(m, cwd="/tmp/run-cwd")
        self.assertEqual(c["stop_conditions"][0]["path"], "/tmp/run-cwd/entregavel.txt")

    def test_cmd_relativo_ancora_no_cwd(self):
        c = adaptar_contrato(MISSAO_SEM_BLOCO_DETERMINISTICA, cwd="/tmp/run-a")
        cmd = c["stop_conditions"][0]["cmd"]
        self.assertIn("cd /tmp/run-a", cmd)  # cmd roda ancorado no cwd da run

    def test_mission_id_extraido(self):
        c = adaptar_contrato(MISSAO_COM_BLOCO, cwd="/tmp/r")
        self.assertEqual(c["mission"], "X-01")

    def test_contrato_sem_provas_falha_no_setup(self):
        m = "# MISSÃO W-04\n\n## Entregas\n1. Algo.\n"
        with self.assertRaises(AdaptadorSetupError):
            adaptar_contrato(m, cwd="/tmp/r")

    def test_adaptado_rodavel_pelo_harness(self):
        """O dict do adaptador alimenta run_mission sem retrabalho."""
        from harness import check_stop_conditions
        c = adaptar_contrato(MISSAO_COM_BLOCO, cwd="/tmp/run-int")
        ok, state = check_stop_conditions(c["stop_conditions"], c["cwd"])
        self.assertFalse(ok)  # nada cumprido ainda, mas avalia sem erro


if __name__ == "__main__":
    unittest.main()