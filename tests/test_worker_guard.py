# RD-WORKER-GUARD-01 — testes do guard de git + prova mecanica no veredito
import json
import os
import subprocess
import sys
import tempfile

HARNESS_DIR = "/home/worker/wt-RD-WORKER-GUARD"
sys.path.insert(0, HARNESS_DIR)
import harness  # noqa: E402


def _repo():
    d = tempfile.mkdtemp()
    subprocess.run("git init -q . && git config user.email w@w && "
                   "git config user.name w && echo x > a.txt && "
                   "git add a.txt && git commit -qm i && echo y > a.txt",
                   shell=True, cwd=d, check=True)
    return d


def _bash(cmd, cwd):
    return harness.run_tool("Bash", {"command": cmd}, cwd)


def test_reset_hard_recusado():
    d = _repo()
    r = _bash("git reset --hard", d)
    assert "GIT_GUARD_RESET_PROIBIDO" in r, r
    assert '"ok": false' in r or '"ok":false' in r, r


def test_reset_com_ref_recusado():
    d = _repo()
    r = _bash("git reset HEAD~1", d)
    assert "GIT_GUARD_RESET_PROIBIDO" in r, r


def test_checkout_branch_recusado():
    d = _repo()
    r = _bash("git checkout main", d)
    assert "GIT_GUARD_RESET_PROIBIDO" in r, r


def test_stash_e_clean_recusados():
    d = _repo()
    for cmd in ("git stash", "git clean -fdx"):
        r = _bash(cmd, d)
        assert "GIT_GUARD_RESET_PROIBIDO" in r, (cmd, r)


def test_checkout_arquivo_permitido():
    d = _repo()
    r = _bash("git checkout -- a.txt", d)
    assert "exit=0" in r, r


def test_reset_unstage_permitido():
    d = _repo()
    r = _bash("git reset", d)
    assert "exit=0" in r, r


def test_prova_verde_veredito_ok():
    p = harness._parse_prova_mecanica(
        "## Prova mecanica\ncmd echo 0 falhas\nexpect 0 falhas\n")
    assert p == [("echo 0 falhas", "0 falhas")], p
    ok, det = harness._rodar_prova_mecanica(p, "/tmp")
    assert ok, det


def test_prova_vermelha_prova_falhou():
    p = [("echo 1 falhas", "0 falhas")]
    ok, det = harness._rodar_prova_mecanica(p, "/tmp")
    assert not ok
    assert det.get("error") == "PROVA_FALHOU", det


def test_contrato_sem_secao_comportamento_antigo():
    assert harness._parse_prova_mecanica("# contrato sem secao") == []
    ok, det = harness._rodar_prova_mecanica([], "/tmp")
    assert ok and det == {"provas": 0}, det


def test_log_recusa_no_trail():
    d = _repo()
    log = os.path.join(d, "guard.log")
    env = dict(os.environ, RD_GIT_GUARD_LOG=log)
    code = ("import sys; sys.path.insert(0, %r)\n"
            "import harness\n"
            "r = harness.run_tool('Bash', {'command': 'git stash'}, %r)\n"
            "assert 'GIT_GUARD_RESET_PROIBIDO' in r, r\n" % (HARNESS_DIR, d))
    p = subprocess.run([sys.executable, "-c", code], env=env,
                        capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    linha = json.loads(open(log).read().strip().splitlines()[-1])
    assert linha["error"] == "GIT_GUARD_RESET_PROIBIDO"
    assert "git stash" in linha["cmd"]