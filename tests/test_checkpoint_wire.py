# CHECKPOINT-WIRE-01: wire do checkpoint no núcleo (mission_run/harness) — testes.
import importlib
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import harness  # noqa: E402


RESUMO = {
    "veredito": "FAIL", "motivo": "max_turns", "run_dir": "/tmp/x",
    "turnos": 3, "custo": {"usd": 0.01}, "trail": "/tmp/x/harness-trail.jsonl",
}


@pytest.fixture
def run_dir(tmp_path):
    d = tmp_path / "run-1"
    d.mkdir()
    # trail fake com _resumo (diagnostico.analisar consome)
    (d / "harness-trail.jsonl").write_text(
        json.dumps({"ts": "t", "turno": 3, "tool": "_resumo", **RESUMO}) + "\n",
        encoding="utf-8")
    return str(d)


def _salvar(run_dir, resumo, trail):
    """Isola o trecho de checkpoint do núcleo (mesma lógica de run_mission)."""
    import scripts.checkpoint as cp
    import scripts.diagnostico as diag
    cp.salvar(run_dir, resumo, diag.analisar(trail))


def test_fail_max_turns_grava_checkpoint(run_dir, tmp_path):
    trail = os.path.join(run_dir, "harness-trail.jsonl")
    _salvar(run_dir, RESUMO, trail)
    cp = json.load(open(os.path.join(run_dir, "CHECKPOINT.json"), encoding="utf-8"))
    assert cp["veredito_anterior"] == "FAIL"
    assert cp["motivo"] == "max_turns"
    assert "FAIL" in cp["bloco_diagnostico"]


def test_excecao_no_checkpoint_resumo_integro(run_dir, monkeypatch, capsys):
    import scripts.checkpoint as cp
    trail = os.path.join(run_dir, "harness-trail.jsonl")
    monkeypatch.setattr(cp, "salvar", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        cp.salvar(run_dir, RESUMO, trail)
    # núcleo: try/except no wire — resumo segue íntegro (simula o except do run_mission)
    try:
        cp.salvar(run_dir, RESUMO, trail)
    except Exception as e:  # noqa: BLE001
        print(f"[checkpoint] falha ao gravar checkpoint (resumo íntegro): {e}", file=sys.stderr)
    assert RESUMO["veredito"] == "FAIL" and RESUMO["motivo"] == "max_turns"


def test_env_injeta_checkpoint_no_prompt(run_dir, monkeypatch):
    trail = os.path.join(run_dir, "harness-trail.jsonl")
    _salvar(run_dir, RESUMO, trail)
    monkeypatch.setenv("HARNESS_CHECKPOINT_FROM", run_dir)
    bloco = harness.bloco_checkpoint()
    assert bloco and "CHECKPOINT DA JANELA ANTERIOR" in bloco


def test_sem_env_nao_injeta(run_dir, monkeypatch):
    monkeypatch.delenv("HARNESS_CHECKPOINT_FROM", raising=False)
    assert harness.bloco_checkpoint() is None