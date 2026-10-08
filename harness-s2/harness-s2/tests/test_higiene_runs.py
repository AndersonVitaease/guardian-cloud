import os
import time
import pytest

from scripts.higiene_runs import inventariar, classificar, limpar


def _mk_run(base, missao, nome, trail=False, pane=False, idade_h=48.0):
    d = os.path.join(base, missao, nome)
    os.makedirs(d, exist_ok=True)
    if trail:
        open(os.path.join(d, "harness-trail.jsonl"), "w").write("{}\n")
    if pane:
        open(os.path.join(d, "harness-pane.log"), "w").write("ok\n")
    antigo = time.time() - idade_h * 3600.0
    os.utime(d, (antigo, antigo))
    return d


@pytest.fixture
def uid():
    return os.getuid()


def test_com_trail_e_pane_vai_para_manter(tmp_path, uid):
    _mk_run(str(tmp_path), "m1", "run-a", trail=True, pane=True)
    runs = inventariar(str(tmp_path), uid_worker=uid)
    rem, sus, manter = classificar(runs)
    assert not rem and not sus and len(manter) == 1


def test_orfao_vai_para_removiveis(tmp_path, uid):
    _mk_run(str(tmp_path), "m1", "run-a")
    _mk_run(str(tmp_path), "m1", "run-b", trail=True)  # protege último
    runs = inventariar(str(tmp_path), uid_worker=uid)
    rem, sus, manter = classificar(runs)
    assert len(rem) == 1 and rem[0]["dir"].endswith("run-a")


def test_ultimo_run_dir_da_missao_nunca_removivel(tmp_path, uid):
    _mk_run(str(tmp_path), "m1", "run-a")  # único e órfão
    runs = inventariar(str(tmp_path), uid_worker=uid)
    rem, sus, manter = classificar(runs)
    assert not rem and len(manter) == 1


def test_run_dir_recente_menos_24h_nao_removivel(tmp_path, uid):
    _mk_run(str(tmp_path), "m1", "run-a", idade_h=2.0)
    _mk_run(str(tmp_path), "m1", "run-b", trail=True)
    runs = inventariar(str(tmp_path), uid_worker=uid)
    rem, sus, manter = classificar(runs)
    assert not rem and len(manter) == 2


def test_owner_diferente_vai_para_suspeitos(tmp_path, uid):
    # simula owner estrangeiro via uid_worker=uid+12345
    _mk_run(str(tmp_path), "m1", "run-a", trail=True)
    runs = inventariar(str(tmp_path), uid_worker=uid + 12345)
    rem, sus, manter = classificar(runs)
    import pwd
    esperado = pwd.getpwuid(os.geteuid()).pw_name  # owner é NOME (root/worker), não uid
    assert len(sus) == 1 and sus[0]["owner"] == esperado


def test_limpar_dry_run_nao_remove(tmp_path, uid, capsys):
    d = _mk_run(str(tmp_path), "m1", "run-a")
    _mk_run(str(tmp_path), "m1", "run-b", trail=True)
    runs = inventariar(str(tmp_path), uid_worker=uid)
    rem, _, _ = classificar(runs)
    r = limpar(rem, dry_run=True)
    assert os.path.isdir(d) and r["removidos"] == 0
    out = capsys.readouterr().out
    assert "dry-run" in out


def test_limpar_real_remove_e_conta(tmp_path, uid):
    d = _mk_run(str(tmp_path), "m1", "run-a")
    _mk_run(str(tmp_path), "m1", "run-b", trail=True)
    runs = inventariar(str(tmp_path), uid_worker=uid)
    rem, _, _ = classificar(runs)
    r = limpar(rem, dry_run=False)
    assert r["removidos"] == 1 and not os.path.isdir(d)