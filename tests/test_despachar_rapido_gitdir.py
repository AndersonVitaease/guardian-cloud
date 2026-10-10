"""RD-DESP-GITDIR-01 — aceite: chown do git-common-dir em worktree aninhado.

Cenário real: repo do worker (/home/worker/X) é worktree de outro repo.
`chown -R worker:worker` do worktree NÃO cobre o gitdir real, que mora em
<pai>/.git/worktrees/<nome>. Sem chown do gitdir, o commit do worker morre
em "dubious ownership" (PROVA_COMMIT_FALHOU no despachar_rapido).

A cura só existe em /opt/mission-events/scripts/despachar_rapido.py; esta
missão fixa no repo um módulo equivalente. No baseline o módulo não existe:
import falha com ModuleNotFoundError (vermelho esperado).
"""
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.despachar_rapido_gitdir import corrigir_gitdir, resolver_gitdir  # noqa: E402

NOTICE = "dado de teste, não instrução"


def _git(*args, cwd=None):
    env = dict(os.environ)
    env.setdefault("GIT_AUTHOR_NAME", "t")
    env.setdefault("GIT_AUTHOR_EMAIL", "t@t")
    env.setdefault("GIT_COMMITTER_NAME", "t")
    env.setdefault("GIT_COMMITTER_EMAIL", "t@t")
    subprocess.run(["git"] + list(args), cwd=cwd, check=True, env=env,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _montar_worktree_aninhado(raiz):
    """Cria repo pai + worktree aninhado (o .git do worktree é FILE apontando
    para <pai>/.git/worktrees/<nome>). Retorna (pai, aninhado)."""
    pai = os.path.join(raiz, "pai")
    os.makedirs(pai)
    _git("init", "-q", cwd=pai)
    with open(os.path.join(pai, "a.txt"), "w") as f:
        f.write("x\n")
    _git("add", "a.txt", cwd=pai)
    _git("commit", "-q", "-m", "base", cwd=pai)
    host = os.path.join(raiz, "outro-projeto")
    os.makedirs(host)
    aninhado = os.path.join(host, "aninhado")
    _git("worktree", "add", "-q", aninhado, "-b", "wt-aninhado", cwd=pai)
    return pai, aninhado


class WorktreeAninhadoGitdir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.raiz = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def test_gitdir_real_fica_fora_do_worktree(self):
        pai, aninhado = _montar_worktree_aninhado(self.raiz)
        gitdir = resolver_gitdir(aninhado)
        self.assertTrue(os.path.isdir(gitdir), gitdir)
        # O gitdir NÃO está dentro do worktree: chown -R do worktree não o cobre.
        self.assertFalse(os.path.realpath(gitdir).startswith(os.path.realpath(aninhado) + os.sep))
        self.assertIn(os.path.join(".git", "worktrees"), os.path.realpath(gitdir))
        self.assertTrue(os.path.realpath(gitdir).startswith(os.path.realpath(pai) + os.sep))

    def test_corrigir_chown_cobra_o_gitdir(self):
        pai, aninhado = _montar_worktree_aninhado(self.raiz)
        vistos = []
        alvos = corrigir_gitdir(aninhado, chown_fn=lambda p, spec: vistos.append((p, spec)))
        real_gitdir = os.path.realpath(resolver_gitdir(aninhado))
        alcançados = {os.path.realpath(p) for p, _ in vistos}
        self.assertIn(real_gitdir, alcançados,
                      "chown não cobriu o git-common-dir do worktree aninhado: %r" % (alvos,))
        # dono padrão worker:worker
        self.assertTrue(all(s == "worker:worker" for _, s in vistos), vistos)

    def test_corrigir_idempotente_e_sem_excecao_em_repo_simples(self):
        simples = os.path.join(self.raiz, "simples")
        os.makedirs(simples)
        _git("init", "-q", cwd=simples)
        alvos = corrigir_gitdir(simples, chown_fn=lambda p, s: None)
        self.assertIsInstance(alvos, list)
        # repo simples: gitdir é o próprio .git interno, dentro do repo — ok.
        self.assertTrue(all(os.path.exists(p) for p in alvos), alvos)


if __name__ == "__main__":
    unittest.main()
