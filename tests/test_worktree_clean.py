import json, os, subprocess, tarfile, pytest

TOOL = os.path.join(os.path.dirname(__file__), "..", "tools-bash", "worktree_clean.sh")

def run_tool(env, *args):
    e = dict(os.environ)
    e.update(env)
    r = subprocess.run(["bash", TOOL, *args], capture_output=True, text=True, env=e)
    assert r.returncode == 0
    return json.loads(r.stdout.strip().splitlines()[-1])

@pytest.fixture
def setup(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    def g(*a): return subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, check=True)
    g("init", "-q"); g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / "f.txt").write_text("x"); g("add", "."); g("commit", "-qm", "base")
    state = tmp_path / "state"; state.mkdir()
    arch = tmp_path / "arquivo"
    prefix = str(tmp_path / "wt-")
    # worktree A: ledger terminal
    g("worktree", "add", "-q", str(tmp_path / "wt-AAA"), "-b", "AAA")
    # worktree B: ledger em voo
    g("worktree", "add", "-q", str(tmp_path / "wt-BBB"), "-b", "BBB")
    (state / "AAA.json").write_text(json.dumps({"status": "closed"}))
    (state / "BBB.json").write_text(json.dumps({"status": "running"}))
    units = tmp_path / "units.sh"
    units.write_text("#!/bin/bash\necho 'harness-XXX-s1.service loaded active running'\nexit 0\n")
    units.chmod(0o755)
    env = {"WORKTREE_CLEAN_REPO": str(repo), "MISSION_STATE_DIR": str(state),
           "WORKTREE_CLEAN_PREFIX": prefix, "WORKTREE_CLEAN_ARCHIVE": str(arch),
           "WORKTREE_CLEAN_UNITS_CMD": str(units)}
    return {"repo": repo, "state": state, "arch": arch, "env": env,
            "wtA": tmp_path / "wt-AAA", "wtB": tmp_path / "wt-BBB"}

def test_dry_run_nao_muta(setup):
    out = run_tool(setup["env"])
    assert out["ok"] and out["dry_run"] is True
    assert out["removidos"] == 0 and out["arquivados"] == 0
    assert setup["wtA"].is_dir() and setup["wtB"].is_dir()
    assert not setup["arch"].exists()

def test_candidato_terminal_detectado(setup):
    out = run_tool(setup["env"])
    paths = [i["worktree"] for i in out["itens"]]
    assert str(setup["wtA"]) in paths

def test_ledger_em_voo_nao_e_candidato(setup):
    out = run_tool(setup["env"])
    paths = [i["worktree"] for i in out["itens"]]
    assert str(setup["wtB"]) not in paths
    assert any(p["motivo"] == "ledger_em_voo" for p in out["pulos"])

def test_apply_arquiva_e_remove(setup):
    runs = setup["wtA"] / "runs" / "x"
    runs.mkdir(parents=True)
    (runs / "d.txt").write_text("dado")
    out = run_tool(setup["env"], "--apply")
    assert out["ok"] and out["removidos"] == 1 and out["arquivados"] == 1
    assert not setup["wtA"].exists()
    assert setup["wtB"].is_dir()
    tars = list(setup["arch"].glob("AAA-*.tar.gz"))
    assert len(tars) == 1
    with tarfile.open(tars[0]) as tf:
        assert "x/d.txt" in tf.getnames()
    man = setup["arch"] / "MANIFESTO-AAA.md"
    assert man.exists()
    txt = man.read_text()
    assert len(txt.splitlines()[3].split()[0]) == 40  # %H do commit

def test_status_sujo_nao_remove(setup):
    (setup["wtA"] / "sujo.txt").write_text("n")
    out = run_tool(setup["env"], "--apply")
    assert out["removidos"] == 0
    assert any(p["motivo"] == "STATUS_SUJO" for p in out["pulos"])
    assert setup["wtA"].is_dir()

def test_systemctl_quebrado(setup):
    bad = setup["state"].parent / "bad.sh"
    bad.write_text("#!/bin/bash\nexit 1\n"); bad.chmod(0o755)
    env = dict(setup["env"]); env["WORKTREE_CLEAN_UNITS_CMD"] = str(bad)
    # remove ledgers para forçar consulta ao systemctl
    (setup["state"] / "AAA.json").unlink()
    out = run_tool(env, "--apply")
    assert out["ok"] is False and out["error"] == "SYSTEMCTL_FAILED"
    assert setup["wtA"].is_dir()