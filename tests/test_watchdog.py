import json, os, subprocess, sys, stat, textwrap
import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SWEEP = os.path.join(REPO, "scripts", "watchdog_sweep.sh")
CTL = os.path.join(REPO, "scripts", "watchdog_ctl.sh")

def run(cmd, env_extra=None, timeout=30):
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=timeout)

def make_script(d, name, body, executable=True):
    p = os.path.join(d, name)
    with open(p, "w") as f:
        f.write("#!/usr/bin/env bash\n" + body + "\n")
    if executable:
        os.chmod(p, 0o755)
    return p

def parse_json(out):
    lines = [l for l in out.strip().splitlines() if l.strip()]
    return json.loads(lines[-1])

def test_sweep_roda_dois_e_falha_nao_aborta(tmp_path):
    d = tmp_path / "wd"; d.mkdir()
    make_script(str(d), "10-fail.sh", "echo falha; exit 3")
    make_script(str(d), "20-ok.sh", "echo reportou")
    r = run(["bash", SWEEP], {"WATCHDOG_D_DIR": str(d)})
    assert r.returncode == 0
    j = parse_json(r.stdout)
    nomes = [x["script"] for x in j["rodados"]]
    assert nomes == ["10-fail", "20-ok"]
    assert len(j["falhas_tipadas"]) == 1

def test_sweep_pula_desabilitado(tmp_path):
    d = tmp_path / "wd"; d.mkdir()
    make_script(str(d), "10-off.sh", "echo x", executable=False)
    make_script(str(d), "20-on.sh", "echo y")
    r = run(["bash", SWEEP], {"WATCHDOG_D_DIR": str(d)})
    j = parse_json(r.stdout)
    assert [x["script"] for x in j["rodados"]] == ["20-on"]

def test_sweep_timeout_mata_e_segue(tmp_path):
    d = tmp_path / "wd"; d.mkdir()
    make_script(str(d), "10-dorme.sh", "sleep 60")
    make_script(str(d), "20-ok.sh", "echo ok")
    r = run(["bash", SWEEP], {"WATCHDOG_D_DIR": str(d), "WATCHDOG_TIMEOUT": "1s"}, timeout=20)
    j = parse_json(r.stdout)
    assert [x["script"] for x in j["rodados"]] == ["10-dorme", "20-ok"]
    assert j["falhas_tipadas"][0]["tipo"] == "timeout"

def test_ctl_dry_run_nao_muta(tmp_path):
    d = tmp_path / "wd"; d.mkdir()
    p = make_script(str(d), "10-x.sh", "echo x")
    before = os.stat(p).st_mode
    r = run(["bash", CTL, "enable", "10-x"], {"WATCHDOG_D_DIR": str(d)})
    assert r.returncode == 0
    assert os.stat(p).st_mode == before
    assert "dry-run" in r.stdout

def test_ctl_enable_chmod(tmp_path):
    d = tmp_path / "wd"; d.mkdir()
    p = make_script(str(d), "10-x.sh", "echo x", executable=False)
    r = run(["bash", CTL, "--apply", "enable", "10-x"], {"WATCHDOG_D_DIR": str(d)})
    assert r.returncode == 0
    assert os.stat(p).st_mode & stat.S_IXUSR

@pytest.mark.parametrize("caso", ["sweep_ok", "ctl_dry", "ctl_apply"])
def test_json_uma_linha(tmp_path, caso):
    d = tmp_path / "wd"; d.mkdir()
    make_script(str(d), "10-ok.sh", "echo oi")
    if caso == "sweep_ok":
        r = run(["bash", SWEEP], {"WATCHDOG_D_DIR": str(d)})
    elif caso == "ctl_dry":
        r = run(["bash", CTL, "list"], {"WATCHDOG_D_DIR": str(d)})
        assert r.returncode == 0
        return
    else:
        r = run(["bash", CTL, "--apply", "disable", "10-ok"], {"WATCHDOG_D_DIR": str(d)})
    j = parse_json(r.stdout)
    assert j.get("ok") is True