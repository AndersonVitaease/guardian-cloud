#!/usr/bin/env python3
# PROVA-HEADLESS-TAB-02 — hermética, stdlib, <60s, sem rede, sem herdr real.
import os, sys, json, time, tempfile, subprocess, importlib.util

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "prova-HEADLESS-TAB-02.out")
LOG = open(OUT, "w", encoding="utf-8")
def say(msg):
    LOG.write(str(msg) + "\n"); LOG.flush(); print(msg)

tmp = tempfile.mkdtemp(prefix="prova-ht02-")
fakebin = os.path.join(tmp, "bin"); os.makedirs(fakebin)
calls_f = os.path.join(tmp, "calls.jsonl")
state_f = os.path.join(tmp, "state.json")
state = {"tabs": [], "next": 1}

CALLS = calls_f
STATE = state_f
fake = r'''#!/usr/bin/env bash
CALLS="@CALLS@"
STATE="@STATE@"
python3 -c 'import sys,json; print(json.dumps({"argv": sys.argv[1:]}))' "$@" >> "$CALLS"
python3 - "$STATE" "$@" <<'PYEOF'
import sys, json, os
state_f = sys.argv[1]
argv = sys.argv[2:]
state = json.load(open(state_f))
cmd = argv[0] if argv else ""
out = {"ok": True}
if cmd == "tab" and "list" in argv:
    out = {"tabs": state["tabs"]}
elif cmd == "tab" and "create" in argv:
    label = argv[argv.index("--label")+1] if "--label" in argv and len(argv) > argv.index("--label")+1 else ""
    tid = "tab-%d" % state["next"]; state["next"] += 1
    state["tabs"].append({"tab_id": tid, "label": label, "pane_id": "pane-%d" % state["next"]})
    out = {"data": {"tab": {"tab_id": tid}, "pane": {"pane_id": "pane-%d" % state["next"]}}}
elif cmd == "tab" and "close" in argv:
    tid = argv[argv.index("close")+1]
    state["tabs"] = [t for t in state["tabs"] if t["tab_id"] != tid]
    out = {"ok": True}
elif cmd == "pane" and "run" in argv:
    out = {"ok": True}
json.dump(state, open(state_f, "w"))
print(json.dumps(out))
PYEOF
'''.replace("@CALLS@", CALLS).replace("@STATE@", STATE)
fake_path = os.path.join(fakebin, "herdr")
open(fake_path, "w").write(fake)
os.chmod(fake_path, 0o755)
json.dump(state, open(state_f, "w"))

os.environ["PATH"] = fakebin + ":" + os.environ.get("PATH", "")
env = dict(os.environ)

# importa consumer PATCHED
spec = importlib.util.spec_from_file_location("oc", os.path.join(BASE, "staging", "orchestrator-consumer.py"))
oc = importlib.util.module_from_spec(spec); spec.loader.exec_module(oc)

# run_dir fake + trilha fake (3 linhas)
run_dir = tempfile.mkdtemp(prefix="rundir-", dir=tmp)
trail = os.path.join(run_dir, "harness-trail.jsonl")
lines = ['{"ev":"a"}', '{"ev":"b"}', '{"ev":"c"}']
open(trail, "w").write("\n".join(lines) + "\n")

MID, SEED = "HT02-TEST", "8834"
# limpa calls
open(calls_f, "w").write("")

oc.ensure_run_tab(MID, run_dir, seed=SEED)
calls = [json.loads(l) for l in open(calls_f).read().splitlines() if l.strip()]
say("calls 1a: " + json.dumps(calls))

# (i) tab create com label RUN:<ID>#s<seed>
creates = [c for c in calls if c["argv"][:2] == ["tab", "create"]]
assert creates, "sem tab create"
assert creates[0]["argv"][5] == "RUN:%s#s%s" % (MID, SEED), creates[0]
say("OK (i) label unico RUN:%s#s%s" % (MID, SEED))

# (ii) pane run com tail -n +1 -F + trilha literal
pruns = [c for c in calls if c["argv"][:2] == ["pane", "run"]]
assert pruns, "sem pane run"
cmd = pruns[0]["argv"][3]
assert "tail -n +1 -F" in cmd and trail in cmd, cmd
say("OK (ii) pane run: %s" % cmd)

# (iii) executa o comando tail em bash real; 3 linhas aparecem
proc = subprocess.Popen(["bash", "-c", cmd], stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, text=True)
time.sleep(2.0)
proc.kill()
out, _ = proc.communicate()
got = [l for l in (out or "").splitlines() if l.strip()]
assert got == lines, got
say("OK (iii) tail ao vivo: %s" % got)

# (iv) dedupe: 2a chamada NAO cria segunda aba
open(calls_f, "w").write("")
oc.ensure_run_tab(MID, run_dir, seed=SEED)
calls2 = [json.loads(l) for l in open(calls_f).read().splitlines() if l.strip()]
creates2 = [c for c in calls2 if c["argv"][:2] == ["tab", "create"]]
assert not creates2, "criou 2a aba: %s" % creates2
st = json.load(open(state_f))
run_tabs = [t for t in st["tabs"] if t["label"].startswith("RUN:")]
assert len(run_tabs) == 1, run_tabs
assert not any("#" in t["label"] and "#s" not in t["label"] for t in st["tabs"]), st["tabs"]
say("OK (iv) dedupe: 1 aba, sem label #<seed> sem 's'")

# (v) fecho fake: tab_reap --apply com active-json listando run como morto
tabs_json = os.path.join(tmp, "tabs.json")
active_json = os.path.join(tmp, "active.json")
json.dump({"result": {"tabs": json.load(open(state_f))["tabs"]}}, open(tabs_json, "w"))
json.dump({"runs": [{"missionId": "OUTRA-VIVA"}]}, open(active_json, "w"))
open(calls_f, "w").write("")
r = subprocess.run(["bash", os.path.join(BASE, "staging", "tab_reap.sh"), "--apply",
                    "--tabs-json", tabs_json, "--active-json", active_json],
                   capture_output=True, text=True, env=env, timeout=30)
say("tab_reap out: " + r.stdout.strip())
res = json.loads(r.stdout)
assert res["ok"] and len(res["fechadas"]) == 1 and res["fechadas"][0]["label"] == "RUN:%s#s%s" % (MID, SEED), res
calls3 = [json.loads(l) for l in open(calls_f).read().splitlines() if l.strip()]
closes = [c for c in calls3 if c["argv"][:2] == ["tab", "close"]]
assert len(closes) == 1, calls3
say("OK (v) reap fechou aba morta 1x; vivas preservadas")

# (vi) reap na forma antiga RUN:ID#SEED
st2 = {"tabs": [{"tab_id": "tab-old", "label": "RUN:%s#%s" % (MID, SEED), "pane_id": "p"}], "next": 99}
json.dump(st2, open(state_f, "w"))
json.dump({"result": {"tabs": st2["tabs"]}}, open(tabs_json, "w"))
open(calls_f, "w").write("")
r2 = subprocess.run(["bash", os.path.join(BASE, "staging", "tab_reap.sh"), "--apply",
                     "--tabs-json", tabs_json, "--active-json", active_json],
                    capture_output=True, text=True, env=env, timeout=30)
res2 = json.loads(r2.stdout)
assert res2["ok"] and len(res2["fechadas"]) == 1 and res2["fechadas"][0]["label"] == "RUN:%s#%s" % (MID, SEED), res2
say("OK (vi) reap tambem fecha label RUN:ID#SEED (forma antiga)")

say("PROVA-HEADLESS-TAB-02-OK")
LOG.close()