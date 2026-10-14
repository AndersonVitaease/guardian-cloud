"""RD-HARN-RETRY-MEMORIA-01 — H3: tentativa N+1 recebe arquivos lidos/escritos e Edits falhos da tentativa anterior.

Dado um trail harness-trail.jsonl real de exemplo (eventos Read/Write/Edit/Bash),
o bloco_diagnostico da tentativa N+1 DEVE incluir:
  - linha "- arquivos lidos (N+1 recebe): ..." (Read + Bash de leitura via code_slice.sh)
  - linha "- arquivos escritos (N+1 recebe): ..." (Write/Edit com is_error false)
  - linha "- Edits falhos (N+1 evita): ..." (Edit com is_error true, com contagem)
Rollback por env: DIAG_MEMORIA=0 devolve o bloco SEM as seções novas (compat).
Fail-open: trail ausente/corrompido -> None (nunca derruba o retry).
"""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import diagnostico  # noqa: E402


def _ev(tool, inp, turno=1, is_error=False):
    return {"ts": "2026-10-10T18:00:00Z", "turno": turno, "tool": tool,
            "input": json.dumps(inp, ensure_ascii=False), "latencia_ms": 0,
            "custo_usd": 0.0, "bytes": 10, "is_error": is_error}


def _trail(recs):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return path


EXEMPLO = [
    {"ts": "t", "tool": "_inicio"},
    _ev("Bash", {"command": "bash /opt/mission-events/tools-bash/code_slice.sh scripts/diagnostico.py 1 120"}),
    _ev("Read", {"path": "tests/test_retry_decide.py"}),
    _ev("Write", {"path": "scripts/retry_memoria.py", "content_bytes": 900}),
    _ev("Edit", {"path": "scripts/diagnostico.py", "old_string": "x", "new_string": "y"}),
    _ev("Edit", {"path": "scripts/diagnostico.py", "old_string": "x", "new_string": "y"}, turno=2, is_error=True),
    _ev("Edit", {"path": "scripts/diagnostico.py", "old_string": "x", "new_string": "y"}, turno=3, is_error=True),
    {"ts": "t", "tool": "_resumo", "veredito": "FAIL", "motivo": "max_turns",
     "turnos": 5, "custo": {"usd": 0.01}, "stop_conditions": []},
]


class DiagnosticoMemoriaH3(unittest.TestCase):
    def test_bloco_inclui_lidos_escritos_e_edits_falhos(self):
        bloco = diagnostico.bloco_diagnostico(_trail(EXEMPLO))
        self.assertIsNotNone(bloco)
        self.assertIn("## DIAGNÓSTICO PRÉVIO (gerado)", bloco)
        self.assertIn("- arquivos lidos (N+1 recebe):", bloco)
        self.assertIn("scripts/diagnostico.py", bloco)
        self.assertIn("tests/test_retry_decide.py", bloco)
        self.assertIn("- arquivos escritos (N+1 recebe):", bloco)
        self.assertIn("scripts/retry_memoria.py", bloco)
        self.assertIn("- Edits falhos (N+1 evita):", bloco)
        self.assertIn("scripts/diagnostico.py (2x)", bloco)

    def test_lidos_dedup_preserva_ordem(self):
        recs = [_ev("Read", {"path": "a.py"}),
                _ev("Read", {"path": "a.py"}),
                _ev("Bash", {"command": "code_slice.sh b.py 1 9"})]
        bloco = diagnostico.bloco_diagnostico(_trail(recs))
        self.assertIn("a.py", bloco)
        self.assertIn("b.py", bloco)
        linha = [l for l in bloco.splitlines() if l.startswith("- arquivos lidos")][0]
        self.assertLess(linha.index("a.py"), linha.index("b.py"))
        self.assertEqual(linha.count("a.py"), 1)

    def test_rollback_por_env(self):
        with mock.patch.dict(os.environ, {"DIAG_MEMORIA": "0"}):
            bloco = diagnostico.bloco_diagnostico(_trail(EXEMPLO))
        self.assertIsNotNone(bloco)
        self.assertIn("## DIAGNÓSTICO PRÉVIO (gerado)", bloco)
        self.assertNotIn("arquivos lidos (N+1 recebe)", bloco)
        self.assertNotIn("Edits falhos (N+1 evita)", bloco)

    def test_trail_ausente_continua_none(self):
        self.assertIsNone(diagnostico.bloco_diagnostico("/tmp/nao-existe-ret-mem.jsonl"))


if __name__ == "__main__":
    unittest.main()
