"""Cura do gitdir de worktree aninhado (RD-DESP-GITDIR-01).

Em worktree aninhado, o gitdir real mora em <repo-pai>/.git/worktrees/<nome>,
FORA do worktree; sem chown dele o commit do worker morre em
"dubious ownership" (PROVA_COMMIT_FALHOU).
"""

import os
import subprocess


# gitdir real via: git -C <caminho> rev-parse --git-common-dir
# (em worktree aninhado, o alvo de chown é o gitdir específico do worktree)
def resolver_gitdir(caminho):
    """Retorna o gitdir real (absoluto e realpath) via git rev-parse."""
    proc = subprocess.run(
        ["git", "-C", str(caminho), "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip().splitlines()
        curto = stderr[0][:200] if stderr else "rc=%d" % proc.returncode
        raise RuntimeError("GITDIR_INDETERMINADO: %s" % curto)
    saida = proc.stdout.strip()
    # Worktree aninhado: o gitdir REAL (o que precisa de chown) é o específico
    # do worktree (<pai>/.git/worktrees/<nome>), não o common dir do pai.
    if os.path.isfile(os.path.join(os.path.abspath(str(caminho)), ".git")):
        proc2 = subprocess.run(
            ["git", "-C", str(caminho), "rev-parse", "--git-dir"],
            capture_output=True, text=True, timeout=120,
        )
        if proc2.returncode == 0 and proc2.stdout.strip():
            saida = proc2.stdout.strip()
    if not os.path.isabs(saida):
        saida = os.path.join(os.path.abspath(str(caminho)), saida)
    return os.path.realpath(saida)


def corrigir_gitdir(caminho, chown_fn=None, spec="worker:worker"):
    """Chown worker:worker do caminho, do .git FILE (stub de worktree) e do gitdir real."""
    caminho = os.path.abspath(str(caminho))
    alvos = [caminho]
    git_file = os.path.join(caminho, ".git")
    if os.path.isfile(git_file):
        alvos.append(git_file)
    alvos.append(resolver_gitdir(caminho))
    alvos = [a for a in alvos if os.path.exists(a)]

    chownados = []
    for alvo in alvos:
        if chown_fn is not None:
            chown_fn(alvo, spec)
        else:
            if os.path.isdir(alvo):
                cmd = ["chown", "-R", spec, alvo]
            else:
                cmd = ["chown", spec, alvo]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if proc.returncode != 0:
                stderr = (proc.stderr or "").strip().splitlines()
                curto = stderr[0][:200] if stderr else "rc=%d" % proc.returncode
                raise RuntimeError("CHOWN_FALHOU: %s: %s" % (alvo, curto))
        chownados.append(alvo)
    return chownados