# FECHO-AUTONOMO-01: testes do pacote de fecho.
import json
import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import fecho  # noqa: E402

CONTRATO = """# MISSAO TESTE-FECHO

```harness-stop
file PROGRESS.md
```
"""


@pytest.fixture
def run_dir(tmp_path):
    d = tmp_path / "run"
    d.mkdir()
    (d / "PROGRESS.md").write_text("t1 ok\n", encoding="utf-8")
    (d / "run-summary.json").write_text(json.dumps(
        {"veredito": "PASS", "motivo": "stop_conditions", "turnos": 3,
         "custo_usd": 0.12}), encoding="utf-8")
    (d / "RELATORIO-TESTE-FECHO.md").write_text(
        "## Motivo\nFeito.\n## Entregas\n- fecho.py\n", encoding="utf-8")
    return d


@pytest.fixture
def mission_path(tmp_path):
    p = tmp_path / "missao-teste.md"
    p.write_text(CONTRATO, encoding="utf-8")
    return p


def _suite(verde):
    return {"verde": verde, "passed": 1 if verde else 0,
            "failed": 0 if verde else 1, "rc": 0 if verde else 1}


def test_pronto_true(run_dir, mission_path):
    with mock.patch.object(fecho, "_suite", return_value=_suite(True)):
        f = fecho.verificar(str(run_dir), str(mission_path))
    assert f["pronto"] is True
    assert f["veredito"] == "PASS"
    assert f["conditions"]["todas_ok"] is True
    assert list(f["conditions"]["estado"].values()) == [True]
    assert f["aprendizado"]["veredito"] == "PASS"
    assert (run_dir / "fecho.json").is_file()
    gravado = json.loads((run_dir / "fecho.json").read_text(encoding="utf-8"))
    assert gravado["pronto"] is True


def test_condicao_impossivel(run_dir, tmp_path):
    p = tmp_path / "missao-impossivel.md"
    p.write_text("```harness-stop\nfile NUNCA-EXISTE.md\n```\n", encoding="utf-8")
    with mock.patch.object(fecho, "_suite", return_value=_suite(True)):
        f = fecho.verificar(str(run_dir), str(p))
    assert f["pronto"] is False
    assert f["conditions"]["todas_ok"] is False
    assert list(f["conditions"]["estado"].values()) == [False]


def test_suite_vermelha(run_dir, mission_path):
    with mock.patch.object(fecho, "_suite", return_value=_suite(False)):
        f = fecho.verificar(str(run_dir), str(mission_path))
    assert f["pronto"] is False
    assert f["suite"]["verde"] is False


def test_resumo_ausente_erro_suave(run_dir, mission_path):
    (run_dir / "run-summary.json").unlink()
    with mock.patch.object(fecho, "_suite", return_value=_suite(True)):
        f = fecho.verificar(str(run_dir), str(mission_path))
    assert f["resumo_ausente"] is True
    assert f["veredito"] is None
    assert f["pronto"] is True  # stop-conditions + suíte definem pronto


def test_suite_subprocess_real(run_dir, mission_path, tmp_path):
    # suíte fake via subprocess: true → verde; false → vermelha
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_ok.py").write_text("def test_x():\n    assert True\n")
    s = fecho._suite(repo=str(repo))
    assert s["verde"] is True and s["passed"] == 1
    (repo / "tests" / "test_ok.py").write_text("def test_x():\n    assert False\n")
    s = fecho._suite(repo=str(repo))
    assert s["verde"] is False and s["failed"] == 1


def test_wire_chamado_no_fim(run_dir, mission_path):
    # wire: mission_run chama fecho.verificar após o aprende (mock)
    import mission_run
    with mock.patch.object(fecho, "verificar",
                           return_value={"pronto": True}) as mv, \
         mock.patch.dict(os.environ, {"HARNESS_APRENDE": "0"}):
        mission_run._fecho_salvar({"run_dir": str(run_dir),
                                 "mission": str(mission_path)})
    mv.assert_called_once_with(str(run_dir), str(mission_path))


def test_cli_exit_code(run_dir, mission_path, capsys):
    with mock.patch.object(fecho, "_suite", return_value=_suite(True)):
        assert fecho.main(["fecho.py", str(run_dir), str(mission_path)]) == 0
    with mock.patch.object(fecho, "_suite", return_value=_suite(False)):
        assert fecho.main(["fecho.py", str(run_dir), str(mission_path)]) == 1
    out = capsys.readouterr().out
    assert '"pronto"' in out