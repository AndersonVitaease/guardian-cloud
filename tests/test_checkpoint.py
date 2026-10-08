import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import checkpoint  # noqa: E402

RESUMO = {
    "mission_id": "MISSAO-X",
    "veredito": "PAUSADA",
    "motivo": "max_turns",
    "turnos": 45,
    "custo": 1.23,
    "pendentes": ["cmd test -f RELATORIO.md", "cmd pytest -q"],
    "max_turns_sugerido": 60,
    "nota_janela": "janela nova",
    "bloco_diagnostico": "entregue: scripts/a.py verde",
}


def test_salvar_e_retomar(tmp_path):
    run_dir = tmp_path / "run"
    checkpoint.salvar(str(run_dir), RESUMO, "entregue: scripts/a.py verde")
    cp_path = run_dir / "CHECKPOINT.json"
    assert cp_path.exists()
    cp = json.loads(cp_path.read_text(encoding="utf-8"))
    assert cp["mission_id"] == "MISSAO-X"
    assert cp["veredito_anterior"] == "PAUSADA"
    assert cp["pendentes"] == RESUMO["pendentes"]
    assert cp["proxima_janela"]["max_turns_sugerido"] == 60
    prompt = checkpoint.retomar_prompt(str(cp_path))
    assert "## CHECKPOINT DA JANELA ANTERIOR" in prompt
    assert "MISSAO-X" in prompt
    for p in RESUMO["pendentes"]:
        assert p in prompt
    assert "NÃO REFAÇA o que está verde" in prompt
    assert "scripts/a.py verde" in prompt


def test_atomicidade_nunca_parcial(tmp_path):
    run_dir = tmp_path / "run"
    checkpoint.salvar(str(run_dir), RESUMO, "diag")
    # nenhum tmp sobrando e arquivo parseável
    sobras = [f for f in os.listdir(run_dir) if f.startswith(".checkpoint-")]
    assert sobras == []
    json.loads((run_dir / "CHECKPOINT.json").read_text(encoding="utf-8"))


def test_cli_salvar_e_retomar(tmp_path):
    resumo_path = tmp_path / "resumo.json"
    resumo_path.write_text(json.dumps(RESUMO), encoding="utf-8")
    run_dir = tmp_path / "run"
    py = sys.executable
    r = subprocess.run([py, "scripts/checkpoint.py", "salvar", str(run_dir), str(resumo_path)],
                       capture_output=True, text=True)
    assert r.returncode == 0
    r = subprocess.run([py, "scripts/checkpoint.py", "retomar", str(run_dir)],
                       capture_output=True, text=True)
    assert r.returncode == 0
    assert "CHECKPOINT DA JANELA ANTERIOR" in r.stdout
    assert "test -f RELATORIO.md" in r.stdout