import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import canario_fila as cf


def _pf(tmp_path):
    p = tmp_path / "prompt.md"
    p.write_text("# canary\n", encoding="utf-8")
    return str(p)


def test_enfileirar_ids_unicos(tmp_path):
    fila = str(tmp_path / "fila.jsonl")
    a = cf.enfileirar(fila, mission_id="M1", promptfile=_pf(tmp_path))
    b = cf.enfileirar(fila, mission_id="M2", promptfile=_pf(tmp_path))
    assert a["id"] != b["id"]
    assert len(open(fila).read().strip().split("\n")) == 2


def test_enfileirar_payload_valido(tmp_path):
    fila = str(tmp_path / "fila.jsonl")
    pf = _pf(tmp_path)
    intent = cf.enfileirar(fila, mission_id="MX", promptfile=pf)
    assert intent["priority"] == 0
    assert intent["type"] == "mission_dispatch"
    assert intent["payload"]["missionId"] == "MX"
    assert intent["payload"]["promptFile"] == pf
    assert intent["payload"]["consequence"] is False
    assert intent["payload"]["spawnedBy"] == "operator"
    assert intent["payload"]["status"] == "queued"
    assert intent["payload"]["cwd"]
    assert intent["payload"]["queuedAt"].endswith("Z")
    assert "prompt" not in intent["payload"]
    assert intent["id"].startswith("intent-canario-")
    assert json.loads(open(fila).read().strip()) == intent


def test_enfileirar_promptfile_ausente_cria(tmp_path):
    fila = str(tmp_path / "fila.jsonl")
    pf = str(tmp_path / "sub" / "prompt.md")
    cf.enfileirar(fila, mission_id="MY", promptfile=pf)
    assert os.path.isfile(pf)
    with open(pf, encoding="utf-8") as f:
        conteudo = f.read()
    assert "CANARIO-OK.txt" in conteudo
    # idempotente
    with open(pf, "a", encoding="utf-8") as f:
        f.write("extra\n")
    cf.enfileirar(fila, mission_id="MZ", promptfile=pf)
    assert conteudo + "extra\n" == open(pf).read()


def test_esperar_dispatch_acha_linha(tmp_path):
    log = tmp_path / "log.txt"
    log.write_text("foo\nbar\n2026 dispatch_via_harness: CANARIO-TEST-1 ok\n")
    r = cf.esperar_dispatch(str(log), "CANARIO-TEST-1", ciclos=1, intervalo=0)
    assert r["despachado"] is True
    assert "dispatch_via_harness: CANARIO-TEST-1" in r["linha"]


def test_esperar_dispatch_nao_acha(tmp_path):
    log = tmp_path / "log.txt"
    log.write_text("nada aqui\n")
    r = cf.esperar_dispatch(str(log), "NOPE", ciclos=3, intervalo=0)
    assert r["despachado"] is False
    assert r["linha"] is None


def test_checar_run_ok(tmp_path, monkeypatch):
    run = tmp_path / "run-1"
    run.mkdir()
    (run / "harness-pane.log").write_text("x")
    monkeypatch.setattr(cf, "_worker_uid_gid", lambda: (os.getuid(), os.getgid()))
    assert cf.checar_run(str(run))["ok"] is True


def test_checar_run_root_owner_fail(tmp_path, monkeypatch):
    run = tmp_path / "run-2"
    run.mkdir()
    (run / "harness-pane.log").write_text("x")
    monkeypatch.setattr(cf, "_worker_uid_gid", lambda: (0, 999999))
    assert cf.checar_run(str(run))["ok"] is False


def test_checar_run_ausente_fail(tmp_path):
    assert cf.checar_run(str(tmp_path / "nao-existe"))["ok"] is False


def test_main_end_to_end_ok(tmp_path, monkeypatch):
    fila = str(tmp_path / "fila.jsonl")
    base = tmp_path / "runs"
    base.mkdir()
    run = base / "run-x"
    run.mkdir()
    (run / "harness-pane.log").write_text("x")
    monkeypatch.setattr(cf, "_worker_uid_gid", lambda: (os.getuid(), os.getgid()))
    monkeypatch.setattr(cf, "esperar_dispatch", lambda lp, mid, ciclos=6, intervalo=60: {
        "despachado": True, "linha": f"dispatch_via_harness: {mid}"})
    assert cf.main(["--fila", fila, "--log", str(tmp_path / "log"),
                    "--base-runs", str(base), "--promptfile", _pf(tmp_path),
                    "--json"]) == 0


def test_main_run_ausente_fail(tmp_path, monkeypatch):
    base = tmp_path / "runs"
    base.mkdir()
    monkeypatch.setattr(cf, "esperar_dispatch", lambda lp, mid, ciclos=6, intervalo=60: {
        "despachado": True, "linha": "x"})
    assert cf.main(["--fila", str(tmp_path / "fila.jsonl"), "--log", str(tmp_path / "log"),
                    "--base-runs", str(base), "--promptfile", _pf(tmp_path)]) == 1
