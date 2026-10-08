import json
import subprocess
import sys

import pytest

sys.path.insert(0, "scripts")
import requeue_guard  # noqa: E402

PY = "/usr/bin/python3"
CLI = "scripts/requeue_guard.py"


def _fila(tmp_path, linhas):
    p = tmp_path / "fila.jsonl"
    p.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return str(p)


def test_id_presente_decide_skip(tmp_path):
    f = _fila(tmp_path, [json.dumps({"id": "intent-a"})])
    d = requeue_guard.decidir_requeue(f, {"id": "intent-a"})
    assert d == {"requeue": False, "motivo": "intent-intent-a já na fila"}


def test_id_ausente_procede(tmp_path):
    f = _fila(tmp_path, [json.dumps({"id": "intent-a"})])
    d = requeue_guard.decidir_requeue(f, {"id": "intent-b"})
    assert d["requeue"] is True


def test_mesmo_id_3x_uma_decisao(tmp_path):
    linha = json.dumps({"id": "intent-x"})
    f = _fila(tmp_path, [linha, linha, linha])
    assert requeue_guard.ja_na_fila(f, "intent-x") is True
    assert requeue_guard.decidir_requeue(f, {"id": "intent-y"})["requeue"] is True


def test_linhas_corrompidas_ignoradas(tmp_path):
    f = _fila(tmp_path, ["{corrompida", "", json.dumps({"id": "intent-c"})])
    assert requeue_guard.ja_na_fila(f, "intent-c") is True


def test_arquivo_ausente_false(tmp_path):
    assert requeue_guard.ja_na_fila(str(tmp_path / "nao_existe.jsonl"), "z") is False


def test_cli_exit_3(tmp_path):
    f = _fila(tmp_path, [json.dumps({"id": "intent-d"})])
    r = subprocess.run([PY, CLI, "--fila", f, "--id", "intent-d"], capture_output=True)
    assert r.returncode == 3


def test_cli_json_parse(tmp_path):
    f = _fila(tmp_path, [json.dumps({"id": "intent-e"})])
    r = subprocess.run([PY, CLI, "--fila", f, "--id", "intent-e"], capture_output=True)
    out = json.loads(r.stdout.decode())
    assert out == {"ja_na_fila": True, "requeue": False}


def test_match_exato_id_completo(tmp_path):
    f = _fila(tmp_path, [json.dumps({"id": "intent-tenant-foundation-01"})])
    assert requeue_guard.ja_na_fila(f, "intent-tenant-foundation-01") is True
    assert requeue_guard.ja_na_fila(f, "intent-tenant-foundation-0") is False
    assert requeue_guard.ja_na_fila(f, "intent-tenant-foundation-011") is False


def test_cli_exit_0_quando_procede(tmp_path):
    f = _fila(tmp_path, [])
    r = subprocess.run([PY, CLI, "--fila", f, "--id", "novo"], capture_output=True)
    assert r.returncode == 0
    assert json.loads(r.stdout.decode())["requeue"] is True