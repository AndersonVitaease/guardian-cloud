# -*- coding: utf-8 -*-
# Prova hermética GB-PLUGIN-ROTA-01
import sys, os, json, types
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "patches", "GB-PLUGIN-ROTA-01"))

import __init__ as plugin

class Args:
    def __init__(self, worktree=None, seed=None, budget=None):
        self.worktree = worktree
        self.seed = seed
        self.budget = budget

class MC:
    def __init__(self):
        self.spawned = []
    def run_command(self, *a, **k):
        self.spawned.append((a, k))
        return "", ""

calls = []
def fake_run(cmd, capture_output=True, text=True):
    calls.append(list(cmd))
    return types.SimpleNamespace(returncode=0, stdout=json.dumps({"ok": True, "missionId": "M1"}), stderr="")

plugin.subprocess.run = fake_run

# (a) args.worktree -> despachar com cwd <wt>/runs/<ID> e --executar
mc = MC()
payload = {"missionId": "GB-X-01", "promptFile": "/tmp/prompt.md", "cwd": "/fora/padrao"}
r = plugin.handle_mission_dispatch(mc, Args(worktree="/wt/a"), payload)
assert calls, "despachar não foi chamado"
cmd = calls[-1]
assert cmd[1] == "/opt/mission-events/scripts/despachar_missao.py"
assert cmd[3] == "/wt/a/runs/GB-X-01", cmd
assert "--executar" in cmd, cmd
assert r["ok"] is True

# (b) payload.cwd fora do padrão -> corrigido
calls.clear()
plugin.handle_mission_dispatch(mc, Args(worktree="/wt/b"), {"missionId": "M2", "promptFile": "/tmp/p.md", "cwd": "/malicioso"})
assert calls[-1][3] == "/wt/b/runs/M2", calls[-1]

# (b2) payload.cwd DENTRO do padrão é preservado
calls.clear()
plugin.handle_mission_dispatch(mc, Args(worktree="/wt/c"), {"missionId": "M3", "promptFile": "/tmp/p.md", "cwd": "/wt/c/runs/M3/sub"})
assert calls[-1][3] == "/wt/c/runs/M3/sub", calls[-1]

# (c) gate recusando -> zero chamadas
calls.clear()
r = plugin.handle_mission_dispatch(mc, Args(worktree="/wt/d"), {"promptFile": "/tmp/p.md"})  # sem missionId
assert calls == [], calls
assert r["ok"] is False

# (d) NENHUM spawn de claude (run_command)
assert mc.spawned == [], mc.spawned

print("GB-PLUGIN-ROTA-01-PROVA-OK")