# -*- coding: utf-8 -*-
"""Testes do relatorio_dia.py — runs FABRICADAS em tmp dirs."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

from relatorio_dia import relatorio_do_dia  # noqa: E402

DIA1 = "2026-10-06"
DIA2 = "2026-10-07"


def _resumo(ts, veredito="PASS", motivo="stop_condition", turnos=3,
            usd=0.001, lat=None, run_dir=None):
    d = {
        "ts": ts, "turno": turnos, "tool": "_resumo",
        "veredito": veredito, "motivo": motivo, "turnos": turnos,
        "custo": {"calls": turnos, "in": 100, "out": 50, "cache": 0,
                  "usd": usd},
        "stop_conditions_cumpridas": "2/2",
        "latencia_ms": lat or {"p50": 1000, "p99": 2000, "max": 2000},
    }
    if run_dir:
        d["run_dir"] = run_dir
    return d


def _fabricar(base, missao, nome, resumo):
    run_dir = os.path.join(base, missao, nome)
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "harness-trail.jsonl"), "w",
              encoding="utf-8") as f:
        if resumo is not None:
            f.write(json.dumps(resumo, ensure_ascii=False) + "\n")
    return run_dir


@pytest.fixture
def base_tmp(tmp_path):
    base = tmp_path / "runs"
    base.mkdir()
    # dia 1: 2 runs (1 PASS, 1 FAIL com motivo)
    _fabricar(str(base), "missao-a", "run-20261006-100000-seed1-1",
              _resumo("2026-10-06T13:00:00Z", "PASS", usd=0.001,
                      lat={"p50": 1000, "p99": 2000, "max": 2000}))
    _fabricar(str(base), "missao-a", "run-20261006-110000-seed2-2",
              _resumo("2026-10-06T14:00:00Z", "FAIL", motivo="testes_vermelhos",
                      usd=0.002, lat={"p50": 3000, "p99": 4000, "max": 4000},
                      run_dir=str(base / "missao-a" / "run-20261006-110000-seed2-2")))
    # dia 2: 1 PASS + 1 em andamento (sem resumo)
    _fabricar(str(base), "missao-b", "run-20261007-090000-seed3-3",
              _resumo("2026-10-07T12:00:00Z", "PASS", usd=0.0035,
                      lat={"p50": 500, "p99": 900, "max": 900}))
    _fabricar(str(base), "missao-b", "run-20261007-100000-seed4-4", None)
    return str(base)


def test_cabecalho_data_brt_e_totais(base_tmp):
    txt = relatorio_do_dia(base_tmp, dia=DIA1)
    assert "2026-10-06" in txt
    assert "terça-feira" in txt
    assert "Totais: 2 runs | PASS 1 | FAIL 1" in txt


def test_tabela_com_n_mais_1_linhas(base_tmp):
    txt = relatorio_do_dia(base_tmp, dia=DIA1)
    linhas_tab = [l for l in txt.splitlines() if l.startswith("|")]
    # header + separador + N linhas de dados (N=2)
    assert len(linhas_tab) == 2 + 2


def test_fails_com_causa(base_tmp):
    txt = relatorio_do_dia(base_tmp, dia=DIA1)
    assert "## FAILs do dia" in txt
    assert "testes_vermelhos" in txt
    assert "run-20261006-110000-seed2-2" in txt


def test_dia_vazio_sem_runs(base_tmp, capsys):
    txt = relatorio_do_dia(base_tmp, dia="2026-01-01")
    assert "SEM RUNS" in txt


def test_latencias_consolidadas(base_tmp):
    txt = relatorio_do_dia(base_tmp, dia=DIA1)
    # p50 de [1000, 3000] = 2000; p99 de [2000, 4000] = 3980; max = 4000
    assert "p50 2000 ms" in txt
    assert "p99 3980 ms" in txt
    assert "max 4000 ms" in txt


def test_custo_total_virgula_ptbr(base_tmp):
    txt = relatorio_do_dia(base_tmp, dia=DIA1)
    # 0.001 + 0.002 = 0.003 -> "$ 0,00300"
    assert "$ 0,00300" in txt


def test_em_andamento_sem_resumo(base_tmp):
    txt = relatorio_do_dia(base_tmp, dia=DIA2)
    assert "EM ANDAMENTO" in txt
    assert "Totais: 2 runs | PASS 1 | FAIL 0" in txt


def test_out_escreve_arquivo(base_tmp, tmp_path):
    out = tmp_path / "rel.md"
    relatorio_do_dia(base_tmp, dia=DIA1, out=str(out))
    assert out.exists()
    assert "FAILs do dia" in out.read_text(encoding="utf-8")
