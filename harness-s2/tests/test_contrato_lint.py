import json
import subprocess
import sys

sys.path.insert(0, "scripts")
import contrato_lint  # noqa: E402

BOM = """# MISSAO OK
## GOAL
1. `scripts/a.py`
2. `tests/test_a.py`
## harness-stop
```harness-stop
file RELATORIO.md
cmd test -f scripts/a.py
cmd python3 -m pytest tests -q
```
"""

RUINS = {
    "SEM_STOP": "# MISSAO\n## GOAL\nfaz coisas\n",
    "COND_FRAGIL_WC": "```harness-stop\ncmd test -f x | wc -l\n```",
    "COND_FRAGIL_TESTF": "```harness-stop\ncmd test -f\n```",
    "COND_FRAGIL_GREP": "```harness-stop\ncmd grep foo arquivo.txt\n```",
    "COND_GITHUB_URL": "```harness-stop\ncmd test \"$(git rev-parse origin/master)\" = abc\n```",
    "PROIBIDO_ROOT_PATH": "## GOAL\nescreva em /opt/mission/x.md\n```harness-stop\ncmd test -f x\n```",
}


def _codigos(texto):
    return {a["codigo"] for a in contrato_lint.lint(texto)}


def test_contrato_bom_sem_erros():
    achados = contrato_lint.lint(BOM)
    assert [a for a in achados if a["severidade"] == "erro"] == []


def test_sem_stop():
    assert "SEM_STOP" in _codigos(RUINS["SEM_STOP"])


def test_wc_l():
    assert "COND_FRAGIL" in _codigos(RUINS["COND_FRAGIL_WC"])


def test_test_f_sem_caminho():
    assert "COND_FRAGIL" in _codigos(RUINS["COND_FRAGIL_TESTF"])


def test_grep_sem_q():
    assert "COND_FRAGIL" in _codigos(RUINS["COND_FRAGIL_GREP"])


def test_origin_sem_lsremote():
    achados = contrato_lint.lint(RUINS["COND_GITHUB_URL"])
    assert "COND_GITHUB_URL" in {a["codigo"] for a in achados}
    assert all(a["severidade"] == "aviso" for a in achados if a["codigo"] == "COND_GITHUB_URL")


def test_root_path():
    assert "PROIBIDO_ROOT_PATH" in _codigos(RUINS["PROIBIDO_ROOT_PATH"])


def test_contexto_gigante():
    texto = BOM + "x" * 6100
    assert "CONTEXTO_GIGANTE" in _codigos(texto)


def test_cli_exit_codes(tmp_path):
    py = sys.executable
    bom = tmp_path / "bom.md"
    bom.write_text(BOM, encoding="utf-8")
    r = subprocess.run([py, "scripts/contrato_lint.py", str(bom)], capture_output=True, text=True)
    assert r.returncode == 0
    json.loads(r.stdout)
    ruim = tmp_path / "ruim.md"
    ruim.write_text(RUINS["COND_FRAGIL_WC"], encoding="utf-8")
    r = subprocess.run([py, "scripts/contrato_lint.py", str(ruim)], capture_output=True, text=True)
    assert r.returncode == 1
    json.loads(r.stdout)