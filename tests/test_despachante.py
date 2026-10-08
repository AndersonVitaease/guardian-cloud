import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import despachante as d


def missao(mid, deps=None, **kw):
    m = {"id": mid, "contrato_path": f"contratos/{mid}.md", "cwd": "/tmp/x",
         "seed": 1, "budget": 1.0, "max_turns": 5, "deps": deps or []}
    m.update(kw)
    return m


def plano(*missoes, politica="parar"):
    return {"politica_fail": politica, "missoes": list(missoes)}


# ---------- ler_plano ----------

def test_ler_plano_valido():
    p = d.ler_plano(plano(missao("A"), missao("B", ["A"])))
    assert p["politica_fail"] == "parar"
    assert set(p["missoes"]) == {"A", "B"}


def test_ler_plano_invalido_sem_missoes():
    for bad in ({}, {"missoes": []}, {"missoes": "x"}):
        try:
            d.ler_plano(bad)
            assert False, bad
        except ValueError:
            pass


def test_ler_plano_campo_faltante():
    m = missao("A")
    del m["seed"]
    try:
        d.ler_plano(plano(m))
        assert False
    except ValueError:
        pass


def test_ler_plano_id_duplicado():
    try:
        d.ler_plano(plano(missao("A"), missao("A")))
        assert False
    except ValueError:
        pass


def test_ler_plano_dep_inexistente():
    try:
        d.ler_plano(plano(missao("A", ["Z"])))
        assert False
    except ValueError:
        pass


def test_ler_plano_ciclo():
    try:
        d.ler_plano(plano(missao("A", ["B"]), missao("B", ["A"])))
        assert False
    except ValueError:
        pass


def test_ler_plano_politica_invalida():
    try:
        d.ler_plano(plano(missao("A"), politica="x"))
        assert False
    except ValueError:
        pass


def test_ler_plano_de_arquivo(tmp_path):
    f = tmp_path / "plano.json"
    f.write_text(json.dumps(plano(missao("A"))), encoding="utf-8")
    p = d.ler_plano(str(f))
    assert p["missoes"]["A"]["seed"] == 1


# ---------- ordem topológica ----------

def test_ordem_topologica_dag():
    p = d.ler_plano(plano(missao("SC-2", ["SC-1"]), missao("SC-1"),
                          missao("SC-3", ["SC-1"]), missao("SC-4", ["SC-2", "SC-3"])))
    ordem = d.ordem_topologica(p)
    assert ordem.index("SC-1") < ordem.index("SC-2")
    assert ordem.index("SC-1") < ordem.index("SC-3")
    assert ordem.index("SC-2") < ordem.index("SC-4")
    assert ordem.index("SC-3") < ordem.index("SC-4")


def test_ordem_topologica_paralelas():
    p = d.ler_plano(plano(missao("A"), missao("B")))
    assert set(d.ordem_topologica(p)) == {"A", "B"}


# ---------- dry-run ----------

def test_dry_run_nao_executa(tmp_path, capsys):
    p = d.ler_plano(plano(missao("A"), missao("B", ["A"])))
    chamadas = []
    orig = subprocess.Popen
    subprocess.Popen = lambda *a, **k: chamadas.append(a) or (_ for _ in ()).throw(AssertionError("executou!"))
    try:
        f = tmp_path / "plano.json"
        f.write_text(json.dumps(plano(missao("A"), missao("B", ["A"]))), encoding="utf-8")
        rc = d.main([str(f), "--dry-run"])
    finally:
        subprocess.Popen = orig
    assert rc == 0
    assert chamadas == []
    out = capsys.readouterr().out
    assert "systemd-run" in out and "harness-A" in out and "harness-B" in out


# ---------- despachar / aguardar (mock subprocess) ----------

class FakeProc:
    def __init__(self):
        self.cmd = None


def test_despachar_respeita_deps(tmp_path):
    p = d.ler_plano(plano(missao("A"), missao("B", ["A"])))
    procs = []

    def fake_spawner(cmd, **kw):
        pr = FakeProc()
        pr.cmd = cmd
        procs.append(pr)
        return pr

    inicio = str(tmp_path / "desp")
    desp = d.despachar(p, inicio, spawner=fake_spawner)
    assert desp == ["A"]  # B bloqueada por dep
    # pousa A com PASS
    rd = Path(p["missoes"]["A"]["_run_dir"])
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "resumo.json").write_text(json.dumps({"veredito": "PASS", "turnos": 3, "custo": 0.5}), encoding="utf-8")
    p["missoes"]["A"]["_estado"] = "POUSADA_PASS"
    desp = d.despachar(p, inicio, spawner=fake_spawner)
    assert desp == ["B"]
    cmd = procs[1].cmd
    assert cmd[0] == "systemd-run" and "--uid=worker" in cmd and "--unit=harness-B" in cmd
    assert "--collect" in cmd
    assert str(cmd[cmd.index("/usr/bin/python3") + 1]).endswith("mission_run.py")
    assert "--seed" in cmd and "--budget" in cmd and "--max-turns" in cmd and "--out" in cmd


def _spawner_que_pousa(vereditos, base):
    """Spawner fake: escreve resumo.json imediatamente (simula pouso instantâneo)."""
    procs = []
    def fake(cmd, **kw):
        mid = [c for c in cmd if c.startswith("--unit=")][0].replace("--unit=harness-", "")
        out = cmd[cmd.index("--out") + 1]
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps({"veredito": vereditos[mid], "turnos": 3, "custo": 0.4}), encoding="utf-8")
        pr = FakeProc(); pr.cmd = cmd; procs.append(pr); return pr
    fake.procs = procs
    return fake


def test_aguardar_politica_parar(tmp_path):
    p = d.ler_plano(plano(missao("A"), missao("B", ["A"]), missao("C", ["B"])))
    sp = _spawner_que_pousa({"A": "FAIL", "B": "PASS", "C": "PASS"}, tmp_path)
    regs = d.aguardar(p, str(tmp_path / "desp"), poll=0.01, deadline=2.0, spawner=sp)
    assert regs["A"]["estado"] == "POUSADA_FAIL"
    assert regs["B"]["estado"] == "BLOQUEADA"
    assert regs["C"]["estado"] == "BLOQUEADA"
    assert len(sp.procs) == 1  # B e C nunca despachadas


def test_aguardar_politica_continuar(tmp_path):
    p = d.ler_plano(plano(missao("A"), missao("B", ["A"]), politica="continuar"))
    sp = _spawner_que_pousa({"A": "FAIL", "B": "PASS"}, tmp_path)
    regs = d.aguardar(p, str(tmp_path / "desp"), poll=0.01, deadline=2.0, spawner=sp)
    assert regs["A"]["estado"] == "POUSADA_FAIL"
    assert regs["B"]["estado"] == "POUSADA_PASS"
    assert len(sp.procs) == 2  # B despachada mesmo com A FAIL


def test_aguardar_resumo_fake(tmp_path):
    p = d.ler_plano(plano(missao("A"), missao("B", ["A"])))
    sp = _spawner_que_pousa({"A": "PASS", "B": "PASS"}, tmp_path)
    regs = d.aguardar(p, str(tmp_path / "desp"), poll=0.01, deadline=2.0, spawner=sp)
    assert regs["A"]["veredito"] == "PASS"
    assert regs["B"]["veredito"] == "PASS"
    assert regs["B"]["turnos"] == 3 and regs["B"]["custo"] == 0.4
    assert regs["B"]["run_dir"]


def test_ler_resumo_ausente(tmp_path):
    assert d.ler_resumo(str(tmp_path)) is None


def test_ler_resumo_corrompido(tmp_path):
    (tmp_path / "resumo.json").write_text("{quebrado", encoding="utf-8")
    assert d.ler_resumo(str(tmp_path)) is None


def test_main_exit_codes(tmp_path, monkeypatch, capsys):
    # plano com todas PASS -> exit 0
    pf = tmp_path / "plano.json"
    pf.write_text(json.dumps(plano(missao("A"))), encoding="utf-8")
    procs = []

    def fake_spawner(cmd, **kw):
        pr = FakeProc(); pr.cmd = cmd; procs.append(pr); return pr

    monkeypatch.setattr(d.subprocess, "Popen", fake_spawner)
    monkeypatch.chdir(tmp_path)
    # pré-cria resumo no run_dir que o main vai usar: intercepta via aguardar deadline curto
    monkeypatch.setattr(d, "POLL_INTERVAL", 0.01)
    # escreve resumo após despacho usando thread
    import threading

    def pousa():
        for _ in range(200):
            dirs = list(tmp_path.glob("runs/DESPACHO-*/A"))
            if dirs:
                (dirs[0] / "resumo.json").write_text(json.dumps({"veredito": "PASS", "turnos": 1, "custo": 0.1}), encoding="utf-8")
                return
            time.sleep(0.01)

    th = threading.Thread(target=pousa); th.start()
    rc = d.main([str(pf)])
    th.join()
    assert rc == 0