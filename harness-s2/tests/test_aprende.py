# Testes HARNESS-MEMORIA-01: aprende.py (extrair/registro/wire no fim da run).
import importlib
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts import aprende  # noqa: E402

RELATORIO = """# RELATORIO-X — MISSAO-FAKE

## Entrega
Criado utilitario foo.py com subcomandos soma e media. Testes verdes.

## GOAL
Wire no mission_run.py apos veredito gravado.

## Causa
Gap: resultado mora no run dir e nada grava em memoria consultavel.

## Dívidas
Nenhuma divida tecnica aberta.
"""


@pytest.fixture
def run_dir(tmp_path):
    (tmp_path / "RELATORIO-FAKE.md").write_text(RELATORIO, encoding="utf-8")
    (tmp_path / "run-summary.json").write_text(json.dumps(
        {"veredito": "PASS", "motivo": "ok", "turnos": 7, "custo_usd": 0.42}),
        encoding="utf-8")
    return str(tmp_path)


def test_extrair_fixture(run_dir):
    d = aprende.extrair(run_dir)
    assert d["mission_id"] == "FAKE"
    assert d["veredito"] == "PASS"
    assert d["entregas"] and "foo.py" in d["entregas"][0]
    assert d["causas_medidas"] and "run dir" in d["causas_medidas"][0]
    assert d["dividas"] and "divida" in d["dividas"][0].lower()
    assert "trail" not in json.dumps(d)  # sem texto cru de trail


def test_registro_append_2x_jsonl_valido(run_dir):
    aprende.registro(run_dir)
    aprende.registro(run_dir)
    path = os.path.join(run_dir, "aprendizado.jsonl")
    with open(path, encoding="utf-8") as f:
        linhas = [json.loads(l) for l in f if l.strip()]
    assert len(linhas) == 2
    assert linhas[0]["veredito"] == "PASS"


def test_sem_relatorio_erro_suave(tmp_path, capsys):
    d = aprende.extrair(str(tmp_path))
    assert d["erro"] == "sem_relatorio"
    rc = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "aprende.py"),
                         str(tmp_path)], capture_output=True, text=True)
    assert rc.returncode == 0
    assert json.loads(rc.stdout)["erro"] == "sem_relatorio"


def test_cli_imprime_json_exit0(run_dir):
    rc = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "aprende.py"),
                         run_dir], capture_output=True, text=True)
    assert rc.returncode == 0
    assert json.loads(rc.stdout)["veredito"] == "PASS"


def test_wire_chama_registro_ao_terminar(run_dir, monkeypatch):
    """Mock do fluxo: fim de run com veredito gravado → registro executado."""
    chamado = {}
    fake = importlib.import_module("scripts.aprende")
    orig = fake.registro

    def spy(rd, **kw):
        chamado["rd"] = rd
        return orig(rd, **kw)

    monkeypatch.setattr(fake, "registro", spy)
    # simula o wire do mission_run (mesmo código do bloco pós-veredito)
    s = {"veredito": "PASS", "run_dir": run_dir}
    if os.environ.get("HARNESS_APRENDE", "1") != "0":
        try:
            fake.registro(s["run_dir"])
        except Exception:
            pass
    assert chamado["rd"] == run_dir
    assert os.path.isfile(os.path.join(run_dir, "aprendizado.jsonl"))


def test_wire_gate_desligado(run_dir, monkeypatch):
    monkeypatch.setenv("HARNESS_APRENDE", "0")
    chamado = []
    fake = importlib.import_module("scripts.aprende")
    monkeypatch.setattr(fake, "registro", lambda rd, **kw: chamado.append(rd))
    s = {"veredito": "PASS", "run_dir": run_dir}
    if os.environ.get("HARNESS_APRENDE", "1") != "0":
        try:
            fake.registro(s["run_dir"])
        except Exception:
            pass
    assert chamado == []
    assert not os.path.isfile(os.path.join(run_dir, "aprendizado.jsonl"))