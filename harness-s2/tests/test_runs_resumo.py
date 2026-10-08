# -*- coding: utf-8 -*-
"""Testes do CLI runs_resumo (dirs temporários fabricados)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from runs_resumo import resumo_runs  # noqa: E402


def _fabricar(base, missao, run_nome, resumo=None, trail_linhas=None):
    run_dir = os.path.join(base, missao, run_nome)
    os.makedirs(run_dir, exist_ok=True)
    linhas = trail_linhas if trail_linhas is not None else ([{"turno": 1, "tool": "outro"}] + ([resumo] if resumo else []))
    with open(os.path.join(run_dir, "harness-trail.jsonl"), "w", encoding="utf-8") as f:
        for l in linhas:
            f.write(json.dumps(l) + "\n")
    return run_dir


def _resumo(veredito="PASS", ts="2026-10-07T18:00:00Z", turnos=3, usd=0.01, sc="2/2"):
    return {"tool": "_resumo", "veredito": veredito, "ts": ts, "turnos": turnos,
            "custo": {"usd": usd}, "stop_conditions_cumpridas": sc}


def test_run_pass(tmp_path):
    _fabricar(str(tmp_path), "missao-x", "run-20261007-100000-seed1-1", _resumo())
    itens = resumo_runs(str(tmp_path))
    assert len(itens) == 1
    it = itens[0]
    assert it["veredito"] == "PASS"
    assert it["turnos"] == 3
    assert it["custo_usd"] == 0.01
    assert it["stop_conditions"] == "2/2"
    assert it["data_brt"].endswith("BRT")
    assert "15:00" in it["data_brt"]  # UTC 18:00 -> BRT 15:00


def test_run_em_andamento(tmp_path):
    _fabricar(str(tmp_path), "missao-y", "run-20261007-110000-seed2-2",
              trail_linhas=[{"turno": 1, "tool": "outro"}])
    itens = resumo_runs(str(tmp_path))
    assert len(itens) == 1
    assert itens[0]["veredito"] == "EM ANDAMENTO"
    assert itens[0]["turnos"] is None


def test_dir_vazio(tmp_path, capsys):
    itens = resumo_runs(str(tmp_path))
    assert itens == []
    # dir inexistente -> exit 1 com mensagem honesta
    import pytest
    with pytest.raises(SystemExit) as e:
        resumo_runs(str(tmp_path / "nao-existe"))
    assert e.value.code == 1


def test_ordenacao_mais_recente_primeiro(tmp_path):
    _fabricar(str(tmp_path), "m1", "run-20261007-090000-seed1-1", _resumo(ts="2026-10-07T12:00:00Z"))
    _fabricar(str(tmp_path), "m2", "run-20261007-120000-seed2-2", _resumo(ts="2026-10-07T15:00:00Z"))
    _fabricar(str(tmp_path), "m3", "run-20261007-150000-seed3-3", _resumo(ts="2026-10-07T18:00:00Z"))
    itens = resumo_runs(str(tmp_path))
    nomes = [os.path.basename(i["dir"]) for i in itens]
    assert nomes == ["run-20261007-150000-seed3-3", "run-20261007-120000-seed2-2", "run-20261007-090000-seed1-1"]


def test_limite(tmp_path):
    for i in range(5):
        _fabricar(str(tmp_path), f"m{i}", f"run-20261007-10000{i}-seed{i}-{i}", _resumo())
    assert len(resumo_runs(str(tmp_path), limite=2)) == 2
