import json

import pytest

from scripts.cache_stream import analisar


def _escrever(tmp_path, linhas):
    p = tmp_path / "janela.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for l in linhas:
            f.write(json.dumps(l) + "\n")
    return str(p)


def _ev(ts, tokens_in, cache_read, tokens_out=100, latency_ms=1000):
    return {"ts": ts, "event": "proxy_call", "tokens_in": tokens_in,
            "cache_read": cache_read, "tokens_out": tokens_out,
            "latency_ms": latency_ms}


def test_periodos_separados(tmp_path):
    p = _escrever(tmp_path, [
        _ev("2026-10-07T10:00:00Z", 1000, 800),
        _ev("2026-10-07T23:00:00Z", 1000, 0),
    ])
    r = analisar(p)
    assert r["antes"]["n_chamadas"] == 1
    assert r["depois"]["n_chamadas"] == 1
    assert r["antes"]["cache_read"] == 800
    assert r["depois"]["cache_read"] == 0


def test_pct_cache_bate(tmp_path):
    p = _escrever(tmp_path, [
        _ev("2026-10-07T10:00:00Z", 1000, 829),
        _ev("2026-10-07T10:01:00Z", 1000, 829),
    ])
    r = analisar(p)
    assert r["antes"]["pct_cache"] == 82.9


def test_custo_bate_numeros_redondos(tmp_path):
    p = _escrever(tmp_path, [
        _ev("2026-10-07T10:00:00Z", 1_000_000, 0, tokens_out=0, latency_ms=1),
    ])
    r = analisar(p)
    assert r["antes"]["custo_usd"] == pytest.approx(0.15, abs=1e-6)
    p2 = _escrever(tmp_path, [
        _ev("2026-10-07T10:00:00Z", 1_000_000, 1_000_000, tokens_out=0, latency_ms=1),
    ])
    r2 = analisar(p2)
    assert r2["antes"]["custo_usd"] == pytest.approx(0.03, abs=1e-6)


def test_sem_linhas_pos_flip_periodo_vazio(tmp_path):
    p = _escrever(tmp_path, [_ev("2026-10-07T10:00:00Z", 1000, 500)])
    r = analisar(p)
    assert r["antes"]["n_chamadas"] == 1
    assert r["depois"]["n_chamadas"] == 0
    assert r["depois"]["pct_cache"] == 0.0
    assert r["delta_custo_por_1000"] is None


def test_janela_vazia_erro_claro(tmp_path):
    p = _escrever(tmp_path, [])
    with pytest.raises(ValueError, match="[Jj]anela vazia"):
        analisar(p)


def test_delta_custo_por_1000(tmp_path):
    p = _escrever(tmp_path, [
        _ev("2026-10-07T10:00:00Z", 1_000_000, 1_000_000, tokens_out=0, latency_ms=1),
        _ev("2026-10-07T23:00:00Z", 1_000_000, 0, tokens_out=0, latency_ms=1),
    ])
    r = analisar(p)
    assert r["delta_custo_por_1000"] == pytest.approx(120.0, abs=0.01)