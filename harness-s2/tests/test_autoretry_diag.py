"""DIAG-AUTORETRY-01 — testes de scripts/diagnostico.py + wiring no autoretry."""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import diagnostico  # noqa: E402
import scripts.autoretry as autoretry  # noqa: E402


def _escrever_trail(tmp_path, eventos):
    p = tmp_path / "harness-trail.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for e in eventos:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return str(p)


def _trail_fail(tmp_path):
    eventos = [
        {"turno": 1, "tool": "Bash", "input": {"command": "cd /x && " + "a" * 80},
         "custo_usd": 0.01},
        {"turno": 2, "tool": "Bash", "input": {"command": "cd /x && " + "a" * 80},
         "custo_usd": 0.01},
        {"turno": 3, "tool": "Bash", "input": {"command": "cd /x && " + "a" * 80},
         "custo_usd": 0.01},
        {"turno": 3, "tool": "Write", "input": {"file_path": "saida.txt", "content": "x"}},
        {"turno": 3, "tool": "_stop_check", "stop_state": {"0:file": True, "1:cmd": False}},
        {"turno": 4, "tool": "_resumo", "veredito": "FAIL", "motivo": "max_turns",
         "turnos": 4, "custo": {"usd": 0.03},
         "stop_conditions": [
             {"kind": "file", "path": "saida.txt", "ok": True},
             {"kind": "cmd", "cmd": "pytest -q", "ok": False}]},
    ]
    return _escrever_trail(tmp_path, eventos)


def test_analisar_campos(tmp_path):
    trail = _trail_fail(tmp_path)
    d = diagnostico.analisar(trail)
    assert d["veredito"] == "FAIL"
    assert d["motivo"] == "max_turns"
    assert d["turnos"] == 4
    assert d["custo_usd"] == pytest.approx(0.03)
    assert len(d["stop_conditions"]["ok"]) == 1
    pend = d["stop_conditions"]["pendentes"]
    assert len(pend) == 1 and pend[0]["nome"] == "pytest -q"
    assert d["comandos_repetidos"][0]["vezes"] == 3
    assert d["arquivo_mais_recente"] == "saida.txt"
    tools = [a["tool"] for a in d["ultimas_acoes"]]
    assert "Write" in tools and "_resumo" not in tools


def test_analisar_trail_ausente_e_corrompido(tmp_path):
    assert diagnostico.analisar(str(tmp_path / "nada.jsonl")) is None
    p = tmp_path / "ruim.jsonl"
    p.write_text("{quebrado\n", encoding="utf-8")
    assert diagnostico.analisar(str(p)) is None


def test_bloco_contem_campos(tmp_path):
    trail = _trail_fail(tmp_path)
    bloco = diagnostico.bloco_diagnostico(trail)
    assert "DIAGNÓSTICO PRÉVIO" in bloco
    assert "pytest -q" in bloco
    assert "FAIL" in bloco


def test_cli_exit_codes(tmp_path, capsys):
    trail = _trail_fail(tmp_path)
    assert diagnostico.main([trail]) == 0
    assert diagnostico.main([trail, "--json"]) == 0
    assert diagnostico.main([str(tmp_path / "nada.jsonl")]) == 1
    ruim = tmp_path / "ruim.jsonl"
    ruim.write_text("{quebrado\n", encoding="utf-8")
    assert diagnostico.main([str(ruim)]) == 1


def test_autoretry_usa_bloco_diagnostico(tmp_path, monkeypatch):
    """Wiring: FAIL no retry chama diagnostico.bloco_diagnostico do SOURCE module."""
    chamadas = []
    monkeypatch.setattr(diagnostico, "bloco_diagnostico",
                        lambda t: chamadas.append(t) or "BLOCO-FAKE")
    monkeypatch.setattr(autoretry.mission_run, "extrair_memoria",
                        lambda t: pytest.fail("fallback não deveria rodar"))

    def fake_run(mission, run_dir, budget, max_turns, seed=0, model=None,
                 bridge_fn=None, contract_prefix="", **kw):
        os.makedirs(run_dir, exist_ok=True)
        trail = os.path.join(run_dir, "harness-trail.jsonl")
        with open(trail, "w", encoding="utf-8") as f:
            f.write(json.dumps({"turno": 1, "tool": "_resumo", "veredito": "FAIL",
                                "motivo": "max_turns", "custo": {"usd": 0.01},
                                    "stop_conditions": [{"kind": "file", "path": "a.txt", "ok": True}]}) + "\n")
        return {"veredito": "FAIL", "run_dir": run_dir, "seed": seed,
                "custo": {"usd": 0.01}}

    monkeypatch.setattr(autoretry.harness, "run_mission", fake_run)
    monkeypatch.setattr(autoretry.harness, "MODEL", "fake")
    agregado = autoretry.rodar_com_retry("m.md", str(tmp_path), 1.0, 5, n_retries=1)
    assert len(chamadas) == 2  # 1x por tentativa FAIL (2 tentativas)
    assert agregado["tentativas"] == 2


def test_autoretry_fallback_quando_diagnostico_none(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostico, "bloco_diagnostico", lambda t: None)
    monkeypatch.setattr(autoretry.mission_run, "extrair_memoria", lambda t: "FALLBACK")

    def fake_run(mission, run_dir, budget, max_turns, seed=0, model=None,
                 bridge_fn=None, contract_prefix="", **kw):
        os.makedirs(run_dir, exist_ok=True)
        with open(os.path.join(run_dir, "harness-trail.jsonl"), "w") as f:
            f.write(json.dumps({"turno": 1, "tool": "_resumo", "veredito": "FAIL",
                                "motivo": "x", "custo": {"usd": 0.01}}) + "\n")
        return {"veredito": "FAIL", "run_dir": run_dir, "seed": seed,
                "custo": {"usd": 0.01}}

    monkeypatch.setattr(autoretry.harness, "run_mission", fake_run)
    monkeypatch.setattr(autoretry.harness, "MODEL", "fake")
    autoretry.rodar_com_retry("m.md", str(tmp_path), 1.0, 5, n_retries=1)
    # fallback rodou sem exceção — fail-open garantido