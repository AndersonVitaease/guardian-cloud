import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import fila_dedupe  # noqa: E402

PY = "/usr/bin/python3"
SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "fila_dedupe.py")


def _escrever(path, n_dupes=785, extras=None):
    line = json.dumps({"id": "intent-tenant-foundation-01", "op": "x"})
    lines = [line] + [line] * n_dupes
    lines += extras or []
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lines


def test_785_dupes_colapsa_para_2(tmp_path):
    f = tmp_path / "fila.jsonl"
    _escrever(f, n_dupes=784, extras=[json.dumps({"id": "outro-01"})])
    res = fila_dedupe.dedupe(str(f))
    assert res["antes"] == 786
    assert res["unicos"] == 2
    assert res["duplicadas"] == 784
    assert res["corrompidas"] == 0


def test_dry_run_nao_escreve(tmp_path):
    f = tmp_path / "fila.jsonl"
    _escrever(f)
    antes = f.read_bytes()
    mtime = f.stat().st_mtime_ns
    fila_dedupe.dedupe(str(f))
    assert f.read_bytes() == antes
    assert f.stat().st_mtime_ns == mtime
    assert not list(tmp_path.glob("*.bak-*"))


def test_linhas_mantidas_byte_identicas(tmp_path):
    f = tmp_path / "fila.jsonl"
    orig = _escrever(f, n_dupes=3)
    res = fila_dedupe.dedupe(str(f))
    assert res["linhas"][0] == orig[0]
    assert res["linhas"][0].encode("utf-8") == orig[0].encode("utf-8")


def test_corrompidas_contadas_nao_crash(tmp_path):
    f = tmp_path / "fila.jsonl"
    _escrever(f, n_dupes=2, extras=["{quebrado", "", "   ", "nao-json"])
    res = fila_dedupe.dedupe(str(f))
    assert res["corrompidas"] == 4
    assert res["unicos"] == 1


def test_primeira_ocorrencia_mantida(tmp_path):
    f = tmp_path / "fila.jsonl"
    f.write_text(
        json.dumps({"id": "a", "seq": 1})
        + "\n"
        + json.dumps({"id": "a", "seq": 2})
        + "\n",
        encoding="utf-8",
    )
    res = fila_dedupe.dedupe(str(f))
    assert json.loads(res["linhas"][0])["seq"] == 1


def test_arquivo_vazio(tmp_path):
    f = tmp_path / "vazia.jsonl"
    f.write_text("", encoding="utf-8")
    res = fila_dedupe.dedupe(str(f))
    assert res["antes"] == 0 and res["unicos"] == 0


def test_apply_escreve_e_cria_bak(tmp_path):
    f = tmp_path / "fila.jsonl"
    _escrever(f, n_dupes=5)
    res = fila_dedupe.aplicar(str(f), backup=True)
    assert res["arquivo"] == str(f)
    baks = list(tmp_path.glob("fila.jsonl.bak-*"))
    assert len(baks) == 1
    assert len(baks[0].read_text().strip().splitlines()) == 6
    assert len(f.read_text().strip().splitlines()) == 1


def test_apply_sem_backup(tmp_path):
    f = tmp_path / "fila.jsonl"
    _escrever(f, n_dupes=2)
    fila_dedupe.aplicar(str(f), backup=False)
    assert not list(tmp_path.glob("*.bak-*"))


def test_apply_conteudo_byte_identico(tmp_path):
    f = tmp_path / "fila.jsonl"
    orig = _escrever(f, n_dupes=3)
    fila_dedupe.aplicar(str(f), backup=False)
    kept = f.read_text().strip().splitlines()
    assert kept[0] == orig[0]
    assert kept[0].encode() == orig[0].encode()


def test_apply_idempotente(tmp_path):
    f = tmp_path / "fila.jsonl"
    _escrever(f, n_dupes=4)
    fila_dedupe.aplicar(str(f), backup=False)
    r1 = fila_dedupe.aplicar(str(f), backup=False)
    assert r1["duplicadas"] == 0 and r1["unicos"] == 1


def test_cli_dry_run_exit0(tmp_path):
    f = tmp_path / "fila.jsonl"
    _escrever(f)
    r = subprocess.run([PY, SCRIPT, "--fila", str(f)], capture_output=True, text=True)
    assert r.returncode == 0
    assert "duplicadas=785" in r.stdout


def test_cli_missing_exit1(tmp_path):
    r = subprocess.run(
        [PY, SCRIPT, "--fila", str(tmp_path / "nao-existe.jsonl")],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1
    assert r.stderr.strip()


def test_cli_usage_exit2():
    r = subprocess.run([PY, SCRIPT], capture_output=True, text=True)
    assert r.returncode == 2


def test_cli_json_output(tmp_path):
    f = tmp_path / "fila.jsonl"
    _escrever(f, n_dupes=2)
    r = subprocess.run(
        [PY, SCRIPT, "--fila", str(f), "--json"], capture_output=True, text=True
    )
    assert r.returncode == 0
    res = json.loads(r.stdout)
    assert res["unicos"] == 1 and res["duplicadas"] == 2


def test_cli_apply(tmp_path):
    f = tmp_path / "fila.jsonl"
    _escrever(f, n_dupes=3)
    r = subprocess.run(
        [PY, SCRIPT, "--fila", str(f), "--apply"], capture_output=True, text=True
    )
    assert r.returncode == 0
    assert len(f.read_text().strip().splitlines()) == 1
    assert list(tmp_path.glob("fila.jsonl.bak-*"))