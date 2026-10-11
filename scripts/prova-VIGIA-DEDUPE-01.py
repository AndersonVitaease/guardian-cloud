#!/usr/bin/env python3
"""Prova E2E VIGIA-DEDUPE-01: emite o fluxo duas vezes com o mesmo estado
e exige exatamente 1 'fim' no jsonl resultante."""
import importlib.util
import json
import os
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MARCA = "VIGIA-DEDUPE-01-PROVA-OK"


def _carregar():
    spec = importlib.util.spec_from_file_location(
        "vigia_run_prova", os.path.join(RAIZ, "scripts", "vigia_run.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    with tempfile.TemporaryDirectory() as td:
        jsonl = os.path.join(td, "vigia-PROVA.jsonl")
        os.environ["VIGIA_JSONL_PATH"] = jsonl
        mod = _carregar()
        mod._emit({"evento": "andamento", "turn": 17, "cost_usd": 0.42})
        mod._emit({"evento": "andamento", "turn": 17, "cost_usd": 0.42})
        mod._emit({"evento": "fim", "veredito": "OK", "tentativas": 1,
                   "turn": 19, "cost_usd": 0.9, "motivo": "prova"})
        mod2 = _carregar()
        mod2._emit({"evento": "andamento", "turn": 17, "cost_usd": 0.42})
        mod2._emit({"evento": "fim", "veredito": "OK", "tentativas": 1,
                    "turn": 19, "cost_usd": 0.9, "motivo": "prova"})
        mod2._emit({"evento": "fim", "veredito": "OK", "tentativas": 1,
                    "turn": 19, "cost_usd": 0.9, "motivo": "prova"})
        evs = [json.loads(l) for l in open(jsonl, encoding="utf-8") if l.strip()]
        fins = [e for e in evs if e.get("evento") == "fim"]
        ands = [e for e in evs if e.get("evento") == "andamento"]
        ok = len(fins) == 1 and len(ands) == 1
        saida = "%s\nfins=%d andamentos=%d total=%d\n" % (
            MARCA if ok else "VIGIA-DEDUPE-01-PROVA-FALHOU",
            len(fins), len(ands), len(evs))
        with open(os.path.join(RAIZ, "scripts", "prova-VIGIA-DEDUPE-01.out"),
                  "w", encoding="utf-8") as f:
            f.write(saida)
        print(saida.strip())
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
