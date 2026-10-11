#!/usr/bin/env python3
"""GB-SO-ISO-01 - prova: isolamento de disco por tenant no mission_run."""
import os, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mission_run import TenantBoundaryError, tenant_silo

BASE = tempfile.mkdtemp(prefix="gb-so-iso-01-")
FALHAS = []

def check(nome, cond, detalhe=""):
    print(("PASS" if cond else "FAIL"), nome, detalhe)
    if not cond:
        FALHAS.append(nome)

def env_limpo():
    e = dict(os.environ)
    e.pop("GUARDIAN_TENANT_ID", None)
    e.pop("MISSION_STATE_DIR", None)
    e.pop("MISSION_EVENTS_DIR", None)
    return e

# (1) tenant-a com env setado grava silo de A
cwd_a = os.path.join(BASE, "wt-a")
os.makedirs(cwd_a, exist_ok=True)
env = env_limpo()
env["GUARDIAN_TENANT_ID"] = "tenant-a"
silo_a = tenant_silo(cwd_a, env=env)
check("silo-a-resolvido", silo_a == os.path.join(cwd_a, "tenants", "tenant-a"), silo_a)
for sub in ("state", "mission-events", "runs"):
    check("silo-a-dir-" + sub, os.path.isdir(os.path.join(silo_a, sub)))
check("env-state-a", env["MISSION_STATE_DIR"] == os.path.join(silo_a, "state"))
check("env-events-a", env["MISSION_EVENTS_DIR"] == os.path.join(silo_a, "mission-events"))
with open(os.path.join(silo_a, "state", "marcador-a.txt"), "w") as f:
    f.write("dado-tenant-a")

# (2) worker A tenta paths de B -> TENANT_BOUNDARY
try:
    tenant_silo(os.path.join(cwd_a, "tenants", "tenant-b"), env=dict(env))
    check("recusa-tenant-b", False, "nao recusou")
except TenantBoundaryError as e:
    check("recusa-tenant-b", "TENANT_BOUNDARY" in str(e), str(e))
try:
    tenant_silo(os.path.join(cwd_a, "..", "tenant-b"), env=dict(env))
    check("recusa-dotdot", False, "nao recusou")
except TenantBoundaryError as e:
    check("recusa-dotdot", "TENANT_BOUNDARY" in str(e), str(e))
try:
    tenant_silo(cwd_a, tenant_id="tenant-b", env=dict(env))
    check("recusa-slug-divergente", False, "nao recusou")
except TenantBoundaryError as e:
    check("recusa-slug-divergente", "TENANT_BOUNDARY" in str(e), str(e))

# (3) nada de A no disco de B e vice-versa
cwd_b = os.path.join(BASE, "wt-b")
os.makedirs(cwd_b, exist_ok=True)
env_b = env_limpo()
env_b["GUARDIAN_TENANT_ID"] = "tenant-b"
silo_b = tenant_silo(cwd_b, env=env_b)
check("silo-b-resolvido", silo_b == os.path.join(cwd_b, "tenants", "tenant-b"))
with open(os.path.join(silo_b, "state", "marcador-b.txt"), "w") as f:
    f.write("dado-tenant-b")
check("b-nao-ve-a", not os.path.exists(os.path.join(silo_b, "state", "marcador-a.txt")))
check("a-nao-ve-b", not os.path.exists(os.path.join(silo_a, "state", "marcador-b.txt")))
achou_fora = []
for root, _d, files in os.walk(BASE):
    if "marcador-a.txt" in files and not root.startswith(silo_a):
        achou_fora.append(root)
    if "marcador-b.txt" in files and not root.startswith(silo_b):
        achou_fora.append(root)
check("vazamento-zero", not achou_fora, str(achou_fora))

# (4) sem env de tenant -> legado preservado
env_l = env_limpo()
check("legado-none", tenant_silo(cwd_a, env=env_l) is None)
check("legado-env-intacto", "MISSION_STATE_DIR" not in env_l and "MISSION_EVENTS_DIR" not in env_l)

# CLI: main() com env tenant e --cwd invalido -> exit nao-zero, sem traceback
mr = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mission_run.py")
missao = os.path.join(BASE, "missao-fake.md")
with open(missao, "w") as f:
    f.write("# missao fake\n")
e_cli = env_limpo()
e_cli["GUARDIAN_TENANT_ID"] = "tenant-a"
r = subprocess.run([sys.executable, mr, "--mission", missao,
                    "--cwd", os.path.join(cwd_a, "tenants", "tenant-b")],
                   env=e_cli, capture_output=True, text=True, timeout=30)
out = r.stdout + r.stderr
check("cli-boundary-exit", r.returncode != 0, "rc=%d" % r.returncode)
check("cli-boundary-typado", "TENANT_BOUNDARY" in out and "Traceback" not in out, out[:200])

print()
if FALHAS:
    print("FALHAS:", FALHAS)
    sys.exit(1)
print("GB-SO-ISO-01-PROVA-OK")
