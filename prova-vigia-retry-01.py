#!/usr/bin/env python3
"""Prova GB-VIGIA-RETRY-01: retry com backoff em notify_nascimento.

Monkeypatch de subprocess.run via injeção (sem rede real):
- 2 primeiras chamadas levantam TimeoutError, 3ª retorna stdout b"OK"
  -> função retorna "ok" e foram feitas 3 chamadas.
- 4 falhas -> retorna "falho" com detalhe e 4 chamadas.
"""
import sys, types
sys.path.insert(0, "/home/worker/wt-GB-VIGIA-RETRY-01/scripts")
import despachar_missao as dm

# injeção: substitui subprocess.run e time.sleep no módulo alvo
chamadas = {"n": 0}

def fake_run_ok_na_3(cmd, **kw):
    chamadas["n"] += 1
    if chamadas["n"] <= 2:
        raise TimeoutError("ROTA_OFFLINE gateway 8642")
    return types.SimpleNamespace(stdout=b"OK\n", stderr=b"")

dm.subprocess.run = fake_run_ok_na_3
dm.time.sleep = lambda s: None
st, det = dm.notify_nascimento("teste")
assert st == "ok" and det == "", (st, det)
assert chamadas["n"] == 3, chamadas

chamadas["n"] = 0
def fake_run_sempre_timeout(cmd, **kw):
    chamadas["n"] += 1
    raise TimeoutError("ROTA_OFFLINE gateway 8642")

dm.subprocess.run = fake_run_sempre_timeout
st, det = dm.notify_nascimento("teste")
assert st == "falho" and "ROTA_OFFLINE" in det, (st, det)
assert chamadas["n"] == 4, chamadas

print("GB-VIGIA-RETRY-01-PROVA-OK")