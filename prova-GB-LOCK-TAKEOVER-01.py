#!/usr/bin/env python3
"""Prova hermetica GB-LOCK-TAKEOVER-01.

Importa o modulo COM O PATCH aplicado sobre copia em tempdir; sem rede, sem hermes real.
Cobertura:
 (a) dono morto (pid inexistente) => takeover, turno adquirido no retry;
 (b) dono vivo com heartbeat antigo (> LOCK_STEAL_MIN) => takeover;
 (c) dono vivo com heartbeat recente => NAO rouba; mensagem PT-BR com retry;
     apos esgotar retries, erro final PT-BR;
 (d) leases antigos sem campo de heartbeat => tratados como sem progresso conhecido
     (usa acquired_at/idade do lease) - compatibilidade.
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import time
import types
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(HERE, "turn_facade_lease.py.ref")
PATCH = os.path.join(HERE, "lock-takeover.patch")

os.environ["LOCK_STEAL_MIN"] = "120"
os.environ["LOCK_RETRY_MAX"] = "2"
os.environ["LOCK_RETRY_BACKOFF_SECONDS"] = "0.05"

FAILURES = []


def check(name, cond, detail=""):
    print("[%s] %s %s" % ("ok" if cond else "FALHOU", name, detail))
    if not cond:
        FAILURES.append(name)


def apply_patch_to_tempdir():
    tmp = tempfile.mkdtemp(prefix="gb-lock-takeover-")
    dst = os.path.join(tmp, "turn_facade_lease.py")
    shutil.copy(REF, dst)
    r = subprocess.run(["patch", "-p1", "--silent", "-i", PATCH, "-d", tmp],
                       capture_output=True, text=True)
    assert r.returncode == 0, "patch falhou: %s" % r.stderr
    return tmp, dst


def import_patched(dst):
    class _Stub(types.ModuleType):
        def __getattr__(self, item):
            return mock.MagicMock(name="%s.%s" % (self.__name__, item))

    needed = ["agent", "agent.db", "agent.periodic_scheduler", "agent.config",
              "agent.logging_setup", "db", "config", "utils"]
    for name in needed:
        if name not in sys.modules:
            m = _Stub(name)
            m.__path__ = []
            sys.modules[name] = m
    spec = importlib.util.spec_from_file_location("turn_facade_lease_patched", dst)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["turn_facade_lease_patched"] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeDB:
    """DB falso: acquire falha enquanto o lease do dono nao foi liberado."""

    def __init__(self, owner_pid, heartbeat=None, acquired_at=None):
        self.owner_pid = owner_pid
        self.heartbeat = heartbeat
        self.acquired_at = acquired_at
        self.acquire_calls = 0
        self.release_calls = []
        self.heartbeat_stamps = 0

    def get_session_turn_lease_info(self, session_id):
        info = {"holder": "owner-window", "pid": self.owner_pid}
        if self.heartbeat is not None:
            info["heartbeat"] = self.heartbeat
        if self.acquired_at is not None:
            info["acquired_at"] = self.acquired_at
        return info

    def acquire_session_turn_lease(self, session_id, holder, ttl_seconds=None,
                                   wait_seconds=None, **kw):
        self.acquire_calls += 1
        return bool(self.release_calls)

    def release_session_turn_lease(self, session_id, holder):
        self.release_calls.append((session_id, holder))
        return True

    def stamp_session_turn_lease_heartbeat(self, session_id, holder):
        self.heartbeat_stamps += 1
        return True


class FakeAgent:
    def __init__(self):
        self.messages = []

    def _emit_status(self, message):
        self.messages.append(message)


def dead_pid():
    pid = os.fork()
    if pid == 0:
        os._exit(0)
    os.waitpid(pid, 0)
    time.sleep(0.05)
    return pid


def main():
    tmp, dst = apply_patch_to_tempdir()
    mod = import_patched(dst)
    now = time.time()

    # (a) dono morto => takeover no retry
    db = FakeDB(owner_pid=dead_pid(), heartbeat=now)
    agent = FakeAgent()
    ok = mod._attempt_lease_takeover(agent, db, "sess-a", "window-b")
    check("(a) dono morto => takeover", ok and db.release_calls and db.acquire_calls >= 1,
          "release=%r acquire_calls=%d" % (db.release_calls, db.acquire_calls))

    # (b) dono vivo zumbi (heartbeat antigo > LOCK_STEAL_MIN) => takeover
    db = FakeDB(owner_pid=os.getpid(), heartbeat=now - 9999.0)
    agent = FakeAgent()
    ok = mod._attempt_lease_takeover(agent, db, "sess-b", "window-b")
    check("(b) dono zumbi => takeover", ok and db.release_calls,
          "release=%r" % (db.release_calls,))

    # (c) dono vivo com heartbeat recente => NAO rouba; PT-BR com retry; erro final PT-BR
    db = FakeDB(owner_pid=os.getpid(), heartbeat=now)
    agent = FakeAgent()
    ok = mod._attempt_lease_takeover(agent, db, "sess-c", "window-b")
    check("(c) dono ativo => NAO rouba", (not ok) and (not db.release_calls),
          "ok=%r release=%r" % (ok, db.release_calls))
    check("(c) mensagem PT-BR amigavel com retry",
          any("Outra janela" in m and "Tentando novamente" in m for m in agent.messages),
          "mensagens=%r" % agent.messages)
    check("(c) respeita LOCK_RETRY_MAX", len(agent.messages) == mod.LOCK_RETRY_MAX,
          "emitidas=%d esperadas=%d" % (len(agent.messages), mod.LOCK_RETRY_MAX))
    # erro final PT-BR: constante embutida na funcao de admissao patcheada
    consts = []
    for fn_name in ("admit_durable_turn_lease",):
        fn = getattr(mod, fn_name, None)
        if fn is not None:
            consts.extend(str(c) for c in getattr(fn.__code__, "co_consts", ()))
    check("(c) erro final PT-BR no caminho de recusa",
          any("Outra janela" in c and "nao foi processada" in c for c in consts),
          "consts_ptbr=%r" % [c for c in consts if "Outra janela" in c])

    # (d) lease antigo sem heartbeat => usa acquired_at (idade do lease)
    db = FakeDB(owner_pid=os.getpid(), acquired_at=now - 9999.0)
    agent = FakeAgent()
    ok = mod._attempt_lease_takeover(agent, db, "sess-d", "window-b")
    check("(d) lease sem heartbeat, idade antiga => takeover", ok and db.release_calls,
          "release=%r" % (db.release_calls,))
    # (d2) sem heartbeat E sem acquired_at => sem progresso conhecido => fail-closed
    db = FakeDB(owner_pid=os.getpid())
    agent = FakeAgent()
    ok = mod._attempt_lease_takeover(agent, db, "sess-d2", "window-b")
    check("(d) lease sem qualquer idade => fail-closed, nao rouba",
          (not ok) and (not db.release_calls), "ok=%r" % ok)

    shutil.rmtree(tmp, ignore_errors=True)
    print()
    if FAILURES:
        print("RESUMO: %d falhas: %r" % (len(FAILURES), FAILURES))
        sys.exit(1)
    print("RESUMO: 0 falhas")


if __name__ == "__main__":
    main()
