"""Testes hermeticos do dedupe de emissao do vigia (VIGIA-DEDUPE-01)."""
import importlib.util
import json
import os
import sys

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _carregar(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "vigia_run_dedupe", os.path.join(RAIZ, "scripts", "vigia_run.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    jsonl = os.path.join(str(tmp_path), "vigia-TESTE.jsonl")
    monkeypatch.setenv("VIGIA_JSONL_PATH", str(jsonl))
    return mod, jsonl


def _ler(jsonl):
    if not os.path.exists(jsonl):
        return []
    return [json.loads(l) for l in open(jsonl, encoding="utf-8") if l.strip()]


def test_fim_duplicado_nao_emitido_2x(tmp_path, monkeypatch):
    mod, jsonl = _carregar(tmp_path, monkeypatch)
    ev = {"evento": "fim", "veredito": "OK", "tentativas": 1}
    mod._emit(dict(ev)); mod._emit(dict(ev)); mod._emit(dict(ev))
    fins = [e for e in _ler(jsonl) if e["evento"] == "fim"]
    assert len(fins) == 1


def test_andamento_mesmo_turn_custo_nao_reemitido(tmp_path, monkeypatch):
    mod, jsonl = _carregar(tmp_path, monkeypatch)
    ev = {"evento": "andamento", "turn": 17, "cost_usd": 0.42}
    mod._emit(dict(ev)); mod._emit(dict(ev)); mod._emit(dict(ev))
    ands = [e for e in _ler(jsonl) if e["evento"] == "andamento"]
    assert len(ands) == 1


def test_fim_veredito_diferente_e_emitido(tmp_path, monkeypatch):
    mod, jsonl = _carregar(tmp_path, monkeypatch)
    mod._emit({"evento": "fim", "veredito": "OK", "tentativas": 1})
    mod._emit({"evento": "fim", "veredito": "FAIL", "tentativas": 1})
    mod._emit({"evento": "fim", "veredito": "OK", "tentativas": 2})
    fins = [e for e in _ler(jsonl) if e["evento"] == "fim"]
    assert len(fins) == 3
    assert [e["veredito"] for e in fins] == ["OK", "FAIL", "OK"]
